"""Global search (data-level) — Sub-pass B.

One endpoint that fans out across records, entity_types, categories, tags,
and media, returning a unified result list with facets and pagination.

Ranking:
    - MongoDB `$text` on records.search_text (Phase 0 index).
    - Regex + weighted title/label boosts on the smaller collections.

Cursor pagination: opaque base64-encoded skip integer, keeps client stateless.
"""
from __future__ import annotations

import base64
import re
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import strip_id

router = APIRouter(prefix="/search", tags=["search"])

Kind = Literal["record", "entity_type", "category", "tag", "media"]
ALL_KINDS: list[Kind] = ["record", "entity_type", "category", "tag", "media"]

# The public spec uses plural type names (records, entity_types, …) — accept
# both forms and normalize internally to the singular Kind literal.
_KIND_ALIASES = {
    "records": "record",
    "entity_types": "entity_type",
    "entitytypes": "entity_type",
    "categories": "category",
    "tags": "tag",
    "media": "media",
    # Also allow the singular forms
    "record": "record",
    "entity_type": "entity_type",
    "category": "category",
    "tag": "tag",
}


def _normalize_kinds(raw: str) -> list[Kind]:
    """Parse the `types` query param into internal Kind list."""
    if not raw:
        return list(ALL_KINDS)
    out: list[Kind] = []
    seen: set[str] = set()
    for token in raw.split(","):
        t = token.strip().lower()
        if not t:
            continue
        k = _KIND_ALIASES.get(t)
        if k and k not in seen:
            out.append(k)
            seen.add(k)
    return out or list(ALL_KINDS)


def _snippet(text: str, q: str, radius: int = 80) -> str | None:
    if not text or not q:
        return None
    idx = text.lower().find(q.lower())
    if idx < 0:
        return text[: radius * 2].strip() if text else None
    start = max(0, idx - radius)
    end = min(len(text), idx + len(q) + radius)
    out = text[start:end].strip()
    if start > 0:
        out = "…" + out
    if end < len(text):
        out = out + "…"
    return out


