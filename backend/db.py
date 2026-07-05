"""MongoDB connection, indexes, and tenant helpers."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URL)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        _db = get_client()[DB_NAME]
    return _db


def tenant_filter(org_id: str, extra: dict | None = None) -> dict:
    """Build a query filter scoped to an org and excluding soft-deleted docs.

    Every read/update/delete in the app MUST route through this helper so we
    never accidentally cross tenant boundaries.
    """
    q: dict = {"org_id": org_id, "deleted_at": None}
    if extra:
        q.update(extra)
    return q


async def ensure_indexes() -> None:
    db = get_db()

    await db.entity_types.create_index(
        [("org_id", 1), ("key", 1)],
        unique=True,
        partialFilterExpression={"deleted_at": None},
        name="uniq_org_key_active",
    )
    await db.entity_types.create_index([("org_id", 1), ("deleted_at", 1)])

    await db.field_definitions.create_index(
        [("org_id", 1), ("entity_type_id", 1), ("key", 1)],
        unique=True,
        partialFilterExpression={"deleted_at": None},
        name="uniq_org_et_key_active",
    )
    await db.field_definitions.create_index(
        [("org_id", 1), ("entity_type_id", 1), ("order", 1)]
    )

    await db.records.create_index(
        [("org_id", 1), ("entity_type_id", 1), ("deleted_at", 1)]
    )
    await db.records.create_index([("org_id", 1), ("record_number", 1)])
    # text index for future search UI (Phase 2)
    try:
        await db.records.create_index([("search_text", "text")])
    except Exception:
        # index may already exist with different definition — ignore
        pass
