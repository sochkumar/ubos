"""Audit log read endpoint (admin+)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from auth_deps import AuthContext, require_permission
from db import get_db
from models import strip_id

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    action: str | None = None,
    actor_id: str | None = None,
    ctx: AuthContext = Depends(require_permission("audit.read")),
):
    db = get_db()
    q: dict = {"org_id": ctx.org_id}
    if action:
        q["action"] = action
    if actor_id:
        q["actor_id"] = actor_id
    total = await db.audit_logs.count_documents(q)
    cursor = db.audit_logs.find(q).sort("ts", -1).skip(skip).limit(limit)
    items = [strip_id(d) for d in await cursor.to_list(limit)]
    # attach actor email if we can
    actor_ids = list({i["actor_id"] for i in items if i.get("actor_id")})
    if actor_ids:
        users = {u["_id"]: u for u in await db.users.find(
            {"_id": {"$in": actor_ids}}, {"email": 1, "name": 1}
        ).to_list(1000)}
        for i in items:
            u = users.get(i.get("actor_id"))
            if u:
                i["actor_email"] = u.get("email")
                i["actor_name"] = u.get("name")
    return {"total": total, "items": items}
