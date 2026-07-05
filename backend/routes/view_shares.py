"""View-share endpoints — Phase 5-B.

Uses the same `share_links` collection as record shares, discriminated by `kind`.
Kind='view' → shared saved views (public read of a filtered record list).

Also: internal (RBAC-gated) sharing via `views.shared_with[]`.
"""
from __future__ import annotations

import base64
import os
import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

import bcrypt
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from audit import audit
from auth_deps import AuthContext, require_permission, try_auth
from db import get_db, tenant_filter
from models import strip_id
from routes.shares import (
    _check_password_gate, _check_rate, _client_ip, _hash_password,
    _public_base, _serialize_share, _share_active, _sign_unlock,
    _unlock_cookie_name, _UNLOCK_TTL_SEC, _verify_password, _RL,
    _UNLOCK_ATTEMPT_LIMIT, _UNLOCK_ATTEMPT_WINDOW, _READ_PER_MIN,
)
from services.query_builder import build_filter_query, build_sort_spec
from services.categories import descendant_ids_including_self

router = APIRouter(tags=["view-shares"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


_VISIBILITY = Literal["private", "org_only", "public", "password"]


class ViewShareCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    visibility: _VISIBILITY = "public"
    visible_columns: list[str] | None = None
    include_media: bool = False
    include_relationships: bool = False
    expires_at: datetime | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class ViewShareUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    visibility: _VISIBILITY | None = None
    visible_columns: list[str] | None = None
    include_media: bool | None = None
    include_relationships: bool | None = None
    expires_at: datetime | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UnlockBody(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class CollaboratorAdd(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    permission: Literal["view", "edit"] = "view"


class CollaboratorUpdate(BaseModel):
    permission: Literal["view", "edit"]


def _serialize_view_share(doc: dict) -> dict:
    d = strip_id(doc)
    d.pop("password_hash", None)
    d["has_password"] = bool(doc.get("password_hash"))
    base = _public_base()
    d["public_url"] = f"{base}/v/{doc['token']}" if base else f"/v/{doc['token']}"
    return d


async def _load_share_view(db, token: str) -> dict:
    s = await db.share_links.find_one({"token": token, "kind": "view"})
    if not s:
        raise HTTPException(404, {"code": "share_not_found",
                                   "detail": "This view link is not valid."})
    if not _share_active(s):
        raise HTTPException(status_code=410, detail={
            "code": "share_expired_or_revoked",
            "detail": "This link is no longer available.",
        })
    return s


# ─────────────────────── view share CRUD ───────────────────────
async def _can_manage_view(db, ctx: AuthContext, view: dict) -> bool:
    if ctx.role in ("owner", "admin"):
        return True
    if view.get("user_id") == ctx.user["_id"]:
        return True
    # collaborators with edit permission
    for c in (view.get("shared_with") or []):
        if c.get("user_id") == ctx.user["_id"] and c.get("permission") == "edit":
            return True
    return False


async def _load_view(db, ctx: AuthContext, view_id: str) -> dict:
    v = await db.views.find_one({"_id": view_id, "org_id": ctx.org_id, "deleted_at": None})
    if not v:
        raise HTTPException(404, "view not found")
    return v


@router.get("/views/{vid}/shares")
async def list_view_shares(
    vid: str, ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    await _load_view(db, ctx, vid)  # 404 if not accessible
    cursor = db.share_links.find({
        "org_id": ctx.org_id, "kind": "view", "view_id": vid,
    }).sort("created_at", -1)
    return [_serialize_view_share(d) for d in await cursor.to_list(200)]


@router.post("/views/{vid}/shares", status_code=201)
async def create_view_share(
    vid: str, body: ViewShareCreate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    v = await _load_view(db, ctx, vid)
    if not await _can_manage_view(db, ctx, v):
        raise HTTPException(403, "you do not have permission to share this view")
    if body.visibility == "password" and not body.password:
        raise HTTPException(422, {"code": "password_required",
                                   "detail": "A password is required for password-protected shares."})
    token = secrets.token_urlsafe(24)
    doc = {
        "_id": str(uuid.uuid4()),
        "org_id": ctx.org_id,
        "kind": "view",
        "view_id": vid,
        "record_id": None,
        "token": token,
        "visibility": body.visibility,
        "visible_columns": body.visible_columns,
        "visible_fields": None,  # not used for kind=view
        "include_media": bool(body.include_media),
        "include_relationships": bool(body.include_relationships),
        "expires_at": body.expires_at.isoformat() if body.expires_at else None,
        "password_hash": _hash_password(body.password) if body.password and body.visibility == "password" else None,
        "revoked_at": None,
        "view_count": 0,
        "last_viewed_at": None,
        "created_by": ctx.user["_id"],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.share_links.insert_one(doc)
    audit(bg, action="view.shared_public", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="view", target_id=vid,
          diff={"share_id": doc["_id"], "visibility": body.visibility}, request=request)
    if body.password and body.visibility == "password":
        audit(bg, action="share.password_set", actor_id=ctx.user["_id"], org_id=ctx.org_id,
              target_type="share", target_id=doc["_id"], request=request)
    return _serialize_view_share(doc)


@router.patch("/view-shares/{sid}")
async def update_view_share(
    sid: str, body: ViewShareUpdate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    doc = await db.share_links.find_one({"_id": sid, "org_id": ctx.org_id, "kind": "view"})
    if not doc:
        raise HTTPException(404, "view share not found")
    v = await db.views.find_one({"_id": doc["view_id"], "org_id": ctx.org_id})
    if not v or not await _can_manage_view(db, ctx, v):
        raise HTTPException(403, "cannot manage this view share")
    raw = body.model_dump(exclude_unset=True)
    password = raw.pop("password", None)
    updates = dict(raw)
    if "expires_at" in updates and updates["expires_at"]:
        updates["expires_at"] = updates["expires_at"].isoformat() \
            if isinstance(updates["expires_at"], datetime) else updates["expires_at"]
    target_vis = updates.get("visibility", doc.get("visibility"))
    if password is not None:
        if target_vis != "password":
            raise HTTPException(422, "password only allowed when visibility='password'")
        updates["password_hash"] = _hash_password(password)
    elif "visibility" in updates and updates["visibility"] == "password" and not doc.get("password_hash"):
        raise HTTPException(422, {"code": "password_required",
                                   "detail": "Set a password when switching to password visibility."})
    elif "visibility" in updates and updates["visibility"] != "password":
        updates["password_hash"] = None
    updates["updated_at"] = _now_iso()
    await db.share_links.update_one({"_id": sid}, {"$set": updates})
    fresh = await db.share_links.find_one({"_id": sid})
    audit(bg, action="share.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="share", target_id=sid,
          diff={k: v for k, v in updates.items() if k != "password_hash"},
          request=request)
    if password is not None:
        audit(bg, action="share.password_changed", actor_id=ctx.user["_id"],
              org_id=ctx.org_id, target_type="share", target_id=sid, request=request)
    return _serialize_view_share(fresh)


# ─────────────────────── public view endpoints ───────────────────────
async def _apply_view_share_gate(db, share: dict, ctx, request):
    v = share["visibility"]
    if v == "private":
        if not ctx or ctx.org_id != share["org_id"]:
            raise HTTPException(401, "authentication required for this share")
    elif v == "org_only":
        if not ctx or ctx.org_id != share["org_id"]:
            raise HTTPException(401, "authentication in the owning org required")
    elif v == "password":
        if not (ctx and ctx.org_id == share["org_id"]):
            _check_password_gate(share, request)


async def _resolve_visible_columns(view: dict, share: dict, field_defs: list[dict]) -> list[dict]:
    """Compute the columns to expose. Sensitive fields always stripped."""
    def _is_sensitive(fd: dict) -> bool:
        return bool(fd.get("sensitive")) or bool((fd.get("config") or {}).get("sensitive"))

    non_sensitive_by_key = {f["key"]: f for f in field_defs if not _is_sensitive(f)}
    requested = share.get("visible_columns")
    if requested is None:
        requested = view.get("visible_fields") or []
    if not requested:
        # If neither set, expose all non-sensitive
        allowed = list(non_sensitive_by_key.values())
    else:
        allowed = [non_sensitive_by_key[k] for k in requested if k in non_sensitive_by_key]

    # Preserve field metadata but strip internal ids
    cols = []
    for fd in allowed:
        cols.append({
            "field_key": fd["key"],
            "label": fd.get("label") or fd["key"],
            "type": fd.get("type"),
        })
    return cols


@router.get("/public/views/{token}")
async def public_view(
    token: str, request: Request, bg: BackgroundTasks,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    q: str | None = Query(default=None),
    ctx: AuthContext | None = Depends(try_auth),
):
    _check_rate(f"pub_view:{_client_ip(request)}", per_minute=_READ_PER_MIN)
    db = get_db()
    share = await _load_share_view(db, token)
    await _apply_view_share_gate(db, share, ctx, request)

    org = await db.organizations.find_one(
        {"_id": share["org_id"], "deleted_at": None},
        {"name": 1, "settings": 1},
    )
    if not org:
        raise HTTPException(410, {"code": "org_gone",
                                   "detail": "This workspace is no longer available."})

    view = await db.views.find_one({
        "_id": share["view_id"], "org_id": share["org_id"], "deleted_at": None,
    })
    if not view:
        raise HTTPException(404, {"code": "view_deleted",
                                   "detail": "The saved view no longer exists."})

    et = await db.entity_types.find_one({
        "_id": view["entity_type_id"], "org_id": share["org_id"], "deleted_at": None,
    })
    if not et:
        raise HTTPException(404, {"code": "entity_type_gone",
                                   "detail": "The entity type behind this view no longer exists."})

    field_defs = await db.field_definitions.find(
        tenant_filter(share["org_id"], {"entity_type_id": view["entity_type_id"]}),
    ).sort("order", 1).to_list(1000)
    visible_columns = await _resolve_visible_columns(view, share, field_defs)
    non_sensitive_keys = {c["field_key"] for c in visible_columns}

    # Build query from view state (viewer treats share as "public viewer")
    base = tenant_filter(share["org_id"], {"entity_type_id": view["entity_type_id"]})
    view_q = q or view.get("q")
    if view_q:
        base["$text"] = {"$search": view_q}
    view_cats = view.get("category_ids") or []
    if view_cats:
        cat_ids = await descendant_ids_including_self(
            db, org_id=share["org_id"], entity_type_id=view["entity_type_id"],
            cat_id=view_cats[0],
        )
        base["category_ids"] = {"$in": cat_ids} if cat_ids else view_cats[0]
    if view.get("tag_ids"):
        base["tag_ids"] = {"$in": view["tag_ids"]}
    filters = view.get("filters") or []
    if filters:
        defs_by_key = {d["key"]: d for d in field_defs}
        extra = build_filter_query(filters, defs_by_key)
        if extra:
            base = {"$and": [base, extra]}

    sort_spec = build_sort_spec(view.get("sort") or [])

    # cursor pagination
    try:
        skip = int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()) if cursor else 0
    except Exception:
        skip = 0

    total = await db.records.count_documents(base)
    cur = db.records.find(base).sort(sort_spec).skip(skip).limit(limit)
    docs = await cur.to_list(limit)
    next_cursor = None
    if skip + len(docs) < total:
        next_cursor = base64.urlsafe_b64encode(str(skip + limit).encode()).decode().rstrip("=")

    # Build records payload
    records_out = []
    rec_ids = [d["_id"] for d in docs]

    # Categories + tags in one shot
    cats_map = {}
    tags_map = {}
    all_cat_ids = list({cid for d in docs for cid in (d.get("category_ids") or [])})
    all_tag_ids = list({tid for d in docs for tid in (d.get("tag_ids") or [])})
    if all_cat_ids:
        cs = await db.categories.find(
            tenant_filter(share["org_id"], {"_id": {"$in": all_cat_ids}}),
            {"name": 1, "path_names": 1, "color": 1},
        ).to_list(500)
        cats_map = {c["_id"]: c for c in cs}
    if all_tag_ids:
        ts = await db.tags.find(
            tenant_filter(share["org_id"], {"_id": {"$in": all_tag_ids}}),
            {"name": 1, "color": 1},
        ).to_list(500)
        tags_map = {t["_id"]: t for t in ts}

    # Media hydration if included
    media_by_record: dict[str, list] = {}
    if share.get("include_media") and rec_ids:
        media_docs = await db.media.find({
            "org_id": share["org_id"], "deleted_at": None,
            "attached_to.record_id": {"$in": rec_ids},
        }, {"filename": 1, "mime": 1, "size": 1, "attached_to": 1}).to_list(2000)
        for m in media_docs:
            for a in (m.get("attached_to") or []):
                rid = a.get("record_id")
                if rid in rec_ids:
                    media_by_record.setdefault(rid, []).append({
                        "id": m["_id"], "filename": m["filename"],
                        "mime": m["mime"], "size": m["size"],
                    })

    for d in docs:
        row_fields = {k: (d.get("fields") or {}).get(k) for k in non_sensitive_keys}
        rec_out = {
            "id": d["_id"],
            "title": d.get("title"),
            "record_number": d.get("record_number"),
            "updated_at": d.get("updated_at"),
            "fields": row_fields,
            "category_paths": [
                cats_map[cid].get("path_names") for cid in (d.get("category_ids") or [])
                if cid in cats_map
            ],
            "tags": [
                {"id": tid, "name": tags_map[tid].get("name"), "color": tags_map[tid].get("color")}
                for tid in (d.get("tag_ids") or []) if tid in tags_map
            ],
            "media": media_by_record.get(d["_id"], []),
        }
        records_out.append(rec_out)

    # Record view for the share
    async def _bump():
        await db.share_links.update_one(
            {"_id": share["_id"]},
            {"$inc": {"view_count": 1}, "$set": {"last_viewed_at": _now_iso()}},
        )
    bg.add_task(_bump)

    return {
        "view": {
            "id": view["_id"],
            "name": view.get("name"),
            "description": view.get("description"),
            "layout": view.get("layout") or "table",
            "entity_type_name": et.get("name_plural") or et.get("name_singular"),
            "entity_type_icon": et.get("icon"),
            "entity_type_color": et.get("color"),
            "org_name": org.get("name"),
            "visible_columns": visible_columns,
        },
        "records": records_out,
        "pagination": {"total": total, "cursor": cursor, "next_cursor": next_cursor, "limit": limit},
        "share": {
            "token": share["token"],
            "visibility": share["visibility"],
            "include_media": share.get("include_media", False),
            "include_relationships": share.get("include_relationships", False),
            "expires_at": share.get("expires_at"),
        },
        "meta": {"generated_at": _now_iso()},
    }


@router.get("/public/views/{token}/records/{record_id}")
async def public_view_record(
    token: str, record_id: str, request: Request, bg: BackgroundTasks,
    ctx: AuthContext | None = Depends(try_auth),
):
    _check_rate(f"pub_view_r:{_client_ip(request)}", per_minute=_READ_PER_MIN)
    db = get_db()
    share = await _load_share_view(db, token)
    await _apply_view_share_gate(db, share, ctx, request)

    view = await db.views.find_one({
        "_id": share["view_id"], "org_id": share["org_id"], "deleted_at": None,
    })
    if not view:
        raise HTTPException(404, "view no longer exists")

    rec = await db.records.find_one({
        "_id": record_id, "org_id": share["org_id"],
        "entity_type_id": view["entity_type_id"], "deleted_at": None,
    })
    if not rec:
        raise HTTPException(404, "record not found in this view")

    field_defs = await db.field_definitions.find(
        tenant_filter(share["org_id"], {"entity_type_id": view["entity_type_id"]}),
    ).sort("order", 1).to_list(1000)
    visible_columns = await _resolve_visible_columns(view, share, field_defs)
    non_sensitive_keys = {c["field_key"] for c in visible_columns}

    # Media (only if included on share)
    media = []
    if share.get("include_media"):
        media_docs = await db.media.find({
            "org_id": share["org_id"], "deleted_at": None,
            "attached_to.record_id": record_id,
        }, {"filename": 1, "mime": 1, "size": 1}).to_list(200)
        media = [{"id": m["_id"], "filename": m["filename"],
                  "mime": m["mime"], "size": m["size"]} for m in media_docs]

    field_defs_out = [
        {"key": fd["key"], "label": fd.get("label"), "type": fd.get("type")}
        for fd in field_defs if fd["key"] in non_sensitive_keys
    ]

    return {
        "record": {
            "id": rec["_id"],
            "title": rec.get("title"),
            "record_number": rec.get("record_number"),
            "updated_at": rec.get("updated_at"),
            "fields": {k: (rec.get("fields") or {}).get(k) for k in non_sensitive_keys},
        },
        "field_defs": field_defs_out,
        "media": media,
        "share": {
            "token": share["token"],
            "visibility": share["visibility"],
            "include_media": share.get("include_media", False),
        },
        "view": {"id": view["_id"], "name": view.get("name")},
    }


@router.post("/public/views/{token}/unlock")
async def public_view_unlock(
    token: str, body: UnlockBody, request: Request, response: Response,
    bg: BackgroundTasks,
):
    """Verify the password and set an unlock cookie for a view share."""
    ip = _client_ip(request)
    db = get_db()
    share = await _load_share_view(db, token)
    if share.get("visibility") != "password" or not share.get("password_hash"):
        raise HTTPException(404, "share not found")

    key = f"unlock:{ip}:{share['_id']}"
    now = time.time()
    hits = _RL[key]
    cutoff = now - _UNLOCK_ATTEMPT_WINDOW
    while hits and hits[0] < cutoff:
        hits.pop(0)
    if len(hits) >= _UNLOCK_ATTEMPT_LIMIT:
        retry_after = int(_UNLOCK_ATTEMPT_WINDOW - (now - hits[0])) + 1
        raise HTTPException(429, {
            "code": "too_many_attempts",
            "detail": "Too many attempts. Please wait a minute and try again.",
            "retry_after": retry_after,
        })

    if not _verify_password(body.password, share["password_hash"]):
        hits.append(now)
        audit(bg, action="share.unlock_attempt_failed",
              actor_id=None, org_id=share["org_id"],
              target_type="share", target_id=share["_id"], request=request)
        raise HTTPException(401, {
            "code": "invalid_password",
            "detail": "Incorrect password.",
            "attempts_remaining": max(0, _UNLOCK_ATTEMPT_LIMIT - len(hits)),
        })

    _RL.pop(key, None)
    signed = _sign_unlock(share["_id"], share["password_hash"])
    response.set_cookie(
        key=_unlock_cookie_name(token),
        value=signed,
        max_age=_UNLOCK_TTL_SEC,
        httponly=True,
        secure=True,
        samesite="lax",
        path=f"/api/public/views/{token}",
    )
    audit(bg, action="share.unlock_success", actor_id=None, org_id=share["org_id"],
          target_type="share", target_id=share["_id"], request=request)
    return {"unlocked": True, "expires_in": _UNLOCK_TTL_SEC}


# ─────────────────────── internal collaborators ───────────────────────
@router.get("/views/{vid}/collaborators")
async def list_collaborators(
    vid: str, ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    v = await _load_view(db, ctx, vid)
    collabs = v.get("shared_with") or []
    if not collabs:
        return []
    uids = [c["user_id"] for c in collabs]
    users = {u["_id"]: u for u in
             await db.users.find({"_id": {"$in": uids}},
                                  {"name": 1, "email": 1, "avatar_url": 1}).to_list(len(uids))}
    return [
        {
            **c,
            "user": {
                "id": u.get("_id") or c["user_id"],
                "name": (u or {}).get("name"),
                "email": (u or {}).get("email"),
                "avatar_url": (u or {}).get("avatar_url"),
            },
        }
        for c in collabs
        for u in [users.get(c["user_id"], {})]
    ]


@router.post("/views/{vid}/collaborators", status_code=201)
async def add_collaborator(
    vid: str, body: CollaboratorAdd,
    bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    v = await _load_view(db, ctx, vid)
    if not await _can_manage_view(db, ctx, v):
        raise HTTPException(403, "you do not have permission to modify collaborators")

    # target must be a member of the same org
    m = await db.memberships.find_one({
        "user_id": body.user_id, "org_id": ctx.org_id, "status": "active",
    })
    if not m:
        raise HTTPException(400, "user is not a member of this org")

    # No-op if already there — update permission if different
    existing = [c for c in (v.get("shared_with") or []) if c["user_id"] == body.user_id]
    now = _now_iso()
    if existing:
        await db.views.update_one(
            {"_id": vid, "shared_with.user_id": body.user_id},
            {"$set": {"shared_with.$.permission": body.permission,
                      "shared_with.$.added_at": now, "shared_with.$.added_by": ctx.user["_id"],
                      "updated_at": now}},
        )
    else:
        await db.views.update_one(
            {"_id": vid},
            {"$push": {"shared_with": {
                "user_id": body.user_id,
                "permission": body.permission,
                "added_at": now,
                "added_by": ctx.user["_id"],
            }}, "$set": {"updated_at": now}},
        )
    audit(bg, action="view.shared_internal", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="view", target_id=vid,
          diff={"user_id": body.user_id, "permission": body.permission}, request=request)

    fresh = await db.views.find_one({"_id": vid})
    return {"ok": True, "collaborators": fresh.get("shared_with", [])}


@router.patch("/views/{vid}/collaborators/{user_id}")
async def update_collaborator(
    vid: str, user_id: str, body: CollaboratorUpdate,
    bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    v = await _load_view(db, ctx, vid)
    if not await _can_manage_view(db, ctx, v):
        raise HTTPException(403, "cannot modify collaborators")
    if not any(c["user_id"] == user_id for c in (v.get("shared_with") or [])):
        raise HTTPException(404, "collaborator not found")
    now = _now_iso()
    await db.views.update_one(
        {"_id": vid, "shared_with.user_id": user_id},
        {"$set": {"shared_with.$.permission": body.permission, "updated_at": now}},
    )
    audit(bg, action="view.shared_internal", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="view", target_id=vid,
          diff={"user_id": user_id, "permission": body.permission}, request=request)
    fresh = await db.views.find_one({"_id": vid})
    return {"ok": True, "collaborators": fresh.get("shared_with", [])}


@router.delete("/views/{vid}/collaborators/{user_id}", status_code=204)
async def remove_collaborator(
    vid: str, user_id: str,
    bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    v = await _load_view(db, ctx, vid)
    if not await _can_manage_view(db, ctx, v):
        raise HTTPException(403, "cannot modify collaborators")
    now = _now_iso()
    await db.views.update_one(
        {"_id": vid},
        {"$pull": {"shared_with": {"user_id": user_id}},
         "$set": {"updated_at": now}},
    )
    audit(bg, action="view.access_revoked", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="view", target_id=vid,
          diff={"user_id": user_id}, request=request)
    return None
