"""Shared org-creation logic used by /orgs POST, register, and startup seeding."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from security import ROLE_PERMISSIONS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", name.lower().strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:60] or "org"


async def _unique_slug(db, base: str) -> str:
    slug = base
    i = 1
    while await db.organizations.find_one({"slug": slug}):
        i += 1
        slug = f"{base}-{i}"
    return slug


async def create_organization(
    db: AsyncIOMotorDatabase,
    *,
    name: str,
    slug: str | None,
    creator_user_id: str,
    make_default: bool = True,
) -> dict:
    """Create an organization + seed the 4 system roles + owner membership.

    Returns the org document.
    """
    slug = slug or slugify(name)
    slug = await _unique_slug(db, slug)
    now = _now()
    org = {
        "_id": str(uuid.uuid4()),
        "name": name,
        "slug": slug,
        "plan": "free",
        "settings": {},
        "storage_used_bytes": 0,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "created_by": creator_user_id,
    }
    await db.organizations.insert_one(org)

    # Seed the 4 system roles
    role_ids: dict[str, str] = {}
    for role_name, perms in ROLE_PERMISSIONS.items():
        rid = str(uuid.uuid4())
        await db.roles.insert_one({
            "_id": rid,
            "org_id": org["_id"],
            "name": role_name,
            "permissions": list(perms),
            "is_system": True,
            "created_at": now,
        })
        role_ids[role_name] = rid

    # Owner membership
    await db.memberships.insert_one({
        "_id": str(uuid.uuid4()),
        "user_id": creator_user_id,
        "org_id": org["_id"],
        "role_id": role_ids["owner"],
        "role_name": "owner",  # denormalized for cheap reads
        "status": "active",
        "created_at": now,
    })

    if make_default:
        await db.users.update_one(
            {"_id": creator_user_id},
            {"$set": {"default_org_id": org["_id"], "updated_at": now}},
        )

    return org


async def get_membership(db, *, user_id: str, org_id: str) -> dict | None:
    return await db.memberships.find_one(
        {"user_id": user_id, "org_id": org_id, "status": "active"}
    )


async def add_membership(
    db, *, user_id: str, org_id: str, role_name: str
) -> dict:
    role = await db.roles.find_one({"org_id": org_id, "name": role_name})
    if not role:
        raise HTTPException(status_code=400, detail=f"role '{role_name}' does not exist")
    now = _now()
    m = {
        "_id": str(uuid.uuid4()),
        "user_id": user_id,
        "org_id": org_id,
        "role_id": role["_id"],
        "role_name": role_name,
        "status": "active",
        "created_at": now,
    }
    await db.memberships.insert_one(m)
    return m
