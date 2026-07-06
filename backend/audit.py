"""Async, non-blocking audit log helper."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, Request

from db import get_db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _write(entry: dict) -> None:
    await get_db().audit_logs.insert_one(entry)


def audit(
    bg: BackgroundTasks | None,
    *,
    action: str,
    org_id: str | None = None,
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    diff: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Queue an audit log entry as a background task (fire-and-forget)."""
    entry = {
        "_id": str(uuid.uuid4()),
        "org_id": org_id,
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "diff": diff or {},
        "ip": None,
        "ua": (request.headers.get("user-agent") if request else None),
        "ts": _now(),
    }
    if request is not None:
        try:
            from core.request_ip import get_client_ip
            entry["ip"] = get_client_ip(request)
        except Exception:
            entry["ip"] = request.client.host if request.client else None
    if bg is not None:
        bg.add_task(_write, entry)
    else:
        # allow synchronous callers (e.g. startup seeding) to skip logging
        pass
