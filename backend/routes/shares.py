"""Share links: CRUD + public read/media/qr/barcode endpoints."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

import bcrypt
from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Query, Request
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


# ---------------- Password / unlock helpers ----------------
_UNLOCK_TTL_SEC = 30 * 60  # 30 min sliding window
_UNLOCK_ATTEMPT_LIMIT = 5
_UNLOCK_ATTEMPT_WINDOW = 60  # seconds


def _cookie_secret() -> bytes:
    s = os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY")
    if not s:
        raise HTTPException(500, "server missing signing secret")
    return s.encode("utf-8")


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt(10)).decode("utf-8")


def _verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _hash_hint(password_hash: str) -> str:
    """Short deterministic hint of the current password hash; embedded in the
    unlock cookie so it becomes invalid the moment the password is rotated."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def _sign_unlock(share_id: str, password_hash: str, ttl: int = _UNLOCK_TTL_SEC) -> str:
    exp = int(time.time()) + ttl
    payload = f"{share_id}.{exp}.{_hash_hint(password_hash)}"
    sig = hmac.new(_cookie_secret(), payload.encode(), hashlib.sha256).digest()
    return payload + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def _verify_unlock(cookie_val: str, share_id: str, password_hash: str) -> bool:
    if not cookie_val:
        return False
    try:
        sid, exp_s, hint, sig_b64 = cookie_val.rsplit(".", 3)
    except ValueError:
        return False
    if sid != share_id or hint != _hash_hint(password_hash):
        return False
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < int(time.time()):
        return False
    payload = f"{sid}.{exp_s}.{hint}".encode()
    expected = hmac.new(_cookie_secret(), payload, hashlib.sha256).digest()
    pad = "=" * (-len(sig_b64) % 4)
    try:
        given = base64.urlsafe_b64decode(sig_b64 + pad)
    except Exception:
        return False
    return hmac.compare_digest(expected, given)


def _unlock_cookie_name(token: str) -> str:
    # Path-scoped, share-specific — one cookie per share the visitor unlocks.
    return f"share_unlock_{token}"


def _public_base() -> str:
    return (os.environ.get("PUBLIC_APP_URL") or os.environ.get("APP_BASE_URL") or "").rstrip("/")


# ---------------- Simple in-memory rate limiter (per-IP+route) ----------------
_RL: dict[str, list[float]] = defaultdict(list)


def _parse_rate(spec: str, default_per_min: int) -> int:
    """Parse '60/min' | '30/min' → int per-minute. Falls back on parse error."""
    try:
        n, _ = spec.split("/", 1)
        return max(1, int(n.strip()))
    except Exception:
        return default_per_min


_READ_PER_MIN = _parse_rate(os.environ.get("PUBLIC_READ_RATE_LIMIT", "60/min"), 60)
_CODE_PER_MIN = _parse_rate(os.environ.get("PUBLIC_CODE_RATE_LIMIT", "30/min"), 30)


def _check_rate(key: str, per_minute: int) -> None:
    now = time.time()
    hits = _RL[key]
    cutoff = now - 60.0
    while hits and hits[0] < cutoff:
        hits.pop(0)
    if len(hits) >= per_minute:
        raise HTTPException(429, {"code": "rate_limited", "detail": "Too many requests"})
    hits.append(now)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ---------------- Models ----------------
_VISIBILITY = Literal["private", "org_only", "public", "password"]


class ShareCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    visibility: _VISIBILITY = "public"
    visible_fields: list[str] | None = None
    include_media: bool = True
    include_relationships: bool = False
    expires_at: datetime | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class ShareUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    visibility: _VISIBILITY | None = None
    visible_fields: list[str] | None = None
    include_media: bool | None = None
    include_relationships: bool | None = None
    expires_at: datetime | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UnlockBody(BaseModel):
    password: str = Field(min_length=1, max_length=128)


