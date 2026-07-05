"""Organizations, memberships, org switching."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from audit import audit
from auth_deps import AuthContext, get_current_context, get_current_user, require_permission
from db import get_db
from models import MemberRoleUpdate, OrgCreate, OrgQuotaUpdate, OrgUpdate, strip_id
from routes._org_helpers import create_organization, get_membership
from routes.auth import _issue_tokens
from security import ROLE_PERMISSIONS, permissions_for_role
from services import quota as quota_svc

router = APIRouter(prefix="/orgs", tags=["orgs"])


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


@router.post("", status_code=201)
async def create_org(
    payload: OrgCreate,
    bg: BackgroundTasks,
    request: Request,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    org = await create_organization(
        db,
        name=payload.name,
        slug=payload.slug,
        creator_user_id=user["_id"],
        make_default=True,
    )
    audit(bg, action="org.created", actor_id=user["_id"], org_id=org["_id"],
          target_type="org", target_id=org["_id"], diff={"name": org["name"]}, request=request)
    tokens = await _issue_tokens(db, user, org_id=org["_id"])
    return {"org": {**strip_id(org), "role": "owner"}, **tokens}


@router.get("")
async def list_my_orgs(user: dict = Depends(get_current_user)):
    db = get_db()
    memberships = await db.memberships.find(
        {"user_id": user["_id"], "status": "active"}
    ).to_list(100)
    if not memberships:
        return []
    org_ids = [m["org_id"] for m in memberships]
    docs = await db.organizations.find(
        {"_id": {"$in": org_ids}, "deleted_at": None}
    ).to_list(100)
    role_by_org = {m["org_id"]: m.get("role_name") for m in memberships}
    return [{**strip_id(d), "role": role_by_org.get(d["_id"])} for d in docs]


@router.get("/{org_id}")
async def get_org(org_id: str, user: dict = Depends(get_current_user)):
    db = get_db()
    m = await get_membership(db, user_id=user["_id"], org_id=org_id)
    if not m:
        raise HTTPException(status_code=403, detail="not a member of this org")
    doc = await db.organizations.find_one({"_id": org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(status_code=404, detail="organization not found")
    return {**strip_id(doc), "role": m.get("role_name")}


@router.patch("/{org_id}")
async def update_org(
    org_id: str,
    payload: OrgUpdate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("org.update")),
):
    if ctx.org_id != org_id:
        # scripting override: verify membership at least
        raise HTTPException(status_code=403, detail="active org does not match")
    db = get_db()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        doc = await db.organizations.find_one({"_id": org_id, "deleted_at": None})
        if not doc:
            raise HTTPException(status_code=404, detail="organization not found")
        return strip_id(doc)
    # Deep-merge `settings` so callers can PATCH a single key (e.g. support_email)
    # without wiping storage_quota_bytes or other keys.
    if "settings" in updates and isinstance(updates["settings"], dict):
        existing = await db.organizations.find_one(
            {"_id": org_id, "deleted_at": None}, {"settings": 1},
        )
        merged = {**((existing or {}).get("settings") or {}), **updates["settings"]}
        updates["settings"] = merged
    updates["updated_at"] = _iso(_now_dt())
    from pymongo import ReturnDocument
    doc = await db.organizations.find_one_and_update(
        {"_id": org_id, "deleted_at": None},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="organization not found")
    audit(bg, action="org.updated", actor_id=ctx.user["_id"], org_id=org_id,
          target_type="org", target_id=org_id, diff=updates, request=request)
    return strip_id(doc)


@router.patch("/{org_id}/storage-quota")
async def update_storage_quota(
    org_id: str,
    payload: OrgQuotaUpdate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("org.update")),
):
    if ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="active org does not match")
    db = get_db()
    org = await quota_svc.set_quota(db, org_id, payload.storage_quota_bytes)
    audit(bg, action="org.quota_updated", actor_id=ctx.user["_id"], org_id=org_id,
          target_type="org", target_id=org_id,
          diff={"storage_quota_bytes": payload.storage_quota_bytes}, request=request)
    return strip_id(org)


@router.post("/{org_id}/switch")
async def switch_org(
    org_id: str,
    user: dict = Depends(get_current_user),
):
    db = get_db()
    m = await get_membership(db, user_id=user["_id"], org_id=org_id)
    if not m:
        raise HTTPException(status_code=403, detail="not a member of this org")
    org = await db.organizations.find_one({"_id": org_id, "deleted_at": None})
    if not org:
        raise HTTPException(status_code=404, detail="organization not found")
    await db.users.update_one(
        {"_id": user["_id"]}, {"$set": {"default_org_id": org_id, "updated_at": _iso(_now_dt())}}
    )
    return await _issue_tokens(db, user, org_id=org_id)


@router.get("/{org_id}/members")
async def list_members(
    org_id: str, ctx: AuthContext = Depends(require_permission("users.read"))
):
    if ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="active org does not match")
    db = get_db()
    memberships = await db.memberships.find(
        {"org_id": org_id, "status": "active"}
    ).to_list(500)
    user_ids = [m["user_id"] for m in memberships]
    users = {u["_id"]: u for u in await db.users.find({"_id": {"$in": user_ids}}).to_list(500)}
    out = []
    for m in memberships:
        u = users.get(m["user_id"], {})
        out.append({
            "id": m["_id"],
            "user_id": m["user_id"],
            "email": u.get("email"),
            "name": u.get("name"),
            "avatar_url": u.get("avatar_url"),
            "role": m.get("role_name"),
            "role_id": m.get("role_id"),
            "status": m.get("status"),
            "created_at": m.get("created_at"),
        })
    return out


@router.patch("/{org_id}/members/{membership_id}")
async def update_member_role(
    org_id: str,
    membership_id: str,
    payload: MemberRoleUpdate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
):
    if ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="active org does not match")
    db = get_db()
    m = await db.memberships.find_one({"_id": membership_id, "org_id": org_id})
    if not m:
        raise HTTPException(status_code=404, detail="membership not found")

    if m.get("role_name") == "owner" and payload.role_name != "owner":
        remaining_owners = await db.memberships.count_documents(
            {"org_id": org_id, "role_name": "owner", "status": "active", "_id": {"$ne": membership_id}}
        )
        if remaining_owners == 0:
            raise HTTPException(status_code=400, detail="cannot demote the last owner")

    role = await db.roles.find_one({"org_id": org_id, "name": payload.role_name})
    if not role:
        raise HTTPException(status_code=400, detail="role not found for this org")

    from pymongo import ReturnDocument
    updated = await db.memberships.find_one_and_update(
        {"_id": membership_id},
        {"$set": {"role_id": role["_id"], "role_name": payload.role_name,
                  "updated_at": _iso(_now_dt())}},
        return_document=ReturnDocument.AFTER,
    )
    audit(bg, action="member.role_changed", actor_id=ctx.user["_id"], org_id=org_id,
          target_type="membership", target_id=membership_id,
          diff={"from": m.get("role_name"), "to": payload.role_name}, request=request)
    return {
        "id": updated["_id"],
        "user_id": updated["user_id"],
        "role": updated["role_name"],
    }


@router.delete("/{org_id}/members/{membership_id}", status_code=204)
async def remove_member(
    org_id: str,
    membership_id: str,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("users.manage")),
):
    if ctx.org_id != org_id:
        raise HTTPException(status_code=403, detail="active org does not match")
    db = get_db()
    m = await db.memberships.find_one({"_id": membership_id, "org_id": org_id})
    if not m:
        raise HTTPException(status_code=404, detail="membership not found")
    if m.get("role_name") == "owner":
        remaining_owners = await db.memberships.count_documents(
            {"org_id": org_id, "role_name": "owner", "status": "active", "_id": {"$ne": membership_id}}
        )
        if remaining_owners == 0:
            raise HTTPException(status_code=400, detail="cannot remove the last owner")
    await db.memberships.delete_one({"_id": membership_id})
    audit(bg, action="member.removed", actor_id=ctx.user["_id"], org_id=org_id,
          target_type="membership", target_id=membership_id,
          diff={"removed_user_id": m["user_id"]}, request=request)
    return None
