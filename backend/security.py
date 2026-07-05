"""Password hashing, JWT create/verify, RBAC permissions."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

JWT_ALGORITHM = "HS256"


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def _access_ttl() -> int:
    return int(os.environ.get("JWT_ACCESS_TTL_MINUTES", "15"))


def _refresh_ttl_days() -> int:
    return int(os.environ.get("JWT_REFRESH_TTL_DAYS", "30"))


# ─────────────────────── passwords ───────────────────────
def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ─────────────────────── JWTs ───────────────────────
def _iso(dt: datetime) -> str:
    return dt.isoformat()


def create_access_token(
    *,
    user_id: str,
    org_id: str | None,
    role: str | None,
    permissions: list[str],
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=_access_ttl())
    payload: dict[str, Any] = {
        "sub": user_id,
        "org_id": org_id,
        "role": role,
        "permissions": permissions,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "access",
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM), exp


def create_refresh_token(*, user_id: str) -> tuple[str, datetime, str]:
    """Return (raw_token, expires_at, token_hash)."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=_refresh_ttl_days())
    raw = secrets.token_urlsafe(48)
    payload = {
        "sub": user_id,
        "jti": raw[:16],
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": "refresh",
    }
    token = jwt.encode({**payload, "raw": raw}, _secret(), algorithm=JWT_ALGORITHM)
    return token, exp, sha256_hex(token)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise ValueError(str(e)) from e


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ─────────────────────── RBAC ───────────────────────
ALL_PERMISSIONS = [
    "org.read", "org.update",
    "users.read", "users.manage",
    "entity_types.read", "entity_types.manage",
    "fields.read", "fields.manage",
    "records.read", "records.create", "records.update", "records.delete",
    "media.read", "media.manage",
    "audit.read",
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "owner": list(ALL_PERMISSIONS),
    "admin": [p for p in ALL_PERMISSIONS],  # phase 1: same as owner (no delete-org yet)
    "editor": [
        "org.read",
        "entity_types.read", "fields.read",
        "records.read", "records.create", "records.update", "records.delete",
        "media.read", "media.manage",
        "users.read",
    ],
    "viewer": [
        "org.read",
        "entity_types.read", "fields.read",
        "records.read", "media.read",
        "users.read",
    ],
}


def permissions_for_role(role_name: str) -> list[str]:
    return list(ROLE_PERMISSIONS.get(role_name, []))
