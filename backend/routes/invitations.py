"""User invitations — Phase 5-B.

Flow:
  1. Admin+ POSTs {emails, role, expiry} → per-email invitations created.
  2. Recipient clicks link → /api/invitations/:token (public) shows meta.
  3. Recipient signs in with matching email → POST /accept → membership created.

Rate limits: env INVITE_RATE_LIMIT_PER_HOUR per org.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from audit import audit
from auth_deps import AuthContext, get_current_user, require_permission
from core.email import get_email_provider
from core.email.templates import invitation_email
from db import get_db
from models import Email, strip_id
from routes._org_helpers import add_membership, get_membership

router = APIRouter(tags=["invitations"])
log = logging.getLogger("ubos.invitations")


ROLE_NAMES = Literal["admin", "editor", "viewer"]  # owner cannot be invited directly
INVITE_ROLE_NAMES = Literal["owner", "admin", "editor", "viewer"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _public_base() -> str:
    return (
        os.environ.get("PUBLIC_APP_URL")
        or os.environ.get("APP_BASE_URL")
        or ""
    ).rstrip("/")


def _accept_url(token: str) -> str:
    base = _public_base()
    return f"{base}/invitations/{token}/accept" if base else f"/invitations/{token}/accept"


# ---------- rate limit (per org, per hour) ----------
_RL: dict[str, list[float]] = defaultdict(list)


def _rate_limit_key(org_id: str) -> str:
    return f"invite:{org_id}"


def _check_rate_limit(org_id: str) -> None:
    limit = int(os.environ.get("INVITE_RATE_LIMIT_PER_HOUR", "20"))
    if limit <= 0:
        return
    now = time.time()
    hits = _RL[_rate_limit_key(org_id)]
    cutoff = now - 3600.0
    while hits and hits[0] < cutoff:
        hits.pop(0)
    if len(hits) >= limit:
        retry_after = max(1, int(3600 - (now - hits[0])) + 1)
        raise HTTPException(
            429,
            {"code": "invite_rate_limited",
             "detail": f"You've sent {limit} invitations in the past hour. Please wait.",
             "retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )
    hits.append(now)


# ---------- models ----------
class InvitationCreateBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: Email
    role_name: INVITE_ROLE_NAMES = "editor"
    expires_in_days: int | None = Field(default=7, ge=1, le=365)


class BatchInvitationBody(BaseModel):
    """Batch endpoint - accepts multiple emails."""
    model_config = ConfigDict(extra="ignore")
    emails: list[str] = Field(min_length=1, max_length=50)
    role_name: INVITE_ROLE_NAMES = "editor"
    expires_in_days: int | None = Field(default=7, ge=1, le=365)


class InvitationResendBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    expires_in_days: int | None = Field(default=7, ge=1, le=365)


# ---------- serialization ----------
async def _hydrate_invitation(db, inv: dict) -> dict:
    d = strip_id(inv)
    d["accept_url"] = _accept_url(inv["token"])
    # Hide the token in list responses unless caller is admin (accept_url still has it though)
    # We keep token in the doc for admins so they can copy paste links in dev mode.
    inviter_id = inv.get("invited_by")
    if inviter_id:
        u = await db.users.find_one({"_id": inviter_id}, {"name": 1, "email": 1})
        d["inviter"] = {"id": inviter_id, "name": (u or {}).get("name"), "email": (u or {}).get("email")}
    return d


async def _expire_if_needed(db, inv: dict) -> dict:
    if inv.get("status") != "pending":
        return inv
    exp = inv.get("expires_at")
    if exp:
        exp_dt = exp if isinstance(exp, datetime) else datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        if exp_dt < _now():
            await db.invitations.update_one(
                {"_id": inv["_id"]},
                {"$set": {"status": "expired", "updated_at": _iso(_now())}},
            )
            inv["status"] = "expired"
    return inv


# ---------- send email helper ----------
async def _send_invitation_email(
    db, invitation: dict, org: dict, inviter: dict, bg: BackgroundTasks | None
) -> dict:
    provider = get_email_provider()
    accept_url = _accept_url(invitation["token"])
    exp_str = "in 7 days"
    if invitation.get("expires_at"):
        try:
            exp_dt = invitation["expires_at"]
            if not isinstance(exp_dt, datetime):
                exp_dt = datetime.fromisoformat(str(exp_dt).replace("Z", "+00:00"))
            exp_str = exp_dt.strftime("%B %d, %Y")
        except Exception:
            pass
    subject, html, text = invitation_email(
        org_name=org.get("name", "an organization"),
        role_name=invitation["role_name"],
        inviter_name=(inviter.get("name") or inviter.get("email") or "A teammate"),
        invitee_email=invitation["email"],
        accept_url=accept_url,
        expires_at_readable=exp_str,
    )
    result = await provider.send(to=invitation["email"], subject=subject, html=html, text=text)
    now = _iso(_now())
    await db.invitations.update_one(
        {"_id": invitation["_id"]},
        {"$set": {
            "email_sent": result.ok,
            "email_provider": result.provider,
            "email_sent_at": now if result.ok else None,
            "email_message_id": result.message_id,
            "updated_at": now,
        }},
    )
    if bg is not None:
        action = "email.sent" if result.ok else "email.send_failed"
        audit(bg, action=action, actor_id=inviter["_id"], org_id=org["_id"],
              target_type="invitation", target_id=invitation["_id"],
              diff={"provider": result.provider, "email": invitation["email"]}, request=None)
    return {"provider": result.provider, "ok": result.ok, "message_id": result.message_id}


# ---------- create single ----------
async def _create_one_invitation(
    db, *, org_id: str, email: str, role_name: str,
    invited_by: str, expires_in_days: int, bg: BackgroundTasks | None, request: Request | None,
) -> dict:
    email = email.lower().strip()
    if role_name == "owner":
        raise HTTPException(422, {"code": "owner_invite_forbidden",
                                   "detail": "Owner role cannot be assigned via invitation."})

    # Check if user already a member of this org (via email)
    existing_user = await db.users.find_one({"email": email})
    if existing_user:
        existing_m = await db.memberships.find_one({
            "user_id": existing_user["_id"], "org_id": org_id, "status": "active",
        })
        if existing_m:
            raise HTTPException(409, {"code": "already_member",
                                       "detail": f"{email} is already a member of this org."})

    # Reject duplicate pending
    dup = await db.invitations.find_one({
        "org_id": org_id, "email": email, "status": "pending",
    })
    if dup:
        raise HTTPException(409, {"code": "duplicate_pending",
                                   "detail": f"{email} already has a pending invitation.",
                                   "invitation_id": dup["_id"]})

    # Resolve role_id from org's roles
    role = await db.roles.find_one({"org_id": org_id, "name": role_name})
    if not role:
        raise HTTPException(400, f"role '{role_name}' not found in this org")

    now = _now()
    token = secrets.token_urlsafe(32)
    doc = {
        "_id": str(uuid.uuid4()),
        "org_id": org_id,
        "email": email,
        "role_id": role["_id"],
        "role_name": role_name,
        "token": token,
        "invited_by": invited_by,
        "status": "pending",
        "expires_at": now + timedelta(days=expires_in_days),
        "email_sent": False,
        "email_provider": None,
        "email_sent_at": None,
        "email_message_id": None,
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "accepted_at": None,
        "revoked_at": None,
    }
    await db.invitations.insert_one(doc)

    # Load org + inviter for email
    org = await db.organizations.find_one({"_id": org_id})
    inviter = await db.users.find_one({"_id": invited_by})
    email_result = await _send_invitation_email(db, doc, org or {}, inviter or {}, bg)

    audit(bg, action="invitation.created", actor_id=invited_by, org_id=org_id,
          target_type="invitation", target_id=doc["_id"],
          diff={"email": email, "role": role_name}, request=request)

    fresh = await db.invitations.find_one({"_id": doc["_id"]})
    hydrated = await _hydrate_invitation(db, fresh)
    hydrated["email_delivery"] = email_result
    return hydrated


# ─────────────────────── endpoints ───────────────────────
@router.get("/orgs/{org_id}/invitations")
async def list_invitations(
    org_id: str,
    ctx: AuthContext = Depends(require_permission("users.manage")),
):
    if ctx.org_id != org_id:
        raise HTTPException(403, "active org does not match")
    db = get_db()
    cursor = db.invitations.find({"org_id": org_id}).sort("created_at", -1)
    items = await cursor.to_list(500)
    out = []
    for inv in items:
        inv = await _expire_if_needed(db, inv)
        out.append(await _hydrate_invitation(db, inv))
    return out


@router.post("/orgs/{org_id}/invitations", status_code=201)
async def create_invitation(
    org_id: str,
    body: BatchInvitationBody,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
):
    if ctx.org_id != org_id:
        raise HTTPException(403, "active org does not match")

    # Rate limit — apply once for the batch; each email counts as one hit
    for _ in body.emails:
        _check_rate_limit(org_id)

    db = get_db()
    results = []
    for raw_email in body.emails:
        raw = (raw_email or "").strip().lower()
        if not raw:
            continue
        # basic shape check (Email pydantic type not applicable per-item cleanly here)
        try:
            from models import _validate_email
            email = _validate_email(raw)
        except Exception:
            results.append({"email": raw_email, "status": "invalid_email",
                            "detail": "Not a valid email address"})
            continue
        try:
            hydrated = await _create_one_invitation(
                db, org_id=org_id, email=email, role_name=body.role_name,
                invited_by=ctx.user["_id"], expires_in_days=body.expires_in_days or 7,
                bg=bg, request=request,
            )
            hydrated["status"] = hydrated.get("status", "pending")
            hydrated["_result"] = "sent" if hydrated.get("email_delivery", {}).get("ok") else "sent_no_email"
            results.append(hydrated)
        except HTTPException as e:
            det = e.detail if isinstance(e.detail, dict) else {"detail": str(e.detail)}
            results.append({"email": email, "status": "error",
                            "code": det.get("code"), "detail": det.get("detail") or str(e.detail),
                            "invitation_id": det.get("invitation_id")})
    return {"invitations": results}


@router.post("/orgs/{org_id}/invitations/{iid}/resend")
async def resend_invitation(
    org_id: str, iid: str, body: InvitationResendBody,
    bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
):
    if ctx.org_id != org_id:
        raise HTTPException(403, "active org does not match")
    _check_rate_limit(org_id)
    db = get_db()
    inv = await db.invitations.find_one({"_id": iid, "org_id": org_id})
    if not inv:
        raise HTTPException(404, "invitation not found")
    if inv["status"] in ("accepted", "revoked"):
        raise HTTPException(409, f"invitation is {inv['status']}, cannot resend")
    now = _now()
    new_token = secrets.token_urlsafe(32)
    exp = now + timedelta(days=body.expires_in_days or 7)
    await db.invitations.update_one(
        {"_id": iid},
        {"$set": {
            "token": new_token, "expires_at": exp, "status": "pending",
            "email_sent": False, "email_sent_at": None, "email_message_id": None,
            "updated_at": _iso(now),
        }},
    )
    fresh = await db.invitations.find_one({"_id": iid})
    org = await db.organizations.find_one({"_id": org_id})
    inviter = ctx.user
    email_result = await _send_invitation_email(db, fresh, org or {}, inviter, bg)
    audit(bg, action="invitation.resent", actor_id=ctx.user["_id"], org_id=org_id,
          target_type="invitation", target_id=iid,
          diff={"email": inv["email"]}, request=request)
    fresh = await db.invitations.find_one({"_id": iid})
    hydrated = await _hydrate_invitation(db, fresh)
    hydrated["email_delivery"] = email_result
    return hydrated


@router.post("/orgs/{org_id}/invitations/{iid}/revoke")
async def revoke_invitation(
    org_id: str, iid: str, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
):
    if ctx.org_id != org_id:
        raise HTTPException(403, "active org does not match")
    db = get_db()
    inv = await db.invitations.find_one({"_id": iid, "org_id": org_id})
    if not inv:
        raise HTTPException(404, "invitation not found")
    if inv["status"] in ("accepted", "revoked"):
        raise HTTPException(409, f"invitation is already {inv['status']}")
    now = _now()
    await db.invitations.update_one(
        {"_id": iid},
        {"$set": {"status": "revoked", "revoked_at": _iso(now), "updated_at": _iso(now)}},
    )
    audit(bg, action="invitation.revoked", actor_id=ctx.user["_id"], org_id=org_id,
          target_type="invitation", target_id=iid, request=request)
    fresh = await db.invitations.find_one({"_id": iid})
    return await _hydrate_invitation(db, fresh)


@router.delete("/orgs/{org_id}/invitations/{iid}", status_code=204)
async def delete_invitation(
    org_id: str, iid: str, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
):
    if ctx.org_id != org_id:
        raise HTTPException(403, "active org does not match")
    db = get_db()
    inv = await db.invitations.find_one({"_id": iid, "org_id": org_id})
    if not inv:
        raise HTTPException(404, "invitation not found")
    if inv["status"] not in ("revoked", "expired"):
        raise HTTPException(409, "only revoked or expired invitations can be deleted")
    await db.invitations.delete_one({"_id": iid})
    audit(bg, action="invitation.deleted", actor_id=ctx.user["_id"], org_id=org_id,
          target_type="invitation", target_id=iid, request=request)
    return None


# ─────────────────────── public ───────────────────────
@router.get("/invitations/{token}")
async def get_invitation_by_token(token: str):
    """Public — returns meta about the invitation for the accept UI."""
    db = get_db()
    inv = await db.invitations.find_one({"token": token})
    if not inv:
        raise HTTPException(404, {"code": "invitation_not_found",
                                   "detail": "This invitation link is not valid."})
    inv = await _expire_if_needed(db, inv)
    org = await db.organizations.find_one({"_id": inv["org_id"], "deleted_at": None},
                                           {"name": 1, "slug": 1})
    inviter = None
    if inv.get("invited_by"):
        u = await db.users.find_one({"_id": inv["invited_by"]}, {"name": 1, "email": 1})
        if u:
            inviter = {"name": u.get("name"), "email": u.get("email")}
    return {
        "status": inv["status"],
        "email": inv["email"],
        "role_name": inv["role_name"],
        "org_name": (org or {}).get("name") if org else None,
        "org_slug": (org or {}).get("slug") if org else None,
        "inviter": inviter,
        "expires_at": inv.get("expires_at").isoformat() if isinstance(inv.get("expires_at"), datetime) else inv.get("expires_at"),
        "accepted_at": inv.get("accepted_at"),
        "revoked_at": inv.get("revoked_at"),
    }


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str, bg: BackgroundTasks, request: Request,
    user: dict = Depends(get_current_user),
):
    """Authenticated. The logged-in user's email must match the invitee email."""
    db = get_db()
    inv = await db.invitations.find_one({"token": token})
    if not inv:
        raise HTTPException(404, {"code": "invitation_not_found",
                                   "detail": "This invitation link is not valid."})
    inv = await _expire_if_needed(db, inv)
    if inv["status"] == "accepted":
        # Idempotent — return the existing membership info
        m = await db.memberships.find_one(
            {"user_id": user["_id"], "org_id": inv["org_id"], "status": "active"},
        )
        if m:
            return {"already_accepted": True, "org_id": inv["org_id"], "role": inv["role_name"]}
        raise HTTPException(409, {"code": "already_accepted",
                                   "detail": "This invitation was already accepted."})
    if inv["status"] == "revoked":
        raise HTTPException(410, {"code": "invitation_revoked",
                                   "detail": "This invitation was revoked."})
    if inv["status"] == "expired":
        raise HTTPException(410, {"code": "invitation_expired",
                                   "detail": "This invitation has expired."})

    # Email must match
    if (user.get("email") or "").lower().strip() != inv["email"].lower().strip():
        raise HTTPException(403, {"code": "email_mismatch",
                                   "detail": f"This invitation is for {inv['email']}. "
                                              f"Sign in with that email to accept."})

    # Check org still exists
    org = await db.organizations.find_one({"_id": inv["org_id"], "deleted_at": None})
    if not org:
        raise HTTPException(410, {"code": "org_gone",
                                   "detail": "The organization no longer exists."})

    # Existing membership? — upgrade to invited role if different
    existing = await db.memberships.find_one({
        "user_id": user["_id"], "org_id": inv["org_id"], "status": "active",
    })
    if existing:
        if existing.get("role_name") != inv["role_name"]:
            role = await db.roles.find_one({"org_id": inv["org_id"], "name": inv["role_name"]})
            await db.memberships.update_one(
                {"_id": existing["_id"]},
                {"$set": {"role_id": role["_id"], "role_name": inv["role_name"],
                          "updated_at": _iso(_now())}},
            )
    else:
        await add_membership(db, user_id=user["_id"], org_id=inv["org_id"],
                             role_name=inv["role_name"])

    now = _now()
    await db.invitations.update_one(
        {"_id": inv["_id"]},
        {"$set": {"status": "accepted", "accepted_at": _iso(now),
                  "accepted_by_user_id": user["_id"], "updated_at": _iso(now)}},
    )

    # Set default_org if the user has none
    if not user.get("default_org_id"):
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"default_org_id": inv["org_id"], "updated_at": _iso(now)}},
        )

    audit(bg, action="invitation.accepted", actor_id=user["_id"], org_id=inv["org_id"],
          target_type="invitation", target_id=inv["_id"],
          diff={"email": inv["email"], "role": inv["role_name"]}, request=request)

    return {
        "accepted": True,
        "org_id": inv["org_id"],
        "org_name": org.get("name"),
        "role": inv["role_name"],
        "was_first_org": not bool(user.get("default_org_id")),
    }


