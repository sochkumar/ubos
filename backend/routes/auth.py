"""Authentication endpoints: register, login, refresh, logout, me,
forgot/reset password, change password."""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from audit import audit
from auth_deps import get_current_user
from core.email import get_email_provider
from core.email.templates import password_reset_email
from db import get_db
from models import (
    ChangePassword,
    ForgotPassword,
    RefreshPayload,
    ResetPassword,
    UserLogin,
    UserRegister,
    strip_id,
)
from security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    permissions_for_role,
    sha256_hex,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("ubos.auth")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _resolve_role_and_perms(db, *, user_id: str, org_id: str | None) -> tuple[str | None, list[str]]:
    if not org_id:
        return None, []
    m = await db.memberships.find_one(
        {"user_id": user_id, "org_id": org_id, "status": "active"}
    )
    if not m:
        return None, []
    return m.get("role_name"), permissions_for_role(m.get("role_name") or "viewer")


async def _issue_tokens(db, user: dict, org_id: str | None) -> dict:
    role, perms = await _resolve_role_and_perms(db, user_id=user["_id"], org_id=org_id)
    access, access_exp = create_access_token(
        user_id=user["_id"], org_id=org_id, role=role, permissions=perms
    )
    refresh, refresh_exp, refresh_hash = create_refresh_token(user_id=user["_id"])
    await db.refresh_tokens.insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": user["_id"],
        "token_hash": refresh_hash,
        "expires_at": refresh_exp,
        "revoked_at": None,
        "created_at": _iso(_now_dt()),
    })
    return {
        "access_token": access,
        "refresh_token": refresh,
        "access_expires_at": _iso(access_exp),
        "refresh_expires_at": _iso(refresh_exp),
        "token_type": "Bearer",
        "user": strip_id(user),
        "org_id": org_id,
        "role": role,
        "permissions": perms,
    }


# ─────────────────────── register ───────────────────────
@router.post("/register", status_code=201)
async def register(
    payload: UserRegister, bg: BackgroundTasks, request: Request
):
    db = get_db()
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="email already registered")
    now = _iso(_now_dt())
    user = {
        "_id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(payload.password),
        "name": payload.name.strip(),
        "avatar_url": None,
        "google_sub": None,
        "default_org_id": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.users.insert_one(user)
    audit(bg, action="user.registered", actor_id=user["_id"], target_type="user",
          target_id=user["_id"], request=request)
    tokens = await _issue_tokens(db, user, org_id=None)
    return tokens


# ─────────────────────── login ───────────────────────
async def _lockout_key(email: str, request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}:{email}"


async def _check_lockout(db, ident: str) -> None:
    doc = await db.login_attempts.find_one({"_id": ident})
    if not doc:
        return
    if doc.get("count", 0) >= MAX_FAILED_ATTEMPTS:
        exp = doc.get("expires_at")
        if isinstance(exp, datetime) and exp > _now_dt():
            retry_after = max(1, int((exp - _now_dt()).total_seconds()))
            raise HTTPException(
                status_code=429,
                detail="too many failed attempts — try again later",
                headers={"Retry-After": str(retry_after)},
            )


async def _record_failure(db, ident: str) -> None:
    now = _now_dt()
    exp = now + timedelta(minutes=LOCKOUT_MINUTES)
    await db.login_attempts.update_one(
        {"_id": ident},
        {"$inc": {"count": 1}, "$set": {"expires_at": exp, "updated_at": _iso(now)}},
        upsert=True,
    )


async def _clear_failures(db, ident: str) -> None:
    await db.login_attempts.delete_one({"_id": ident})


@router.post("/login")
async def login(
    payload: UserLogin, bg: BackgroundTasks, request: Request
):
    db = get_db()
    email = payload.email.lower().strip()
    ident = await _lockout_key(email, request)
    await _check_lockout(db, ident)

    user = await db.users.find_one({"email": email, "is_active": True})
    ok = user and verify_password(payload.password, user.get("password_hash"))
    if not ok:
        await _record_failure(db, ident)
        raise HTTPException(status_code=401, detail="invalid email or password")

    await _clear_failures(db, ident)
    audit(bg, action="user.logged_in", actor_id=user["_id"], target_type="user",
          target_id=user["_id"], request=request)
    return await _issue_tokens(db, user, org_id=user.get("default_org_id"))


# ─────────────────────── refresh (with rotation) ───────────────────────
@router.post("/refresh")
async def refresh(payload: RefreshPayload):
    db = get_db()
    try:
        data = decode_token(payload.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid or expired refresh token")
    if data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="wrong token type")

    token_hash = sha256_hex(payload.refresh_token)
    existing = await db.refresh_tokens.find_one({"token_hash": token_hash})
    if not existing or existing.get("revoked_at"):
        raise HTTPException(status_code=401, detail="refresh token revoked or unknown")
    exp = existing.get("expires_at")
    if isinstance(exp, datetime) and exp < _now_dt():
        raise HTTPException(status_code=401, detail="refresh token expired")

    user = await db.users.find_one({"_id": data["sub"], "is_active": True})
    if not user:
        raise HTTPException(status_code=401, detail="user not found or disabled")

    # rotate: revoke old, issue new
    await db.refresh_tokens.update_one(
        {"_id": existing["_id"]},
        {"$set": {"revoked_at": _iso(_now_dt())}},
    )
    return await _issue_tokens(db, user, org_id=user.get("default_org_id"))


# ─────────────────────── logout ───────────────────────
@router.post("/logout", status_code=204)
async def logout(
    payload: RefreshPayload | None = None,
    bg: BackgroundTasks = None,
    request: Request = None,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    if payload and payload.refresh_token:
        await db.refresh_tokens.update_one(
            {"token_hash": sha256_hex(payload.refresh_token)},
            {"$set": {"revoked_at": _iso(_now_dt())}},
        )
    audit(bg, action="user.logged_out", actor_id=user["_id"], target_type="user",
          target_id=user["_id"], request=request)
    return None


# ─────────────────────── me ───────────────────────
@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    db = get_db()
    memberships = await db.memberships.find(
        {"user_id": user["_id"], "status": "active"}
    ).to_list(100)
    orgs = []
    if memberships:
        org_ids = [m["org_id"] for m in memberships]
        docs = await db.organizations.find(
            {"_id": {"$in": org_ids}, "deleted_at": None}
        ).to_list(100)
        role_by_org = {m["org_id"]: m.get("role_name") for m in memberships}
        for d in docs:
            orgs.append({**strip_id(d), "role": role_by_org.get(d["_id"])})
    return {
        "user": strip_id(user),
        "organizations": orgs,
        "default_org_id": user.get("default_org_id"),
    }


# ─────────────────────── forgot / reset ───────────────────────
@router.post("/forgot-password")
async def forgot_password(
    payload: ForgotPassword, bg: BackgroundTasks, request: Request
):
    db = get_db()
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email, "is_active": True})
    reset_url = None
    provider_name = "dev"
    if user:
        raw = secrets.token_urlsafe(32)
        exp = _now_dt() + timedelta(hours=1)
        await db.password_reset_tokens.insert_one({
            "_id": str(uuid.uuid4()),
            "user_id": user["_id"],
            "token_hash": sha256_hex(raw),
            "expires_at": exp,
            "used_at": None,
            "created_at": _iso(_now_dt()),
        })
        origin = (os.environ.get("PUBLIC_APP_URL") or os.environ.get("APP_BASE_URL", "")).rstrip("/")
        reset_url = f"{origin}/reset-password?token={raw}" if origin else f"/reset-password?token={raw}"
        log.warning("[dev] password reset for %s → %s", email, reset_url)
        # Send via email factory
        try:
            provider = get_email_provider()
            subject, html, text = password_reset_email(reset_url=reset_url, expires_hours=1)
            result = await provider.send(
                to=email, subject=subject, html=html, text=text,
            )
            provider_name = result.provider
            action = "email.sent" if result.ok else "email.send_failed"
            audit(bg, action=action, actor_id=user["_id"], org_id=None,
                  target_type="user", target_id=user["_id"],
                  diff={"provider": result.provider, "purpose": "password_reset"}, request=request)
        except Exception as e:
            log.warning("password reset email send failed: %s", e)

    # Always return the same message so we don't leak account existence.
    # Include dev_reset_url only when provider is dev so it's not leaked in prod.
    return {
        "message": "If an account exists for that email, a reset link has been sent.",
        "dev_reset_url": reset_url if provider_name == "dev" else None,
        "email_provider": provider_name,
    }


