"""Dashboard summary — Sub-pass B.

One endpoint that returns the four widgets in a single payload,
process-cached for 30 s per (org_id, user_id).
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Process-level cache — 30 s TTL, keyed by (org_id, user_id)
_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
_TTL_SEC = 30.0


def _mime_family(mime: str | None) -> str:
    if not mime:
        return "other"
    if mime.startswith("image/"):
        return "images"
    if mime.startswith("video/"):
        return "videos"
    if mime.startswith("audio/"):
        return "audio"
    if mime in ("application/pdf",) or mime.startswith("text/") or "document" in mime or "sheet" in mime or "presentation" in mime:
        return "documents"
    return "other"


async def _recent_records(db, org_id: str) -> list[dict]:
    docs = await db.records.find(
        tenant_filter(org_id),
        {
            "_id": 1, "title": 1, "record_number": 1, "entity_type_id": 1,
            "updated_at": 1, "created_at": 1, "tag_ids": 1,
        },
    ).sort("updated_at", -1).limit(10).to_list(10)
    et_ids = list({d.get("entity_type_id") for d in docs if d.get("entity_type_id")})
    ets = {
        e["_id"]: e for e in
        await db.entity_types.find(
            {"_id": {"$in": et_ids}, "org_id": org_id},
            {"name_singular": 1, "name_plural": 1, "icon": 1, "color": 1},
        ).to_list(len(et_ids))
    }
    tag_ids: list[str] = []
    for d in docs:
        tag_ids.extend(d.get("tag_ids") or [])
    if tag_ids:
        tag_docs = await db.tags.find(
            {"_id": {"$in": tag_ids}, "org_id": org_id},
            {"name": 1, "color": 1},
        ).to_list(len(tag_ids))
        tags = {t["_id"]: t for t in tag_docs}
    else:
        tags = {}

    # Derive last-actor per record from the most recent record.created / record.updated
    # audit event on each target_id (one aggregation, no N+1).
    actors_by_record: dict[str, dict[str, Any]] = {}
    rec_ids = [d["_id"] for d in docs]
    if rec_ids:
        pipeline = [
            {"$match": {
                "org_id": org_id,
                "target_type": "record",
                "target_id": {"$in": rec_ids},
                "action": {"$in": ["record.created", "record.updated"]},
            }},
            {"$sort": {"ts": -1}},
            {"$group": {
                "_id": "$target_id",
                "actor_id": {"$first": "$actor_id"},
                "action": {"$first": "$action"},
                "ts": {"$first": "$ts"},
            }},
        ]
        rows = await db.audit_logs.aggregate(pipeline).to_list(len(rec_ids))
        actor_ids = list({r.get("actor_id") for r in rows if r.get("actor_id")})
        if actor_ids:
            user_docs = await db.users.find(
                {"_id": {"$in": actor_ids}},
                {"name": 1, "email": 1, "avatar_url": 1},
            ).to_list(len(actor_ids))
            users = {u["_id"]: u for u in user_docs}
        else:
            users = {}
        for r in rows:
            u = users.get(r.get("actor_id")) or {}
            actors_by_record[r["_id"]] = {
                "id": r.get("actor_id"),
                "name": u.get("name") or u.get("email") or "someone",
                "avatar_url": u.get("avatar_url"),
                "action": r.get("action"),  # tells UI whether it was create vs update
            }

    out = []
    for d in docs:
        et = ets.get(d.get("entity_type_id"), {})
        et_name = et.get("name_plural") or et.get("name_singular") or "Records"
        out.append({
            "id": d["_id"],
            "title": d.get("title") or "(untitled)",
            "record_number": d.get("record_number"),
            "entity_type": {
                "id": d.get("entity_type_id"),
                "name": et_name,
                "icon": et.get("icon"),
                "color": et.get("color"),
            },
            "updated_at": d.get("updated_at"),
            "actor": actors_by_record.get(d["_id"]),
            "tags": [
                {"id": tid, "name": tags.get(tid, {}).get("name"), "color": tags.get(tid, {}).get("color")}
                for tid in (d.get("tag_ids") or [])[:3] if tid in tags
            ],
        })
    return out


async def _activity(db, org_id: str, ctx: AuthContext) -> list[dict]:
    q: dict[str, Any] = {"org_id": org_id}
    # Non-admins see only their own activity + org-wide broadcast events
    if ctx.role not in ("owner", "admin"):
        q["actor_id"] = ctx.user["_id"]
    docs = await db.audit_logs.find(q).sort("ts", -1).limit(15).to_list(15)
    actor_ids = list({d.get("actor_id") for d in docs if d.get("actor_id")})
    if actor_ids:
        user_docs = await db.users.find(
            {"_id": {"$in": actor_ids}},
            {"name": 1, "email": 1, "avatar_url": 1},
        ).to_list(len(actor_ids))
        users = {u["_id"]: u for u in user_docs}
    else:
        users = {}
    out = []
    for d in docs:
        actor = users.get(d.get("actor_id"), {})
        out.append({
            "id": d["_id"],
            "action": d.get("action"),
            "target_type": d.get("target_type"),
            "target_id": d.get("target_id"),
            "diff": d.get("diff") or {},
            "ts": d.get("ts"),
            "actor": {
                "id": d.get("actor_id"),
                "name": actor.get("name") or actor.get("email") or "someone",
                "avatar_url": actor.get("avatar_url"),
            },
        })
    return out


async def _storage(db, org_id: str) -> dict[str, Any]:
    org = await db.organizations.find_one(
        {"_id": org_id, "deleted_at": None},
        {"storage_used_bytes": 1, "settings": 1},
    )
    used = int((org or {}).get("storage_used_bytes") or 0)
    quota = int(((org or {}).get("settings") or {}).get("storage_quota_bytes") or 0)

    # Breakdown by mime family
    pipeline = [
        {"$match": {**tenant_filter(org_id)}},
        {"$group": {"_id": "$mime", "size": {"$sum": "$size"}, "count": {"$sum": 1}}},
    ]
    by_family: dict[str, dict[str, int]] = {}
    async for g in db.media.aggregate(pipeline):
        fam = _mime_family(g.get("_id"))
        b = by_family.setdefault(fam, {"size": 0, "count": 0})
        b["size"] += int(g.get("size") or 0)
        b["count"] += int(g.get("count") or 0)
    return {
        "used_bytes": used,
        "quota_bytes": quota,
        "pct": (used / quota * 100.0) if quota > 0 else 0.0,
        "by_mime_family": by_family,
    }


async def _entity_types_overview(db, org_id: str) -> list[dict]:
    ets = await db.entity_types.find(
        tenant_filter(org_id),
        {"_id": 1, "name_singular": 1, "name_plural": 1, "icon": 1, "color": 1, "key": 1},
    ).to_list(200)
    if not ets:
        return []
    pipeline = [
        {"$match": {**tenant_filter(org_id)}},
        {"$group": {"_id": "$entity_type_id", "count": {"$sum": 1}}},
    ]
    counts = {g["_id"]: int(g["count"]) async for g in db.records.aggregate(pipeline)}
    rows = []
    for e in ets:
        name_plural = e.get("name_plural")
        name_singular = e.get("name_singular")
        rows.append({
            "id": e["_id"],
            "key": e.get("key"),
            # Unified `name` for dashboard clients; falls back to singular
            "name": name_plural or name_singular or "Records",
            "name_singular": name_singular,
            "name_plural": name_plural,
            "icon": e.get("icon"),
            "color": e.get("color"),
            "record_count": counts.get(e["_id"], 0),
        })
    rows.sort(key=lambda r: (-r["record_count"], (r["name"] or "").lower()))
    return rows


@router.get("/summary")
async def dashboard_summary(
    ctx: AuthContext = Depends(require_permission("records.read")),
) -> dict[str, Any]:
    key = (ctx.org_id, ctx.user["_id"])
    now = time.time()
    cached = _CACHE.get(key)
    if cached and (now - cached[0]) < _TTL_SEC:
        return {**cached[1], "cached": True}

    db = get_db()
    recent = await _recent_records(db, ctx.org_id)
    activity = await _activity(db, ctx.org_id, ctx)
    storage = await _storage(db, ctx.org_id)
    ets = await _entity_types_overview(db, ctx.org_id)
    payload = {
        "recent_records": recent,
        "activity": activity,
        "storage": storage,
        "entity_types": ets,
        "cached": False,
    }
    _CACHE[key] = (now, payload)
    return payload


@router.post("/refresh", status_code=204, response_class=Response)
async def bust_cache(
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    """Manual cache bust — used by the frontend after user-driven writes."""
    _CACHE.pop((ctx.org_id, ctx.user["_id"]), None)
    return Response(status_code=204)
