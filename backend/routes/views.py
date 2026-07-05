"""Views (saved query state) CRUD."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pymongo import ReturnDocument

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import ViewCreate, ViewUpdate, strip_id

router = APIRouter(tags=["views"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope_query(ctx: AuthContext, et_id: str) -> dict:
    """Views visible to this user in this et: their own + org-shared."""
    return {
        "org_id": ctx.org_id, "entity_type_id": et_id, "deleted_at": None,
        "$or": [{"user_id": ctx.user["_id"]}, {"is_shared": True}],
    }


@router.get("/entity-types/{et_id}/views")
async def list_views(et_id: str, ctx: AuthContext = Depends(require_permission("records.read"))):
    db = get_db()
    if not await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1}):
        raise HTTPException(404, "entity type not found")
    cursor = db.views.find(_scope_query(ctx, et_id)).sort("created_at", 1)
    return [strip_id(d) for d in await cursor.to_list(500)]


@router.post("/entity-types/{et_id}/views", status_code=201)
async def create_view(
    et_id: str, payload: ViewCreate,
    bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    if not await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1}):
        raise HTTPException(404, "entity type not found")
    if payload.is_shared and ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "only owners/admins can create shared views")
    vid = str(uuid.uuid4())
    doc = {
        "_id": vid, "org_id": ctx.org_id, "entity_type_id": et_id,
        "user_id": None if payload.is_shared else ctx.user["_id"],
        "name": payload.name, "description": payload.description,
        "layout": payload.layout,
        "filters": [f.model_dump() for f in payload.filters],
        "category_ids": payload.category_ids,
        "tag_ids": payload.tag_ids,
        "q": payload.q,
        "sort": [s.model_dump() for s in payload.sort],
        "visible_fields": payload.visible_fields,
        "column_widths": payload.column_widths,
        "is_default": False,
        "is_shared": payload.is_shared,
        "created_at": _now(), "updated_at": _now(), "deleted_at": None,
    }
    await db.views.insert_one(doc)
    audit(bg, action="view.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="view", target_id=vid, diff={"name": payload.name, "shared": payload.is_shared},
          request=request)
    return strip_id(doc)


@router.get("/views/{vid}")
async def get_view(vid: str, ctx: AuthContext = Depends(require_permission("records.read"))):
    doc = await get_db().views.find_one({
        "_id": vid, "org_id": ctx.org_id, "deleted_at": None,
        "$or": [{"user_id": ctx.user["_id"]}, {"is_shared": True}],
    })
    if not doc:
        raise HTTPException(404, "view not found")
    return strip_id(doc)


@router.patch("/views/{vid}")
async def update_view(
    vid: str, payload: ViewUpdate,
    bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    doc = await db.views.find_one({"_id": vid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "view not found")
    is_owner_of_view = doc.get("user_id") == ctx.user["_id"]
    is_admin = ctx.role in ("owner", "admin")
    if doc.get("is_shared") and not is_admin:
        raise HTTPException(403, "only owners/admins can edit shared views")
    if not doc.get("is_shared") and not is_owner_of_view:
        raise HTTPException(403, "cannot edit another user's private view")

    updates = {}
    d = payload.model_dump(exclude_none=True)
    for k, v in d.items():
        if k in ("filters", "sort") and v is not None:
            updates[k] = [x if isinstance(x, dict) else x.model_dump() for x in v]
        else:
            updates[k] = v
    # is_shared flip needs admin
    if "is_shared" in updates and updates["is_shared"] != doc.get("is_shared") and not is_admin:
        raise HTTPException(403, "only owners/admins can toggle sharing")
    if updates.get("is_shared") and doc.get("user_id"):
        updates["user_id"] = None
    if updates.get("is_shared") is False and not doc.get("user_id"):
        updates["user_id"] = ctx.user["_id"]

    updates["updated_at"] = _now()
    fresh = await db.views.find_one_and_update(
        {"_id": vid}, {"$set": updates}, return_document=ReturnDocument.AFTER,
    )
    audit(bg, action="view.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="view", target_id=vid, diff=updates, request=request)
    return strip_id(fresh)


@router.delete("/views/{vid}", status_code=204)
async def delete_view(
    vid: str, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    doc = await db.views.find_one({"_id": vid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "view not found")
    is_admin = ctx.role in ("owner", "admin")
    if doc.get("is_shared") and not is_admin:
        raise HTTPException(403, "only owners/admins can delete shared views")
    if not doc.get("is_shared") and doc.get("user_id") != ctx.user["_id"]:
        raise HTTPException(403, "cannot delete another user's private view")
    await db.views.update_one({"_id": vid}, {"$set": {"deleted_at": _now()}})
    audit(bg, action="view.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="view", target_id=vid, request=request)
    return None


@router.post("/views/{vid}/set-default")
async def set_default_view(vid: str, ctx: AuthContext = Depends(require_permission("records.read"))):
    db = get_db()
    doc = await db.views.find_one({"_id": vid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "view not found")
    # Unset previous default in same scope
    if doc.get("is_shared"):
        await db.views.update_many(
            {"org_id": ctx.org_id, "entity_type_id": doc["entity_type_id"], "is_shared": True},
            {"$set": {"is_default": False}},
        )
    else:
        await db.views.update_many(
            {"org_id": ctx.org_id, "entity_type_id": doc["entity_type_id"],
             "user_id": ctx.user["_id"]},
            {"$set": {"is_default": False}},
        )
    await db.views.update_one({"_id": vid}, {"$set": {"is_default": True, "updated_at": _now()}})
    return {"ok": True}


@router.post("/views/{vid}/duplicate", status_code=201)
async def duplicate_view(vid: str, ctx: AuthContext = Depends(require_permission("records.read"))):
    db = get_db()
    doc = await db.views.find_one({
        "_id": vid, "org_id": ctx.org_id, "deleted_at": None,
        "$or": [{"user_id": ctx.user["_id"]}, {"is_shared": True}],
    })
    if not doc:
        raise HTTPException(404, "view not found")
    new = dict(doc)
    new["_id"] = str(uuid.uuid4())
    new["name"] = f"{doc['name']} (copy)"
    new["is_default"] = False
    new["is_shared"] = False
    new["user_id"] = ctx.user["_id"]
    new["created_at"] = _now()
    new["updated_at"] = _now()
    await db.views.insert_one(new)
    return strip_id(new)