# ─────────────────────── user prompt dismissals ───────────────────────
class DismissPromptBody(BaseModel):
    prompt_key: str = Field(min_length=1, max_length=64)


@router.post("/users/me/dismissed-prompts")
async def dismiss_prompt(
    body: DismissPromptBody, user: dict = Depends(get_current_user),
):
    db = get_db()
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$addToSet": {"dismissed_prompts": body.prompt_key},
         "$set": {"updated_at": _iso(_now())}},
    )
    return {"ok": True, "prompt_key": body.prompt_key}


@router.get("/users/me/dismissed-prompts")
async def list_dismissed_prompts(user: dict = Depends(get_current_user)):
    db = get_db()
    u = await db.users.find_one({"_id": user["_id"]}, {"dismissed_prompts": 1})
    return {"dismissed_prompts": (u or {}).get("dismissed_prompts") or []}


# ─────────────────────── after-import nudge ───────────────────────
@router.get("/nudges/invite-after-import")
async def nudge_invite_after_import(user: dict = Depends(get_current_user)):
    """Return whether to show the "invite a teammate" nudge after a large import.

    Show when:
      - user has NOT dismissed the `invite_after_import` prompt, AND
      - their most recent completed import in the active org has
        inserted + updated >= 50 rows.
    """
    from datetime import timedelta as _td
    db = get_db()
    u = await db.users.find_one(
        {"_id": user["_id"]}, {"dismissed_prompts": 1, "default_org_id": 1},
    )
    dismissed = (u or {}).get("dismissed_prompts") or []
    if "invite_after_import" in dismissed:
        return {"show": False, "reason": "dismissed"}
    org_id = (u or {}).get("default_org_id")
    if not org_id:
        return {"show": False, "reason": "no_org"}
    cutoff = (_now() - _td(days=30)).isoformat()
    recent = await db.import_jobs.find_one({
        "org_id": org_id, "user_id": user["_id"], "status": "completed",
        "created_at": {"$gte": cutoff},
    }, sort=[("created_at", -1)])
    if not recent:
        return {"show": False, "reason": "no_recent_import"}
    total_written = int(recent.get("inserted", 0)) + int(recent.get("updated", 0))
    if total_written < 50:
        return {"show": False, "reason": "small_import", "rows": total_written}
    # Also check if the user already has other members to invite
    members = await db.memberships.count_documents({"org_id": org_id, "status": "active"})
    return {
        "show": True,
        "reason": "large_import_completed",
        "rows": total_written,
        "import_job_id": recent["_id"],
        "org_id": org_id,
        "solo": members <= 1,
    }
