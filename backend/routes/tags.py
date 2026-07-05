"""Tags — org-wide or entity-scoped, with autocomplete + usage_count."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import TagCreate, TagUpdate, strip_id

router = APIRouter(prefix="/tags", tags=["tags"])


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80] or "tag"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hex_color_for(name: str) -> str:
    palette = ["#0d9488", "#0369a1", "#7c3aed", "#dc2626", "#b45309", "#059669", "#2563eb", "#d946ef"]
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) % (2 ** 31)
    return palette[h % len(palette)]


@router.get("")
async def list_tags(
    entity_type_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    scope: dict = {}
    if entity_type_id:
        scope["$or"] = [{"entity_type_id": None}, {"entity_type_id": entity_type_id}]
    filt = tenant_filter(ctx.org_id, scope)
    if q:
        filt["name"] = {"$regex": re.escape(q), "$options": "i"}
    cursor = db.tags.find(filt).sort([("usage_count", -1), ("name", 1)]).limit(100)
    return [strip_id(d) for d in await cursor.to_list(100)]


@router.post("", status_code=201)
async def create_tag(
    payload: TagCreate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("records.create")),
):
    db = get_db()
    et_id = payload.entity_type_id
    if et_id:
        et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
        if not et:
            raise HTTPException(status_code=404, detail="entity type not found")
    slug = _slug(payload.name)
    conflict = await db.tags.find_one(tenant_filter(ctx.org_id, {
        "entity_type_id": et_id, "slug": slug,
    }))
    if conflict:
        return strip_id(conflict)  # idempotent create — return existing
    tid = str(uuid.uuid4())
    doc = {
        "_id": tid, "org_id": ctx.org_id, "entity_type_id": et_id,
        "name": payload.name.strip(), "slug": slug,
        "color": payload.color or _hex_color_for(payload.name),
        "usage_count": 0,
        "created_at": _now(), "updated_at": _now(), "deleted_at": None,
    }
    await db.tags.insert_one(doc)
    audit(bg, action="tag.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="tag", target_id=tid,
          diff={"name": payload.name, "entity_type_id": et_id}, request=request)
    return strip_id(doc)


@router.patch("/{tag_id}")
async def update_tag(
    tag_id: str,
    payload: TagUpdate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
        updates["slug"] = _slug(payload.name)
    if payload.color is not None:
        updates["color"] = payload.color
    if not updates:
        doc = await db.tags.find_one(tenant_filter(ctx.org_id, {"_id": tag_id}))
        if not doc:
            raise HTTPException(status_code=404, detail="tag not found")
        return strip_id(doc)
    updates["updated_at"] = _now()
    from pymongo import ReturnDocument
    doc = await db.tags.find_one_and_update(
        tenant_filter(ctx.org_id, {"_id": tag_id}),
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="tag not found")
    audit(bg, action="tag.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="tag", target_id=tag_id, diff=updates, request=request)
    return strip_id(doc)


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: str,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    now = _now()
    doc = await db.tags.find_one(tenant_filter(ctx.org_id, {"_id": tag_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="tag not found")
    await db.tags.update_one({"_id": tag_id}, {"$set": {"deleted_at": now, "updated_at": now}})
    # Remove this tag id from all records referencing it
    await db.records.update_many(
        tenant_filter(ctx.org_id, {"tag_ids": tag_id}),
        {"$pull": {"tag_ids": tag_id}},
    )
    audit(bg, action="tag.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="tag", target_id=tag_id, request=request)
    return None