@router.post("/reset-password")
async def reset_password(payload: ResetPassword, bg: BackgroundTasks, request: Request):
    db = get_db()
    doc = await db.password_reset_tokens.find_one(
        {"token_hash": sha256_hex(payload.token)}
    )
    if not doc or doc.get("used_at"):
        raise HTTPException(status_code=400, detail="invalid or already-used token")
    exp = doc.get("expires_at")
    if isinstance(exp, datetime) and exp < _now_dt():
        raise HTTPException(status_code=400, detail="reset token expired")
    await db.users.update_one(
        {"_id": doc["user_id"]},
        {"$set": {
            "password_hash": hash_password(payload.new_password),
            "updated_at": _iso(_now_dt()),
        }},
    )
    await db.password_reset_tokens.update_one(
        {"_id": doc["_id"]}, {"$set": {"used_at": _iso(_now_dt())}}
    )
    # revoke all refresh tokens
    await db.refresh_tokens.update_many(
        {"user_id": doc["user_id"], "revoked_at": None},
        {"$set": {"revoked_at": _iso(_now_dt())}},
    )
    audit(bg, action="user.password_changed", actor_id=doc["user_id"],
          target_type="user", target_id=doc["user_id"], request=request)
    return {"message": "password updated"}


@router.post("/change-password")
async def change_password(
    payload: ChangePassword,
    bg: BackgroundTasks,
    request: Request,
    user: dict = Depends(get_current_user),
):
    if not verify_password(payload.current, user.get("password_hash")):
        raise HTTPException(status_code=400, detail="current password is incorrect")
    db = get_db()
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "password_hash": hash_password(payload.new),
            "updated_at": _iso(_now_dt()),
        }},
    )
    audit(bg, action="user.password_changed", actor_id=user["_id"],
          target_type="user", target_id=user["_id"], request=request)
    return {"message": "password updated"}
