"""Category CRUD endpoints — hierarchical, materialized path."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import CategoryCreate, CategoryMove, CategoryReorder, CategoryUpdate, strip_id
from services.categories import (
    create_category,
    get_tree,
    move_category,
    rename_category,
    soft_delete_category,
)

router = APIRouter(tags=["categories"])


def _clean(doc: dict) -> dict:
    d = strip_id(doc)
    d.pop("children", None)  # tree endpoint attaches this in flat mode
    return d


@router.get("/entity-types/{et_id}/categories")
async def list_categories(
    et_id: str,
    flat: bool = Query(default=False),
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    if flat:
        cursor = db.categories.find(
            tenant_filter(ctx.org_id, {"entity_type_id": et_id})
        ).sort([("depth", 1), ("order", 1)])
        return [_clean(d) for d in await cursor.to_list(10000)]
    return await get_tree(db, org_id=ctx.org_id, entity_type_id=et_id)


@router.post("/entity-types/{et_id}/categories", status_code=201)
async def create_category_endpoint(
    et_id: str,
    payload: CategoryCreate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    doc = await create_category(
        db,
        org_id=ctx.org_id,
        entity_type_id=et_id,
        name=payload.name,
        parent_id=payload.parent_id,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
    )
    audit(bg, action="category.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="category", target_id=doc["_id"],
          diff={"name": payload.name, "parent_id": payload.parent_id}, request=request)
    return _clean(doc)


@router.get("/categories/{cat_id}")
async def get_category(
    cat_id: str, ctx: AuthContext = Depends(require_permission("records.read"))
):
    doc = await get_db().categories.find_one(tenant_filter(ctx.org_id, {"_id": cat_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="category not found")
    return _clean(doc)


@router.patch("/categories/{cat_id}")
async def update_category(
    cat_id: str,
    payload: CategoryUpdate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    doc = await db.categories.find_one(tenant_filter(ctx.org_id, {"_id": cat_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="category not found")

    if payload.name is not None and payload.name != doc["name"]:
        doc = await rename_category(db, org_id=ctx.org_id, cat_id=cat_id, new_name=payload.name)

    other_updates = {}
    for k in ("description", "color", "icon"):
        v = getattr(payload, k)
        if v is not None:
            other_updates[k] = v
    if other_updates:
        from datetime import datetime, timezone
        other_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.categories.update_one({"_id": cat_id}, {"$set": other_updates})
        doc = await db.categories.find_one({"_id": cat_id})

    audit(bg, action="category.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="category", target_id=cat_id,
          diff=payload.model_dump(exclude_none=True), request=request)
    return _clean(doc)


@router.delete("/categories/{cat_id}", status_code=204)
async def delete_category(
    cat_id: str,
    bg: BackgroundTasks,
    request: Request,
    cascade: bool = Query(default=False),
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    await soft_delete_category(db, org_id=ctx.org_id, cat_id=cat_id, cascade=cascade)
    audit(bg, action="category.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="category", target_id=cat_id, diff={"cascade": cascade}, request=request)
    return None


@router.post("/categories/{cat_id}/move")
async def move_category_endpoint(
    cat_id: str,
    payload: CategoryMove,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    doc = await move_category(db, org_id=ctx.org_id, cat_id=cat_id, new_parent_id=payload.new_parent_id)
    audit(bg, action="category.moved", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="category", target_id=cat_id,
          diff={"new_parent_id": payload.new_parent_id}, request=request)
    return _clean(doc)


@router.post("/categories/{cat_id}/reorder")
async def reorder_category(
    cat_id: str,
    payload: CategoryReorder,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    cat = await db.categories.find_one(tenant_filter(ctx.org_id, {"_id": cat_id}))
    if not cat:
        raise HTTPException(status_code=404, detail="category not found")
    # Simple approach: bump this one to new_order, then compact siblings
    siblings = await db.categories.find(tenant_filter(ctx.org_id, {
        "entity_type_id": cat["entity_type_id"],
        "parent_id": cat.get("parent_id"),
    })).sort("order", 1).to_list(10000)
    siblings = [s for s in siblings if s["_id"] != cat_id]
    target = max(1, min(payload.new_order, len(siblings) + 1))
    siblings.insert(target - 1, cat)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    for i, s in enumerate(siblings, start=1):
        await db.categories.update_one(
            {"_id": s["_id"]}, {"$set": {"order": i, "updated_at": now}}
        )
    return {"ok": True}
