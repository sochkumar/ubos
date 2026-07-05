"""Share links: CRUD + public read/media/qr/barcode endpoints."""
from __future__ import annotations

import io
import os
import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from audit import audit
from auth_deps import AuthContext, require_permission, try_auth
from core.storage.factory import get_storage_adapter
from db import get_db, tenant_filter
from models import strip_id
from services.qr_barcode import make_qr_png, make_barcode_png

router = APIRouter(tags=["share-links"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _public_base() -> str:
    return (os.environ.get("PUBLIC_APP_URL") or os.environ.get("APP_BASE_URL") or "").rstrip("/")


# ---------------- Simple in-memory rate limiter ----------------
_RL: dict[str, list[float]] = defaultdict(list)


def _check_rate(key: str, per_minute: int) -> None:
    now = time.time()
    hits = _RL[key]
    cutoff = now - 60.0
    while hits and hits[0] < cutoff:
        hits.pop(0)
    if len(hits) >= per_minute:
        raise HTTPException(429, {"code": "rate_limited", "detail": "Too many requests"})
    hits.append(now)


# ---------------- Models ----------------
class ShareCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    visibility: Literal["private", "org_only", "public"] = "public"
    visible_fields: list[str] | None = None
    include_media: bool = True
    include_relationships: bool = False
    expires_at: datetime | None = None


class ShareUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    visibility: Literal["private", "org_only", "public"] | None = None
    visible_fields: list[str] | None = None
    include_media: bool | None = None
    include_relationships: bool | None = None
    expires_at: datetime | None = None


def _serialize_share(doc: dict) -> dict:
    d = strip_id(doc)
    base = _public_base()
    d["public_url"] = f"{base}/s/{doc['token']}" if base else f"/s/{doc['token']}"
    return d


def _share_active(s: dict) -> bool:
    if s.get("revoked_at"):
        return False
    exp = s.get("expires_at")
    if exp:
        exp_dt = exp if isinstance(exp, datetime) else datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        if exp_dt < _now():
            return False
    return True


# ---------------- Authenticated CRUD ----------------
@router.get("/records/{rid}/shares")
async def list_record_shares(
    rid: str, ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    if not await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rid}), {"_id": 1}):
        raise HTTPException(404, "record not found")
    cursor = db.share_links.find(
        {"org_id": ctx.org_id, "record_id": rid}
    ).sort("created_at", -1)
    return [_serialize_share(d) for d in await cursor.to_list(200)]


