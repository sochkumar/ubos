"""
Phase 8 — Universal browse.

`GET /api/records/browse` — cross-collection feed, filterable by
entity_type / category / tag / free-text / updated_since, sorted &
cursor-paginated, with facet counts and per-collection field defs.

Also serves the browse-scope Views CRUD:
    GET  /api/browse/views
    POST /api/browse/views

Browse views are ordinary docs in `views` with `entity_type_id: null`,
so PATCH/DELETE via the existing `/api/views/:vid` endpoints keep
working unchanged.
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import FilterCondition, SortSpec, strip_id
from services.query_builder import build_filter_query

router = APIRouter(tags=["browse"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────── helpers ───────────────────────
def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _encode_cursor(skip: int) -> str:
    return base64.urlsafe_b64encode(str(skip).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        pad = "=" * (-len(cursor) % 4)
        return max(0, int(base64.urlsafe_b64decode(cursor + pad).decode()))
    except Exception:
        return 0


async def _descendant_category_ids(db, org_id: str, cat_id: str) -> list[str]:
    """Descendant-inclusive lookup across ALL entity_types.
    Uses the `path` array field (already indexed as `(org_id, path)`)."""
    cursor = db.categories.find(
        tenant_filter(org_id, {"path": cat_id, "deleted_at": None}),
        {"_id": 1},
    )
    return [d["_id"] for d in await cursor.to_list(10000)]


_SORT_MAP = {
    "updated_at:desc": [("updated_at", -1), ("_id", -1)],
    "updated_at:asc":  [("updated_at",  1), ("_id",  1)],
    "created_at:desc": [("created_at", -1), ("_id", -1)],
    "created_at:asc":  [("created_at",  1), ("_id",  1)],
    "title:asc":       [("title",  1), ("_id",  1)],
    "title:desc":      [("title", -1), ("_id", -1)],
}


# ─────────────────────── main endpoint ───────────────────────
@router.get(
    "/records/browse",
    description=(
        "Cross-collection browsable feed. Returns records across every entity_type "
        "the caller has read on, with facet counts and the field definitions needed "
        "to render adaptive layouts client-side."
    ),
)
async def browse_records(
    q: str | None = Query(default=None, description="free-text search on search_text"),
    entity_type_ids: str | None = Query(default=None, description="comma-separated"),
    category_ids:    str | None = Query(default=None, description="comma-separated (descendant-inclusive)"),
    tag_ids:         str | None = Query(default=None, description="comma-separated"),
    updated_since:   str | None = Query(default=None, description="ISO timestamp"),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    sort: str = Query(default="updated_at:desc"),
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    started = time.perf_counter()
    db = get_db()

    et_ids = _split_csv(entity_type_ids)
    cat_ids = _split_csv(category_ids)
    tag_ids_list = _split_csv(tag_ids)

    sort_spec = _SORT_MAP.get(sort) or _SORT_MAP["updated_at:desc"]

    # ── Build the base filter ──
    filt: dict[str, Any] = tenant_filter(ctx.org_id)
    if et_ids:
        filt["entity_type_id"] = {"$in": et_ids}
    if q:
        filt["$text"] = {"$search": q}
    if updated_since:
        filt["updated_at"] = {"$gte": updated_since}

    # Descendant-inclusive category expansion (union across all supplied cats)
    if cat_ids:
        expanded: set[str] = set()
        for cid in cat_ids:
            expanded.update(await _descendant_category_ids(db, ctx.org_id, cid))
            expanded.add(cid)
        filt["category_ids"] = {"$in": list(expanded)}
    if tag_ids_list:
        filt["tag_ids"] = {"$in": tag_ids_list}

    skip = _decode_cursor(cursor)

    # ── Fetch page + total ──
    # Note: mongo $text score isn't required for our use; default relevance +
    # then the requested sort is fine.
    total = await db.records.count_documents(filt)
    cursor_docs = db.records.find(filt).sort(sort_spec).skip(skip).limit(limit)
    rows = await cursor_docs.to_list(limit)

    # ── Enrich rows with entity_type summary + primary image + refs ──
    et_map: dict[str, dict] = {}
    async for et in db.entity_types.find(
        tenant_filter(ctx.org_id, {"deleted_at": None}),
        {"key": 1, "name_singular": 1, "name_plural": 1, "icon": 1, "color": 1},
    ):
        et_map[et["_id"]] = {
            "id": et["_id"],
            "key": et.get("key"),
            "name_singular": et.get("name_singular"),
            "name_plural": et.get("name_plural"),
            "icon": et.get("icon"),
            "color": et.get("color"),
        }

    # Collect field defs only for entity_types actually present in the response.
    et_ids_in_page = sorted({r["entity_type_id"] for r in rows if r.get("entity_type_id")})
    field_defs_by_et: dict[str, list[dict]] = {}
    if et_ids_in_page:
        fd_cursor = db.field_definitions.find(
            tenant_filter(ctx.org_id, {"entity_type_id": {"$in": et_ids_in_page}}),
        ).sort([("entity_type_id", 1), ("order", 1)])
        async for fd in fd_cursor:
            field_defs_by_et.setdefault(fd["entity_type_id"], []).append(strip_id(fd))

    # Denormalise category paths + primary image
    all_cat_ids: set[str] = set()
    for r in rows:
        for cid in (r.get("category_ids") or []):
            all_cat_ids.add(cid)
    cats_map: dict[str, dict] = {}
    if all_cat_ids:
        async for c in db.categories.find(
            tenant_filter(ctx.org_id, {"_id": {"$in": list(all_cat_ids)}}),
            {"name": 1, "path_names": 1, "entity_type_id": 1},
        ):
            cats_map[c["_id"]] = {"id": c["_id"], "name": c.get("name"),
                                  "path_names": c.get("path_names") or [c.get("name")]}

    # Tag lookup for denorm
    all_tag_ids: set[str] = set()
    for r in rows:
        for tid in (r.get("tag_ids") or []):
            all_tag_ids.add(tid)
    tags_map: dict[str, dict] = {}
    if all_tag_ids:
        async for tg in db.tags.find(
            tenant_filter(ctx.org_id, {"_id": {"$in": list(all_tag_ids)}}),
            {"name": 1, "color": 1},
        ):
            tags_map[tg["_id"]] = {"id": tg["_id"], "name": tg.get("name"), "color": tg.get("color")}

    def _primary_image_url(rec: dict) -> str | None:
        """Find first image field with a media_id; return relative /api URL."""
        defs = field_defs_by_et.get(rec.get("entity_type_id") or "", [])
        for fd in defs:
            if fd.get("type") != "image":
                continue
            v = (rec.get("fields") or {}).get(fd["key"])
            if not v:
                continue
            if isinstance(v, list) and v:
                v = v[0]
            mid = v.get("media_id") if isinstance(v, dict) else v
            if isinstance(mid, str) and mid:
                return f"/api/media/{mid}/thumb"
        return None

    results: list[dict] = []
    for r in rows:
        et = et_map.get(r.get("entity_type_id") or "") or {
            "id": r.get("entity_type_id"), "key": None, "name_singular": None,
            "name_plural": None, "icon": None, "color": None,
        }
        results.append({
            "id": r["_id"],
            "entity_type_id": r.get("entity_type_id"),
            "entity_type": et,
            "title": r.get("title"),
            "record_number": r.get("record_number"),
            "fields": r.get("fields") or {},
            "category_ids": r.get("category_ids") or [],
            "category_paths": [cats_map.get(c) for c in (r.get("category_ids") or []) if cats_map.get(c)],
            "tag_ids": r.get("tag_ids") or [],
            "tags": [tags_map.get(t) for t in (r.get("tag_ids") or []) if tags_map.get(t)],
            "primary_image_url": _primary_image_url(r),
            "created_at": r.get("created_at"),
            "updated_at": r.get("updated_at"),
            "updated_by": r.get("updated_by"),
        })

    # ── Facets: count records per entity_type / category / tag under the
    # SAME base filter (excluding the facet's own dimension so users can
    # broaden their selection). For MVP we use the filter as-is; the client
    # can decide to "remove-and-recount". ──
    async def _facet_group(field: str) -> list[dict]:
        pipe = [
            {"$match": filt},
            {"$unwind": {"path": f"${field}", "preserveNullAndEmptyArrays": False}} if field.endswith("_ids") else {"$match": {}},
            {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 30},
        ]
        # simpler for scalar entity_type_id (no unwind needed)
        if not field.endswith("_ids"):
            pipe = [
                {"$match": filt},
                {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 50},
            ]
        return await db.records.aggregate(pipe).to_list(100)

    et_counts = await _facet_group("entity_type_id")
    cat_counts = await _facet_group("category_ids")
    tag_counts = await _facet_group("tag_ids")

    facets = {
        "entity_types": [
            {
                "id": x["_id"],
                "name": (et_map.get(x["_id"]) or {}).get("name_plural") or (et_map.get(x["_id"]) or {}).get("name_singular"),
                "color": (et_map.get(x["_id"]) or {}).get("color"),
                "count": x["count"],
            }
            for x in et_counts if x["_id"]
        ],
        "categories": [
            {
                "id": x["_id"],
                "name": (cats_map.get(x["_id"]) or {}).get("name"),
                "path_names": (cats_map.get(x["_id"]) or {}).get("path_names") or [],
                "count": x["count"],
            }
            for x in cat_counts if x["_id"] and cats_map.get(x["_id"])
        ],
        "tags": [
            {
                "id": x["_id"],
                "name": (tags_map.get(x["_id"]) or {}).get("name"),
                "color": (tags_map.get(x["_id"]) or {}).get("color"),
                "count": x["count"],
            }
            for x in tag_counts if x["_id"] and tags_map.get(x["_id"])
        ],
    }

    next_cursor = _encode_cursor(skip + limit) if (skip + limit) < total else None
    took_ms = int((time.perf_counter() - started) * 1000)

    return {
        "results": results,
        "next_cursor": next_cursor,
        "facets": facets,
        "total_estimate": total,
        "took_ms": took_ms,
        "entity_type_field_defs": field_defs_by_et,
        "sort": sort,
    }


# ─────────────────────── browse view CRUD ───────────────────────
class BrowseViewCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    layout: Literal["table", "gallery", "grid", "card", "list"] = "table"
    q: str | None = None
    entity_type_ids: list[str] = Field(default_factory=list)
    category_ids: list[str] = Field(default_factory=list)
    tag_ids: list[str] = Field(default_factory=list)
    updated_since: str | None = None
    sort: str = "updated_at:desc"
    visible_fields: list[str] = Field(default_factory=list)
    is_shared: bool = False


@router.get("/browse/views")
async def list_browse_views(
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    cursor = db.views.find({
        "org_id": ctx.org_id,
        "entity_type_id": None,
        "deleted_at": None,
        "$or": [
            {"user_id": ctx.user["_id"]},
            {"is_shared": True},
            {"shared_with.user_id": ctx.user["_id"]},
        ],
    }).sort("created_at", 1)
    return [strip_id(d) for d in await cursor.to_list(500)]


@router.post("/browse/views", status_code=201)
async def create_browse_view(
    payload: BrowseViewCreate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    if payload.is_shared and ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "only owners/admins can create shared views")
    db = get_db()
    vid = str(uuid.uuid4())
    doc = {
        "_id": vid,
        "org_id": ctx.org_id,
        "entity_type_id": None,  # ← browse marker
        "user_id": ctx.user["_id"],
        "name": payload.name,
        "description": payload.description,
        "layout": payload.layout,
        # Reuse the "views" doc shape wherever possible so existing PATCH/DELETE
        # keeps working. Browse-specific state goes on top-level fields the UI
        # knows how to read; nothing else touches them.
        "q": payload.q,
        "browse_entity_type_ids": payload.entity_type_ids,
        "category_ids": payload.category_ids,
        "tag_ids": payload.tag_ids,
        "updated_since": payload.updated_since,
        "browse_sort": payload.sort,
        "visible_fields": payload.visible_fields,
        "filters": [],           # not used in browse-mode; kept for schema uniformity
        "sort": [],              # ditto — browse uses browse_sort (string)
        "column_widths": {},
        "is_default": False,
        "is_shared": payload.is_shared,
        "shared_with": [],
        "created_at": _now(), "updated_at": _now(), "deleted_at": None,
    }
    await db.views.insert_one(doc)
    audit(bg, action="browse_view.created", actor_id=ctx.user["_id"],
          org_id=ctx.org_id, target_type="view", target_id=vid,
          diff={"name": payload.name, "shared": payload.is_shared},
          request=request)
    return strip_id(doc)