def _serialize_share(doc: dict) -> dict:
    d = strip_id(doc)
    # Never leak the hash
    d.pop("password_hash", None)
    d["has_password"] = bool(doc.get("password_hash"))
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
    if body.visibility == "password" and not body.password:
        raise HTTPException(422, {"code": "password_required",
                                   "detail": "A password is required for password-protected shares."})
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
        "password_hash": _hash_password(body.password) if body.password and body.visibility == "password" else None,
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
    if body.password and body.visibility == "password":
        audit(bg, action="share.password_set", actor_id=ctx.user["_id"], org_id=ctx.org_id,
              target_type="share", target_id=doc["_id"], request=request)
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
    raw = body.model_dump(exclude_unset=True)
    password = raw.pop("password", None)
    updates = dict(raw)
    if "expires_at" in updates and updates["expires_at"]:
        updates["expires_at"] = updates["expires_at"].isoformat() \
            if isinstance(updates["expires_at"], datetime) else updates["expires_at"]
    # Password lifecycle
    target_vis = updates.get("visibility", doc.get("visibility"))
    if password is not None:
        if target_vis != "password":
            raise HTTPException(422, "password only allowed when visibility='password'")
        updates["password_hash"] = _hash_password(password)
    elif "visibility" in updates and updates["visibility"] == "password" and not doc.get("password_hash"):
        raise HTTPException(422, {"code": "password_required",
                                   "detail": "Set a password when switching to password visibility."})
    elif "visibility" in updates and updates["visibility"] != "password":
        # Switching away from password protection — drop the hash
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

    # Org must exist and not be soft-deleted (→ 410, org gone).
    org = await db.organizations.find_one(
        {"_id": org_id, "deleted_at": None},
        {"name": 1, "settings": 1},
    )
    if not org:
        raise HTTPException(status_code=410, detail={
            "code": "org_gone", "detail": "This workspace is no longer available.",
        })

    rec = await db.records.find_one(tenant_filter(org_id, {"_id": share["record_id"]}))
    if not rec:
        raise HTTPException(404, "record not found")

    field_defs = await db.field_definitions.find(
        tenant_filter(org_id, {"entity_type_id": rec["entity_type_id"]}),
    ).sort("order", 1).to_list(1000)

    # Sensitive fields are always stripped in public share payloads.
    # Support both top-level `sensitive: True` (Phase 4) and legacy
    # `config.sensitive` for forward compat.
    def _is_sensitive(fd: dict) -> bool:
        return bool(fd.get("sensitive")) or bool((fd.get("config") or {}).get("sensitive"))

    non_sensitive_keys = [f["key"] for f in field_defs if not _is_sensitive(f)]

    # visible_fields: None (or missing)  → all non-sensitive fields
    # visible_fields: []                 → title/record-number-only share
    # visible_fields: [k1, k2, …]        → intersect with non-sensitive
    vf = share.get("visible_fields")
    if vf is None:
        keys = non_sensitive_keys
    else:
        keys = [k for k in vf if k in non_sensitive_keys]

    fields_out = {k: rec.get("fields", {}).get(k) for k in keys}
    exposed_defs = [
        {k2: v for k2, v in fd.items()
         if k2 not in ("_id", "org_id", "entity_type_id", "sensitive")}
        for fd in field_defs if fd["key"] in keys
    ]

    org_settings = (org.get("settings") or {})
    support_email = org_settings.get("support_email") or None

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
        "org": {"name": org.get("name"), "id": org_id, "support_email": support_email},
        "share": {
            "token": share["token"],
            "visibility": share["visibility"],
            "include_media": share.get("include_media", True),
            "include_relationships": share.get("include_relationships", False),
            "expires_at": share.get("expires_at"),
            "created_at": share.get("created_at"),
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
def _check_password_gate(share: dict, request: Request) -> None:
    """Raise 401 password_required if the share is password-protected and the
    caller does not present a valid unlock cookie."""
    if share.get("visibility") != "password":
        return
    if not share.get("password_hash"):
        # Misconfigured — treat as inaccessible
        raise HTTPException(410, "share misconfigured")
    cookie_val = request.cookies.get(_unlock_cookie_name(share["token"]))
    if not _verify_unlock(cookie_val or "", share["_id"], share["password_hash"]):
        raise HTTPException(401, {
            "code": "password_required",
            "detail": "This share requires a password.",
        })


@router.get("/public/records/{token}")
async def public_get_record(
    token: str, request: Request, bg: BackgroundTasks,
    ctx: AuthContext | None = Depends(try_auth),
):
    _check_rate(f"pub_read:{_client_ip(request)}", per_minute=_READ_PER_MIN)
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
    elif v == "password":
        # Signed-in members of the owning org bypass the password prompt.
        if not (ctx and ctx.org_id == share["org_id"]):
            _check_password_gate(share, request)
    # public → no auth required

    payload = await _build_public_payload(db, share)
    await _record_view(db, share["_id"], bg)
    return payload


@router.post("/public/records/{token}/unlock")
async def public_unlock_record(
    token: str, body: UnlockBody, request: Request, response: Response,
    bg: BackgroundTasks,
):
    """Verify the password and set an unlock cookie."""
    ip = _client_ip(request)
    db = get_db()
    share = await _load_share(db, token)
    if share.get("visibility") != "password" or not share.get("password_hash"):
        # Do not disclose whether the share exists
        raise HTTPException(404, "share not found")

    # 5 wrong-password attempts per (IP, share) per 60 s → 429 with retry-after
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
        # Do not reveal whether a share exists; generic message
        raise HTTPException(401, {
            "code": "invalid_password",
            "detail": "Incorrect password.",
            "attempts_remaining": max(0, _UNLOCK_ATTEMPT_LIMIT - len(hits)),
        })

    # Success — reset the bucket + issue cookie
    _RL.pop(key, None)
    signed = _sign_unlock(share["_id"], share["password_hash"])
    response.set_cookie(
        key=_unlock_cookie_name(token),
        value=signed,
        max_age=_UNLOCK_TTL_SEC,
        httponly=True,
        secure=True,
        samesite="lax",
        path=f"/api/public/records/{token}",
    )
    audit(bg, action="share.unlock_success", actor_id=None, org_id=share["org_id"],
          target_type="share", target_id=share["_id"], request=request)
    return {"unlocked": True, "expires_in": _UNLOCK_TTL_SEC}


@router.get("/public/records/{token}/media/{media_id}")
async def public_serve_shared_media(
    token: str, media_id: str, request: Request,
    ctx: AuthContext | None = Depends(try_auth),
):
    _check_rate(f"pub_media:{_client_ip(request)}", per_minute=_READ_PER_MIN)
    db = get_db()
    share = await _load_share(db, token)
    v = share["visibility"]
    if v in ("private", "org_only"):
        if not ctx or ctx.org_id != share["org_id"]:
            raise HTTPException(401, "authentication required")
    elif v == "password":
        if not (ctx and ctx.org_id == share["org_id"]):
            _check_password_gate(share, request)
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
    ctx: AuthContext | None = Depends(try_auth),
):
    _check_rate(f"pub_qr:{_client_ip(request)}", per_minute=_CODE_PER_MIN)
    db = get_db()
    share = await _load_share(db, token)
    v = share["visibility"]
    if v == "password":
        if not (ctx and ctx.org_id == share["org_id"]):
            _check_password_gate(share, request)
    elif v != "public":
        if not (ctx and ctx.org_id == share["org_id"]):
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
    ctx: AuthContext | None = Depends(try_auth),
):
    _check_rate(f"pub_bc:{_client_ip(request)}", per_minute=_CODE_PER_MIN)
    db = get_db()
    share = await _load_share(db, token)
    v = share["visibility"]
    if v == "password":
        if not (ctx and ctx.org_id == share["org_id"]):
            _check_password_gate(share, request)
    elif v != "public":
        if not (ctx and ctx.org_id == share["org_id"]):
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
