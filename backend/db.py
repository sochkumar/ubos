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
        # tz_aware=True + explicit tzinfo so Motor returns tz-aware datetimes
        # (matches the tz-aware datetimes we write, keeps compares safe).
        from datetime import timezone
        _client = AsyncIOMotorClient(MONGO_URL, tz_aware=True, tzinfo=timezone.utc)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    global _db
    if _db is None:
        _db = get_client()[DB_NAME]
    return _db


def tenant_filter(org_id: str, extra: dict | None = None) -> dict:
    """Build a query filter scoped to an org and excluding soft-deleted docs."""
    q: dict = {"org_id": org_id, "deleted_at": None}
    if extra:
        q.update(extra)
    return q


async def ensure_indexes() -> None:
    db = get_db()

    # ── Phase 0 collections ──
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
    try:
        await db.records.create_index([("search_text", "text")])
    except Exception:
        pass

    # ── Phase 1 collections ──
    await db.users.create_index("email", unique=True)
    await db.users.create_index("google_sub", sparse=True)
    await db.organizations.create_index("slug", unique=True)
    await db.memberships.create_index(
        [("user_id", 1), ("org_id", 1)], unique=True, name="uniq_user_org"
    )
    await db.memberships.create_index([("org_id", 1)])
    await db.roles.create_index([("org_id", 1), ("name", 1)], unique=True)

    # Refresh tokens: index by hash + TTL cleanup via expires_at
    await db.refresh_tokens.create_index("token_hash", unique=True)
    await db.refresh_tokens.create_index("user_id")
    await db.refresh_tokens.create_index("expires_at", expireAfterSeconds=0)

    # Password reset tokens: TTL
    await db.password_reset_tokens.create_index("token_hash", unique=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)

    # OAuth state + one-time exchange codes: TTL
    await db.oauth_states.create_index("expires_at", expireAfterSeconds=0)
    await db.oauth_exchange.create_index("expires_at", expireAfterSeconds=0)

    # Login attempts (brute force)
    await db.login_attempts.create_index("identifier")
    await db.login_attempts.create_index("expires_at", expireAfterSeconds=0)

    # Audit logs — indexed by org + ts descending, keep forever
    await db.audit_logs.create_index([("org_id", 1), ("ts", -1)])
    await db.audit_logs.create_index([("actor_id", 1), ("ts", -1)])