@router.post("/records/{rid}/shares", status_code=201)
async def create_record_share(
    rid: str, body: ShareCreate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    db = get_db()
    if not await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rid}), {"_id": 1}):
        raise HTTPException(404, "record not found")
    token = secrets.token_urlsafe(24)
    doc = {
        "_id": str(uuid.uuid4()),
        "org_id": ctx.org_id,
        "record_id": rid,
        "token": token,
        "visibility": body.visibility,
        "visible_fields": body.visible_fields,
        "include_media": bool(body.include_media),
        "include_relationships": bool(body.include_relationships),
        "expires_at": body.expires_at.isoformat() if body.expires_at else None,
        "revoked_at": None,
        "view_count": 0,
        "last_viewed_at": None,
        "created_by": ctx.user["_id"],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.share_links.insert_one(doc)
    audit(bg, action="share.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="record", target_id=rid,
          diff={"share_id": doc["_id"], "visibility": body.visibility}, request=request)
    return _serialize_share(doc)


@router.patch("/shares/{sid}")
async def update_share(
    sid: str, body: ShareUpdate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    db = get_db()
    doc = await db.share_links.find_one({"_id": sid, "org_id": ctx.org_id})
    if not doc:
        raise HTTPException(404, "share not found")
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if "expires_at" in updates and updates["expires_at"]:
        updates["expires_at"] = updates["expires_at"].isoformat() \
            if isinstance(updates["expires_at"], datetime) else updates["expires_at"]
    updates["updated_at"] = _now_iso()
    await db.share_links.update_one({"_id": sid}, {"$set": updates})
    fresh = await db.share_links.find_one({"_id": sid})
    audit(bg, action="share.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="share", target_id=sid, diff=updates, request=request)
    return _serialize_share(fresh)


@router.post("/shares/{sid}/revoke")
async def revoke_share(
    sid: str, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    db = get_db()
    doc = await db.share_links.find_one({"_id": sid, "org_id": ctx.org_id})
    if not doc:
        raise HTTPException(404, "share not found")
    if doc["created_by"] != ctx.user["_id"] and ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "only the creator or an admin can revoke")
    now = _now_iso()
    await db.share_links.update_one(
        {"_id": sid}, {"$set": {"revoked_at": now, "updated_at": now}},
    )
    audit(bg, action="share.revoked", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="share", target_id=sid, request=request)
    fresh = await db.share_links.find_one({"_id": sid})
    return _serialize_share(fresh)


@router.delete("/shares/{sid}", status_code=204)
async def delete_share(
    sid: str, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    db = get_db()
    doc = await db.share_links.find_one({"_id": sid, "org_id": ctx.org_id})
    if not doc:
        raise HTTPException(404, "share not found")
    if doc["created_by"] != ctx.user["_id"] and ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "only the creator or an admin can delete")
    await db.share_links.delete_one({"_id": sid})
    audit(bg, action="share.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="share", target_id=sid, request=request)
    return None


# ---------------- Helpers for the public payload ----------------
async def _load_share(db, token: str) -> dict:
    s = await db.share_links.find_one({"token": token})
    if not s:
        raise HTTPException(404, "share link not found")
    if not _share_active(s):
        raise HTTPException(status_code=410, detail={
            "code": "share_expired_or_revoked",
            "detail": "This link is no longer available.",
        })
    return s


async def _build_public_payload(
    db, share: dict, ctx_org: str | None = None,
) -> dict:
    org_id = share["org_id"]
    rec = await db.records.find_one(tenant_filter(org_id, {"_id": share["record_id"]}))
    if not rec:
        raise HTTPException(404, "record not found")

    field_defs = await db.field_definitions.find(
        tenant_filter(org_id, {"entity_type_id": rec["entity_type_id"]}),
    ).sort("order", 1).to_list(1000)

    # Sensitive fields are always stripped in public payload assembly.
    non_sensitive_keys = [f["key"] for f in field_defs if not (f.get("config") or {}).get("sensitive")]
    if share.get("visible_fields") is not None:
        keys = [k for k in share["visible_fields"] if k in non_sensitive_keys]
    else:
        keys = non_sensitive_keys

    fields_out = {k: rec.get("fields", {}).get(k) for k in keys}
    exposed_defs = [
        {k2: v for k2, v in fd.items() if k2 != "_id" and k2 != "org_id" and k2 != "entity_type_id"}
        for fd in field_defs if fd["key"] in keys
    ]

    org = await db.organizations.find_one({"_id": org_id}, {"name": 1})

    payload = {
        "record": {
            "id": rec["_id"],
            "title": rec.get("title"),
            "record_number": rec.get("record_number"),
            "description": rec.get("description"),
            "fields": fields_out,
            "created_at": rec.get("created_at"),
            "updated_at": rec.get("updated_at"),
        },
        "field_defs": exposed_defs,
        "org": {"name": (org or {}).get("name"), "id": org_id},
        "share": {
            "token": share["token"],
            "visibility": share["visibility"],
            "include_media": share.get("include_media", True),
            "include_relationships": share.get("include_relationships", False),
        },
    }

    # Categories + tags — always public if visible
    if rec.get("category_ids"):
        cats = await db.categories.find(
            tenant_filter(org_id, {"_id": {"$in": rec["category_ids"]}}),
            {"name": 1, "path_names": 1, "slug": 1, "color": 1},
        ).to_list(200)
        payload["record"]["categories"] = [
            {"id": c["_id"], "name": c["name"], "path_names": c.get("path_names")}
            for c in cats
        ]
    if rec.get("tag_ids"):
        tags = await db.tags.find(
            tenant_filter(org_id, {"_id": {"$in": rec["tag_ids"]}}),
            {"name": 1, "slug": 1, "color": 1},
        ).to_list(200)
        payload["record"]["tags"] = [
            {"id": t["_id"], "name": t["name"], "color": t.get("color")} for t in tags
        ]

    # Media
    if share.get("include_media"):
        media_docs = await db.media.find(
            {"org_id": org_id, "deleted_at": None, "attached_to.record_id": rec["_id"]},
            {"filename": 1, "mime": 1, "size": 1, "attached_to": 1},
        ).to_list(200)
        payload["media"] = [
            {"id": m["_id"], "filename": m["filename"], "mime": m["mime"], "size": m["size"]}
            for m in media_docs
        ]
    else:
        payload["media"] = []

    # Relationship summaries (no full expansion)
    if share.get("include_relationships"):
        from services.relationships import list_relationships_for_record
        rels = await list_relationships_for_record(db, org_id=org_id, record_id=rec["_id"])
        # keep only { label, direction, items: [{title, record_number, entity_type_name}] }
        summary_groups = []
        for g in rels.get("groups", []):
            summary_groups.append({
                "label": g["label"],
                "direction": g["direction"],
                "items": [
                    {"title": it["title"], "record_number": it["record_number"],
                     "entity_type_name": it.get("entity_type_name")}
                    for it in g["items"]
                ],
            })
        payload["relationships"] = summary_groups
    else:
        payload["relationships"] = []

    return payload


async def _record_view(db, share_id: str, bg: BackgroundTasks) -> None:
    """Fire-and-forget view counter — sample audit at most once per minute per share."""
    async def _do():
        await db.share_links.update_one(
            {"_id": share_id},
            {"$inc": {"view_count": 1}, "$set": {"last_viewed_at": _now_iso()}},
        )
    bg.add_task(_do)


# ---------------- Public endpoints (unauthed OR org-only) ----------------
@router.get("/public/records/{token}")
async def public_get_record(
    token: str, request: Request, bg: BackgroundTasks,
    ctx: AuthContext | None = Depends(try_auth),
):
    _check_rate(f"pub:{request.client.host if request.client else 'unknown'}", per_minute=60)
    db = get_db()
    share = await _load_share(db, token)

    # Gate by visibility
    v = share["visibility"]
    if v == "private":
        if not ctx or ctx.org_id != share["org_id"]:
            raise HTTPException(401, "authentication required for this share")
    elif v == "org_only":
        if not ctx or ctx.org_id != share["org_id"]:
            raise HTTPException(401, "authentication in the owning org required")
    # public → no auth required

    payload = await _build_public_payload(db, share)
    await _record_view(db, share["_id"], bg)
    return payload


@router.get("/public/records/{token}/media/{media_id}")
async def public_serve_shared_media(
    token: str, media_id: str, request: Request,
    ctx: AuthContext | None = Depends(try_auth),
):
    _check_rate(f"pub_media:{request.client.host if request.client else 'unknown'}", per_minute=60)
    db = get_db()
    share = await _load_share(db, token)
    v = share["visibility"]
    if v in ("private", "org_only"):
        if not ctx or ctx.org_id != share["org_id"]:
            raise HTTPException(401, "authentication required")
    if not share.get("include_media"):
        raise HTTPException(403, "media not included in this share")

    m = await db.media.find_one({"_id": media_id, "org_id": share["org_id"], "deleted_at": None})
    if not m:
        raise HTTPException(404, "media not found")
    # Confirm this media is attached to the shared record
    attached = any(
        (a.get("record_id") == share["record_id"])
        for a in (m.get("attached_to") or [])
    )
    if not attached:
        raise HTTPException(404, "media not attached to this record")

    adapter = get_storage_adapter()
    url = await adapter.presigned_get(m["storage_key"], ttl_seconds=1800)
    return {"url": url, "filename": m["filename"], "mime": m["mime"], "size": m["size"]}


# ---------------- QR / Barcode (authed) ----------------
async def _resolve_qr_payload(db, org_id: str, record_id: str) -> str:
    # Prefer an active public share; fall back to the record's own qr_payload.
    share = await db.share_links.find_one({
        "org_id": org_id, "record_id": record_id,
        "visibility": "public", "revoked_at": None,
    }, sort=[("created_at", -1)])
    base = _public_base()
    if share and _share_active(share):
        return f"{base}/s/{share['token']}" if base else f"/s/{share['token']}"
    rec = await db.records.find_one(tenant_filter(org_id, {"_id": record_id}), {"qr_payload": 1})
    if rec and rec.get("qr_payload"):
        return rec["qr_payload"]
    return f"{base}/r/{record_id}" if base else f"/r/{record_id}"


@router.get("/records/{rid}/qr.png")
async def qr_for_record(
    rid: str,
    size: int = Query(default=256, ge=64, le=1024),
    margin: int = Query(default=4, ge=0, le=16),
    level: Literal["L", "M", "Q", "H"] = Query(default="M"),
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    if not await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rid}), {"_id": 1}):
        raise HTTPException(404, "record not found")
    text = await _resolve_qr_payload(db, ctx.org_id, rid)
    png = make_qr_png(text, size=size, border=margin, level=level)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=300"})


@router.get("/records/{rid}/barcode.png")
async def barcode_for_record(
    rid: str,
    height: int = Query(default=80, ge=30, le=300),
    text: bool = Query(default=True),
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    rec = await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rid}), {"record_number": 1})
    if not rec:
        raise HTTPException(404, "record not found")
    png = make_barcode_png(rec["record_number"], height=height, write_text=text)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=300"})