def _encode_cursor(skip: int) -> str:
    return base64.urlsafe_b64encode(str(skip).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        pad = "=" * (-len(cursor) % 4)
        return int(base64.urlsafe_b64decode(cursor + pad).decode())
    except Exception:
        return 0


def _regex_escape(q: str) -> str:
    return re.escape(q)


# ──────────────────────────────────────────────────────────────────────
#   Per-kind searchers — each returns (results:list, total_matches:int)
# ──────────────────────────────────────────────────────────────────────

async def _search_records(
    db, org_id: str, q: str, entity_type_ids: list[str] | None,
    limit: int, skip: int,
) -> tuple[list[dict], int]:
    base = tenant_filter(org_id)
    if entity_type_ids:
        base["entity_type_id"] = {"$in": entity_type_ids}
    if not q:
        return [], 0

    # Try $text first (fast, uses index), fall back to regex if text query yields nothing
    text_filter = {**base, "$text": {"$search": q}}
    projection = {
        "_id": 1, "title": 1, "record_number": 1, "entity_type_id": 1,
        "search_text": 1, "updated_at": 1, "tag_ids": 1,
        "score": {"$meta": "textScore"},
    }
    cursor = (
        db.records.find(text_filter, projection)
        .sort([("score", {"$meta": "textScore"})])
        .skip(skip).limit(limit)
    )
    docs = await cursor.to_list(limit)
    total = await db.records.count_documents(text_filter)

    # Fallback regex if $text found nothing (short queries, no stemming match)
    if not docs and skip == 0:
        rx = {"$regex": _regex_escape(q), "$options": "i"}
        rgx_filter = {
            **base,
            "$or": [{"title": rx}, {"record_number": rx}, {"search_text": rx}],
        }
        # Regex query cannot use textScore meta projection
        rgx_projection = {k: v for k, v in projection.items() if k != "score"}
        docs = await db.records.find(rgx_filter, rgx_projection).limit(limit).to_list(limit)
        total = await db.records.count_documents(rgx_filter)

    # Attach entity type breadcrumb
    et_ids = list({d["entity_type_id"] for d in docs})
    ets = {
        e["_id"]: e for e in
        await db.entity_types.find(
            {"_id": {"$in": et_ids}, "org_id": org_id},
            {"_id": 1, "name_plural": 1, "name_singular": 1, "icon": 1, "color": 1},
        ).to_list(len(et_ids))
    }

    results = []
    for d in docs:
        et = ets.get(d["entity_type_id"], {})
        title_lower = (d.get("title") or "").lower()
        rn_lower = (d.get("record_number") or "").lower()
        # Boost exact matches
        base_score = float(d.get("score") or 0)
        if title_lower == q.lower():
            base_score += 10
        elif q.lower() in title_lower:
            base_score += 5
        elif q.lower() in rn_lower:
            base_score += 3

        results.append({
            "kind": "record",
            "id": d["_id"],
            "title": d.get("title") or "(untitled)",
            "subtitle": d.get("record_number"),
            "snippet": _snippet(d.get("search_text") or "", q),
            "score": base_score,
            "breadcrumb": [
                {"label": et.get("name_plural") or et.get("name_singular") or "Records",
                 "path": f"/entity-types/{d['entity_type_id']}/records"},
            ],
            "icon": et.get("icon") or "database",
            "entity_type_id": d["entity_type_id"],
            "record_number": d.get("record_number"),
        })
    return results, total


async def _search_entity_types(
    db, org_id: str, q: str, limit: int, skip: int,
) -> tuple[list[dict], int]:
    if not q:
        return [], 0
    rx = {"$regex": _regex_escape(q), "$options": "i"}
    filt = {
        **tenant_filter(org_id),
        "$or": [{"name_singular": rx}, {"name_plural": rx}, {"key": rx}, {"description": rx}],
    }
    total = await db.entity_types.count_documents(filt)
    docs = await db.entity_types.find(filt).skip(skip).limit(limit).to_list(limit)
    results = []
    for d in docs:
        # naive score: title match > desc match
        name = d.get("name_plural") or d.get("name_singular") or ""
        score = 8 if q.lower() in name.lower() else 4
        results.append({
            "kind": "entity_type",
            "id": d["_id"],
            "title": name,
            "subtitle": d.get("name_singular"),
            "snippet": _snippet(d.get("description") or "", q),
            "score": score,
            "breadcrumb": [{"label": "Entity Types", "path": "/entity-types"}],
            "icon": d.get("icon") or "boxes",
        })
    return results, total


async def _search_categories(
    db, org_id: str, q: str, limit: int, skip: int,
) -> tuple[list[dict], int]:
    if not q:
        return [], 0
    rx = {"$regex": _regex_escape(q), "$options": "i"}
    filt = {
        **tenant_filter(org_id),
        "$or": [{"name": rx}, {"path_names": rx}],
    }
    total = await db.categories.count_documents(filt)
    docs = await db.categories.find(filt).skip(skip).limit(limit).to_list(limit)
    et_ids = list({d.get("entity_type_id") for d in docs if d.get("entity_type_id")})
    ets = {
        e["_id"]: e for e in
        await db.entity_types.find(
            {"_id": {"$in": et_ids}, "org_id": org_id},
            {"_id": 1, "name_plural": 1, "name_singular": 1, "icon": 1},
        ).to_list(len(et_ids))
    }
    results = []
    for d in docs:
        et = ets.get(d.get("entity_type_id"), {})
        et_label = et.get("name_plural") or et.get("name_singular") or "Records"
        path_names = d.get("path_names") or []
        results.append({
            "kind": "category",
            "id": d["_id"],
            "title": d.get("name"),
            "subtitle": " / ".join(path_names) if path_names else None,
            "snippet": None,
            "score": 6 if q.lower() in (d.get("name") or "").lower() else 3,
            "breadcrumb": [
                {"label": et_label, "path": f"/entity-types/{d.get('entity_type_id')}/records"},
                {"label": "Categories", "path": f"/entity-types/{d.get('entity_type_id')}/categories"},
            ],
            "icon": "folder-tree",
        })
    return results, total


async def _search_tags(
    db, org_id: str, q: str, limit: int, skip: int,
) -> tuple[list[dict], int]:
    if not q:
        return [], 0
    rx = {"$regex": _regex_escape(q), "$options": "i"}
    filt = {**tenant_filter(org_id), "name": rx}
    total = await db.tags.count_documents(filt)
    docs = await db.tags.find(filt).skip(skip).limit(limit).to_list(limit)
    et_ids = list({d.get("entity_type_id") for d in docs if d.get("entity_type_id")})
    ets = {
        e["_id"]: e for e in
        await db.entity_types.find(
            {"_id": {"$in": et_ids}, "org_id": org_id},
            {"_id": 1, "name_plural": 1, "name_singular": 1},
        ).to_list(len(et_ids))
    }
    results = []
    for d in docs:
        et = ets.get(d.get("entity_type_id"), {})
        et_label = et.get("name_plural") or et.get("name_singular") or "Records"
        results.append({
            "kind": "tag",
            "id": d["_id"],
            "title": d.get("name"),
            "subtitle": f"used {d.get('usage_count', 0)} times",
            "snippet": None,
            "score": 5 if q.lower() == (d.get("name") or "").lower() else 2,
            "breadcrumb": [
                {"label": et_label, "path": f"/entity-types/{d.get('entity_type_id')}/records"},
                {"label": "Tags", "path": f"/entity-types/{d.get('entity_type_id')}/tags"},
            ],
            "icon": "tag",
            "color": d.get("color"),
        })
    return results, total


async def _search_media(
    db, org_id: str, q: str, limit: int, skip: int,
) -> tuple[list[dict], int]:
    if not q:
        return [], 0
    rx = {"$regex": _regex_escape(q), "$options": "i"}
    filt = {
        **tenant_filter(org_id),
        "$or": [{"filename": rx}, {"caption": rx}, {"alt_text": rx}],
    }
    total = await db.media.count_documents(filt)
    docs = await db.media.find(filt).skip(skip).limit(limit).to_list(limit)
    results = []
    for d in docs:
        results.append({
            "kind": "media",
            "id": d["_id"],
            "title": d.get("filename"),
            "subtitle": d.get("mime"),
            "snippet": _snippet(d.get("caption") or "", q),
            "score": 4 if q.lower() in (d.get("filename") or "").lower() else 2,
            "breadcrumb": [{"label": "Media library", "path": "/media"}],
            "icon": "image" if (d.get("mime") or "").startswith("image/") else "file",
            "mime": d.get("mime"),
        })
    return results, total


# ──────────────────────────────────────────────────────────────────────
#                         The endpoint
# ──────────────────────────────────────────────────────────────────────


@router.get("")
async def global_search(
    request: Request,
    q: str = Query("", max_length=200),
    types: str = Query("", description="Comma-separated: record,entity_type,category,tag,media"),
    entity_type_ids: str = Query("", description="Comma-separated entity type ids"),
    limit: int = Query(20, ge=1, le=50),
    cursor: str | None = Query(None),
    ctx: AuthContext = Depends(require_permission("records.read")),
) -> dict[str, Any]:
    t0 = time.perf_counter()
    q = (q or "").strip()
    kinds = _normalize_kinds(types)
    et_ids = [x.strip() for x in entity_type_ids.split(",") if x.strip()] or None
    skip = _decode_cursor(cursor)

    db = get_db()

    # Fan-out — each kind gets its own slice of the limit, then we re-sort by score.
    # For the palette we want breadth (a few of each); for the /search page the
    # caller can lock `types=records` to get depth on one kind.
    if len(kinds) == 1:
        per_kind_limit = limit
    else:
        per_kind_limit = max(3, limit // max(1, len(kinds)))

    results: list[dict] = []
    totals: dict[str, int] = {}

    if "record" in kinds:
        r, t = await _search_records(db, ctx.org_id, q, et_ids, per_kind_limit, skip)
        results += r
        totals["record"] = t
    if "entity_type" in kinds:
        r, t = await _search_entity_types(db, ctx.org_id, q, per_kind_limit, skip)
        results += r
        totals["entity_type"] = t
    if "category" in kinds:
        r, t = await _search_categories(db, ctx.org_id, q, per_kind_limit, skip)
        results += r
        totals["category"] = t
    if "tag" in kinds:
        r, t = await _search_tags(db, ctx.org_id, q, per_kind_limit, skip)
        results += r
        totals["tag"] = t
    if "media" in kinds:
        r, t = await _search_media(db, ctx.org_id, q, per_kind_limit, skip)
        results += r
        totals["media"] = t

    # Sort by score desc, then by title asc for stability
    results.sort(key=lambda r: (-r["score"], (r.get("title") or "").lower()))
    truncated = results[:limit]

    # Facet: kinds
    kind_facets = [{"kind": k, "count": totals.get(k, 0)} for k in ALL_KINDS if totals.get(k, 0) > 0]

    # Facet: entity types (from records slice — most useful facet)
    et_facet: list[dict] = []
    if q and "record" in kinds:
        pipeline = [
            {"$match": {**tenant_filter(ctx.org_id), "$text": {"$search": q}}},
            {"$group": {"_id": "$entity_type_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 20},
        ]
        try:
            groups = await db.records.aggregate(pipeline).to_list(20)
            et_ids_seen = [g["_id"] for g in groups]
            et_docs = {
                e["_id"]: e for e in
                await db.entity_types.find(
                    {"_id": {"$in": et_ids_seen}, "org_id": ctx.org_id},
                    {"name_plural": 1, "name_singular": 1},
                ).to_list(len(et_ids_seen))
            }
            for g in groups:
                et = et_docs.get(g["_id"], {})
                et_facet.append({
                    "id": g["_id"],
                    "name": et.get("name_plural") or et.get("name_singular") or "(deleted)",
                    "count": g["count"],
                })
        except Exception:
            et_facet = []

    total_matches = sum(totals.values())
    remaining = max(0, total_matches - skip - len(truncated))
    next_cursor = _encode_cursor(skip + limit) if remaining > 0 else None

    took_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "results": truncated,
        "next_cursor": next_cursor,
        "facets": {"entity_types": et_facet, "kinds": kind_facets},
        "totals": totals,
        "took_ms": took_ms,
    }
