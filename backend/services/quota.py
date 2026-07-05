"""Per-organization storage quota tracking + enforcement."""
from __future__ import annotations

import os

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase


def _default_quota() -> int:
    return int(os.environ.get("DEFAULT_ORG_STORAGE_QUOTA_BYTES", str(5 * 1024**3)))


def _max_upload() -> int:
    return int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(25 * 1024 * 1024)))


async def get_org(db: AsyncIOMotorDatabase, org_id: str) -> dict:
    org = await db.organizations.find_one({"_id": org_id})
    if not org:
        raise HTTPException(404, "org not found")
    return org


async def quota_of(db: AsyncIOMotorDatabase, org_id: str) -> tuple[int, int, int]:
    """Return (used_bytes, quota_bytes, max_upload_bytes)."""
    org = await get_org(db, org_id)
    used = int(org.get("storage_used_bytes", 0))
    quota = int((org.get("settings") or {}).get("storage_quota_bytes") or _default_quota())
    return used, quota, _max_upload()


async def check_can_upload(db: AsyncIOMotorDatabase, org_id: str, incoming_size: int) -> None:
    if incoming_size > _max_upload():
        raise HTTPException(
            status_code=413,
            detail={
                "code": "file_too_large",
                "detail": "File exceeds MAX_UPLOAD_SIZE_BYTES",
                "max_bytes": _max_upload(),
                "incoming_bytes": incoming_size,
            },
        )
    used, quota, _max = await quota_of(db, org_id)
    if used + incoming_size > quota:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "quota_exceeded",
                "detail": "Storage quota exceeded",
                "quota_bytes": quota,
                "used_bytes": used,
                "incoming_bytes": incoming_size,
            },
        )


async def add_bytes(db: AsyncIOMotorDatabase, org_id: str, delta: int) -> None:
    await db.organizations.update_one(
        {"_id": org_id}, {"$inc": {"storage_used_bytes": int(delta)}}
    )


async def set_quota(db: AsyncIOMotorDatabase, org_id: str, quota_bytes: int) -> dict:
    MIN = 100 * 1024 * 1024      # 100 MB
    MAX = 100 * 1024 * 1024 * 1024  # 100 GB
    if quota_bytes < MIN or quota_bytes > MAX:
        raise HTTPException(422, f"quota must be between {MIN} and {MAX} bytes")
    org = await db.organizations.find_one_and_update(
        {"_id": org_id},
        {"$set": {"settings.storage_quota_bytes": int(quota_bytes)}},
        return_document=True,
    )
    if not org:
        raise HTTPException(404, "org not found")
    return org