@router.get("/public/records/{token}/qr.png")
async def qr_for_shared_record(
    token: str, request: Request,
    size: int = Query(default=256, ge=64, le=1024),
    margin: int = Query(default=4, ge=0, le=16),
    level: Literal["L", "M", "Q", "H"] = Query(default="M"),
):
    _check_rate(f"pub_qr:{request.client.host if request.client else 'unknown'}", per_minute=30)
    db = get_db()
    share = await _load_share(db, token)
    if share["visibility"] != "public":
        raise HTTPException(401, "public QR only available for public shares")
    base = _public_base()
    url = f"{base}/s/{token}" if base else f"/s/{token}"
    png = make_qr_png(url, size=size, border=margin, level=level)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("/public/records/{token}/barcode.png")
async def barcode_for_shared_record(
    token: str, request: Request,
    height: int = Query(default=80, ge=30, le=300),
    text: bool = Query(default=True),
):
    _check_rate(f"pub_bc:{request.client.host if request.client else 'unknown'}", per_minute=30)
    db = get_db()
    share = await _load_share(db, token)
    if share["visibility"] != "public":
        raise HTTPException(401, "public barcode only available for public shares")
    rec = await db.records.find_one(
        tenant_filter(share["org_id"], {"_id": share["record_id"]}),
        {"record_number": 1},
    )
    if not rec:
        raise HTTPException(404, "record not found")
    png = make_barcode_png(rec["record_number"], height=height, write_text=text)
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})
