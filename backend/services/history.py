"""Record versioning + activity emit — small stateless helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def snapshot_version(
    db: AsyncIOMotorDatabase,
    *,
    record: dict,
    actor_id: str | None,
    reason: str | None = None,
) -> int:
    """Snapshot the given record doc as its current version.
    Returns the version_number written."""
    n = int(record.get("version", 1))
    doc = {
        "_id": str(uuid.uuid4()),
        "org_id": record["org_id"],
        "record_id": record["_id"],
        "version_number": n,
        "snapshot": {k: v for k, v in record.items() if k != "_id"},
        "changed_by": actor_id,
        "changed_at": _now(),
        "reason": reason,
    }
    await db.record_versions.insert_one(doc)
    return n


async def emit_activity(
    db: AsyncIOMotorDatabase,
    *,
    record: dict,
    actor_id: str | None,
    actor_name: str | None,
    type: str,
    payload: dict | None = None,
) -> None:
    await db.record_activity.insert_one({
        "_id": str(uuid.uuid4()),
        "org_id": record["org_id"],
        "record_id": record["_id"],
        "entity_type_id": record["entity_type_id"],
        "actor_id": actor_id,
        "actor_name": actor_name,
        "type": type,
        "payload": payload or {},
        "ts": _now(),
    })
