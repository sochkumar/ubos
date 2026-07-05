"""Relationship definitions — schema-level (no instance CRUD in Phase 2)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pymongo import ReturnDocument

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import RelDefCreate, RelDefUpdate, strip_id

router = APIRouter(tags=["relationships"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/entity-types/{et_id}/relationships")
async def list_relationships(
    et_id: str,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    cursor = db.relationship_definitions.find(
        tenant_filter(ctx.org_id, {"from_entity_type_id": et_id})
    ).sort("created_at", 1)
    return [strip_id(d) for d in await cursor.to_list(1000)]


@router.post("/entity-types/{et_id}/relationships", status_code=201)
async def create_relationship(
    et_id: str,
    payload: RelDefCreate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="from entity type not found")
    to_et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": payload.to_entity_type_id}), {"_id": 1})
    if not to_et:
        raise HTTPException(status_code=404, detail="to entity type not found")
    conflict = await db.relationship_definitions.find_one(tenant_filter(ctx.org_id, {
        "from_entity_type_id": et_id, "key": payload.key,
    }))
    if conflict:
        raise HTTPException(status_code=409, detail=f"relationship with key '{payload.key}' already exists")

    rid = str(uuid.uuid4())
    doc = {
        "_id": rid, "org_id": ctx.org_id,
        "from_entity_type_id": et_id,
        "to_entity_type_id": payload.to_entity_type_id,
        "key": payload.key,
        "from_label": payload.from_label,
        "to_label": payload.to_label,
        "cardinality": payload.cardinality,
        "required": payload.required,
        "cascade_delete": payload.cascade_delete,
        "description": payload.description,
        "created_at": _now(), "updated_at": _now(), "deleted_at": None,
    }
    await db.relationship_definitions.insert_one(doc)
    audit(bg, action="relationship.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="relationship", target_id=rid,
          diff={"key": payload.key, "from": et_id, "to": payload.to_entity_type_id},
          request=request)
    return strip_id(doc)


@router.get("/relationships/definitions/{rel_id}")
async def get_relationship(
    rel_id: str, ctx: AuthContext = Depends(require_permission("records.read"))
):
    doc = await get_db().relationship_definitions.find_one(
        tenant_filter(ctx.org_id, {"_id": rel_id})
    )
    if not doc:
        raise HTTPException(status_code=404, detail="relationship not found")
    return strip_id(doc)


@router.patch("/relationships/definitions/{rel_id}")
async def update_relationship(
    rel_id: str,
    payload: RelDefUpdate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        doc = await db.relationship_definitions.find_one(tenant_filter(ctx.org_id, {"_id": rel_id}))
        if not doc:
            raise HTTPException(status_code=404, detail="relationship not found")
        return strip_id(doc)
    updates["updated_at"] = _now()
    doc = await db.relationship_definitions.find_one_and_update(
        tenant_filter(ctx.org_id, {"_id": rel_id}),
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="relationship not found")
    audit(bg, action="relationship.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="relationship", target_id=rel_id, diff=updates, request=request)
    return strip_id(doc)


@router.delete("/relationships/definitions/{rel_id}", status_code=204)
async def delete_relationship(
    rel_id: str,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    now = _now()
    res = await db.relationship_definitions.update_one(
        tenant_filter(ctx.org_id, {"_id": rel_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="relationship not found")
    audit(bg, action="relationship.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="relationship", target_id=rel_id, request=request)
    return None
