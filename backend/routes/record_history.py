"""Record activity + versions endpoints."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pymongo import ReturnDocument

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import CommentPayload, RestorePayload, strip_id
from services.history import emit_activity, snapshot_version

router = APIRouter(tags=["record-history"])


@router.get("/records/{rid}/activity")
async def list_activity(
    rid: str,
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    rec = await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rid}), {"_id": 1})
    if not rec:
        raise HTTPException(404, "record not found")
    q = {"org_id": ctx.org_id, "record_id": rid}
    total = await db.record_activity.count_documents(q)
    cursor = db.record_activity.find(q).sort("ts", -1).skip(skip).limit(limit)
    return {"total": total, "items": [strip_id(d) for d in await cursor.to_list(limit)]}


@router.post("/records/{rid}/activity", status_code=201)
async def post_comment(
    rid: str, payload: CommentPayload,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    db = get_db()
    rec = await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rid}))
    if not rec:
        raise HTTPException(404, "record not found")
    await emit_activity(
        db, record=rec,
        actor_id=ctx.user["_id"], actor_name=ctx.user.get("name") or ctx.user.get("email"),
        type="comment", payload={"text": payload.text},
    )
    return {"ok": True}


@router.get("/records/{rid}/versions")
async def list_versions(
    rid: str,
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    rec = await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rid}), {"_id": 1})
    if not rec:
        raise HTTPException(404, "record not found")
    q = {"org_id": ctx.org_id, "record_id": rid}
    total = await db.record_versions.count_documents(q)
    # Denormalise actor name if possible
    cursor = db.record_versions.find(q).sort("version_number", -1).skip(skip).limit(limit)
    items = [strip_id(d) for d in await cursor.to_list(limit)]
    actor_ids = list({i.get("changed_by") for i in items if i.get("changed_by")})
    if actor_ids:
        users = {u["_id"]: u for u in await db.users.find(
            {"_id": {"$in": actor_ids}}, {"name": 1, "email": 1}
        ).to_list(1000)}
        for i in items:
            u = users.get(i.get("changed_by"))
            if u:
                i["actor_name"] = u.get("name") or u.get("email")
    return {"total": total, "items": items}


@router.get("/records/{rid}/versions/{v}")
async def get_version(
    rid: str, v: int,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    doc = await get_db().record_versions.find_one({
        "org_id": ctx.org_id, "record_id": rid, "version_number": v,
    })
    if not doc:
        raise HTTPException(404, "version not found")
    return strip_id(doc)


@router.post("/records/{rid}/versions/{v}/restore")
async def restore_version(
    rid: str, v: int, payload: RestorePayload,
    bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    db = get_db()
    rec = await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rid}))
    if not rec:
        raise HTTPException(404, "record not found")
    target = await db.record_versions.find_one({
        "org_id": ctx.org_id, "record_id": rid, "version_number": v,
    })
    if not target:
        raise HTTPException(404, "version not found")

    # snapshot current first
    await snapshot_version(db, record=rec, actor_id=ctx.user["_id"], reason=f"pre-restore of v{v}")

    from datetime import datetime, timezone
    snap = dict(target["snapshot"])
    snap["version"] = int(rec.get("version", 1)) + 1
    snap["updated_at"] = datetime.now(timezone.utc).isoformat()
    snap.pop("deleted_at", None)  # restore always un-deletes
    snap["deleted_at"] = None
    updated = await db.records.find_one_and_update(
        {"_id": rid, "org_id": ctx.org_id},
        {"$set": snap},
        return_document=ReturnDocument.AFTER,
    )
    await emit_activity(
        db, record=updated, actor_id=ctx.user["_id"],
        actor_name=ctx.user.get("name") or ctx.user.get("email"),
        type="restored", payload={"from_version": v, "reason": payload.reason},
    )
    audit(bg, action="record.restored", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="record", target_id=rid,
          diff={"from_version": v, "new_version": snap["version"]}, request=request)
    return strip_id(updated)
