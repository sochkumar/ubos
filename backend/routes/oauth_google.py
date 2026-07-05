"""Google OAuth 2.0 endpoints (authlib), env-gated.

Flow:
  1. Frontend calls GET /api/auth/google/login?redirect_uri=<frontend>/auth/google/callback
     Backend stores state in oauth_states (10min TTL) and returns { url: <google-authorize-url> }.
  2. Google redirects the browser to `<redirect_uri>?code=...&state=...` (the FRONTEND callback page).
  3. Frontend callback page POSTs { code, state, redirect_uri } to /api/auth/google/exchange.
  4. Backend exchanges the code with Google, upserts user, issues our JWTs.

Redirect URI is provided by the frontend on every call — NEVER hardcoded, NEVER fallbacked.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from audit import audit
from db import get_db
from models import strip_id
from routes.auth import _issue_tokens

router = APIRouter(prefix="/auth/google", tags=["auth-google"])
log = logging.getLogger("ubos.oauth")

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def google_enabled() -> bool:
    cid = os.environ.get("GOOGLE_CLIENT_ID", "")
    csec = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    return bool(cid) and cid != "REPLACE_ME" and bool(csec) and csec != "REPLACE_ME"


@router.get("/status")
async def status():
    return {"enabled": google_enabled()}


@router.get("/login")
async def start_login(redirect_uri: str = Query(...)):
    if not google_enabled():
        raise HTTPException(status_code=503, detail="Google Sign-In not configured")
    if not redirect_uri.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="invalid redirect_uri")

    state = secrets.token_urlsafe(24)
    exp = _now_dt() + timedelta(minutes=10)
    await get_db().oauth_states.insert_one({
        "_id": state,
        "redirect_uri": redirect_uri,
        "expires_at": exp,
        "created_at": _iso(_now_dt()),
    })
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account",
    }
    return {"url": f"{AUTHORIZE_URL}?{urlencode(params)}", "state": state}


class _ExchangePayload:
    pass


from pydantic import BaseModel


class ExchangeIn(BaseModel):
    code: str
    state: str
    redirect_uri: str


@router.post("/exchange")
async def exchange(payload: ExchangeIn, bg: BackgroundTasks, request: Request):
    if not google_enabled():
        raise HTTPException(status_code=503, detail="Google Sign-In not configured")
    db = get_db()
    st = await db.oauth_states.find_one({"_id": payload.state})
    if not st:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    if st.get("redirect_uri") != payload.redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri mismatch")
    await db.oauth_states.delete_one({"_id": payload.state})

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_res = await client.post(
            TOKEN_URL,
            data={
                "code": payload.code,
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                "redirect_uri": payload.redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        if token_res.status_code >= 400:
            log.warning("Google token exchange failed: %s", token_res.text)
            raise HTTPException(status_code=400, detail="google token exchange failed")
        tk = token_res.json()
        access_token = tk.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="no access_token from google")

        info_res = await client.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
        )
        if info_res.status_code >= 400:
            raise HTTPException(status_code=400, detail="google userinfo failed")
        info = info_res.json()

    email = (info.get("email") or "").lower().strip()
    google_sub = info.get("sub")
    if not email or not google_sub:
        raise HTTPException(status_code=400, detail="google account missing email or sub")

    now = _iso(_now_dt())
    user = await db.users.find_one({"email": email})
    if user:
        upd = {"google_sub": google_sub, "updated_at": now}
        if info.get("picture") and not user.get("avatar_url"):
            upd["avatar_url"] = info["picture"]
        await db.users.update_one({"_id": user["_id"]}, {"$set": upd})
        user = {**user, **upd}
    else:
        user = {
            "_id": str(uuid.uuid4()),
            "email": email,
            "password_hash": None,
            "name": info.get("name") or email.split("@")[0],
            "avatar_url": info.get("picture"),
            "google_sub": google_sub,
            "default_org_id": None,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        await db.users.insert_one(user)
        audit(bg, action="user.registered", actor_id=user["_id"], target_type="user",
              target_id=user["_id"], diff={"provider": "google"}, request=request)

    audit(bg, action="user.logged_in", actor_id=user["_id"], target_type="user",
          target_id=user["_id"], diff={"provider": "google"}, request=request)
    return await _issue_tokens(db, user, org_id=user.get("default_org_id"))
