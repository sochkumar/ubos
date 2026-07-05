"""Phase 0 endpoints migrated to JWT-derived org context + RBAC."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pymongo import ReturnDocument

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import (
    EntityType,
    EntityTypeCreate,
    EntityTypeUpdate,
    FieldDef,
    FieldDefCreate,
    FieldDefUpdate,
    Record,
    RecordCreate,
    RecordUpdate,
    ReorderPayload,
    strip_id,
)
from validator import FieldValidator, ValidationErrors

router = APIRouter(tags=["data"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────── entity_types ───────────────────────
@router.get("/entity-types")
async def list_entity_types(
    ctx: AuthContext = Depends(require_permission("entity_types.read")),
):
    db = get_db()
    cursor = db.entity_types.find(tenant_filter(ctx.org_id)).sort("created_at", 1)
    return [strip_id(d) for d in await cursor.to_list(1000)]


@router.post("/entity-types", status_code=201)
async def create_entity_type(
    payload: EntityTypeCreate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    existing = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"key": payload.key}))
    if existing:
        raise HTTPException(status_code=409, detail=f"entity type with key '{payload.key}' already exists")
    et = EntityType(org_id=ctx.org_id, **payload.model_dump())
    doc = et.model_dump(by_alias=True)
    await db.entity_types.insert_one(doc)
    audit(bg, action="entity_type.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="entity_type", target_id=doc["_id"],
          diff={"key": payload.key, "name": payload.name_plural}, request=request)
    return strip_id(doc)


@router.get("/entity-types/{et_id}")
async def get_entity_type(
    et_id: str, ctx: AuthContext = Depends(require_permission("entity_types.read"))
):
    db = get_db()
    doc = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="entity type not found")
    return strip_id(doc)


@router.patch("/entity-types/{et_id}")
async def update_entity_type(
    et_id: str,
    payload: EntityTypeUpdate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        doc = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}))
        if not doc:
            raise HTTPException(status_code=404, detail="entity type not found")
        return strip_id(doc)
    updates["updated_at"] = _now()
    doc = await db.entity_types.find_one_and_update(
        tenant_filter(ctx.org_id, {"_id": et_id}),
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="entity type not found")
    audit(bg, action="entity_type.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="entity_type", target_id=et_id, diff=updates, request=request)
    return strip_id(doc)


@router.delete("/entity-types/{et_id}", status_code=204)
async def delete_entity_type(
    et_id: str,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    now = _now()
    res = await db.entity_types.update_one(
        tenant_filter(ctx.org_id, {"_id": et_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="entity type not found")
    await db.field_definitions.update_many(
        tenant_filter(ctx.org_id, {"entity_type_id": et_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    await db.records.update_many(
        tenant_filter(ctx.org_id, {"entity_type_id": et_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    audit(bg, action="entity_type.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="entity_type", target_id=et_id, request=request)
    return None


# ─────────────────────── fields ───────────────────────
@router.get("/entity-types/{et_id}/fields")
async def list_fields(
    et_id: str, ctx: AuthContext = Depends(require_permission("fields.read"))
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    cursor = db.field_definitions.find(
        tenant_filter(ctx.org_id, {"entity_type_id": et_id})
    ).sort([("order", 1), ("created_at", 1)])
    return [strip_id(d) for d in await cursor.to_list(1000)]


@router.post("/entity-types/{et_id}/fields", status_code=201)
async def create_field(
    et_id: str,
    payload: FieldDefCreate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("fields.manage")),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    conflict = await db.field_definitions.find_one(
        tenant_filter(ctx.org_id, {"entity_type_id": et_id, "key": payload.key})
    )
    if conflict:
        raise HTTPException(status_code=409, detail=f"field with key '{payload.key}' already exists")
    if not payload.order:
        last = await db.field_definitions.find(
            tenant_filter(ctx.org_id, {"entity_type_id": et_id})
        ).sort("order", -1).limit(1).to_list(1)
        next_order = (last[0]["order"] + 1) if last else 1
    else:
        next_order = payload.order
    fd = FieldDef(
        org_id=ctx.org_id, entity_type_id=et_id,
        **{**payload.model_dump(), "order": next_order},
    )
    doc = fd.model_dump(by_alias=True)
    await db.field_definitions.insert_one(doc)
    audit(bg, action="field.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="field", target_id=doc["_id"],
          diff={"key": payload.key, "type": payload.type, "entity_type_id": et_id},
          request=request)
    return strip_id(doc)


@router.patch("/fields/{field_id}")
async def update_field(
    field_id: str,
    payload: FieldDefUpdate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("fields.manage")),
):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        doc = await db.field_definitions.find_one(tenant_filter(ctx.org_id, {"_id": field_id}))
        if not doc:
            raise HTTPException(status_code=404, detail="field not found")
        return strip_id(doc)
    updates["updated_at"] = _now()
    doc = await db.field_definitions.find_one_and_update(
        tenant_filter(ctx.org_id, {"_id": field_id}),
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="field not found")
    audit(bg, action="field.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="field", target_id=field_id, diff=updates, request=request)
    return strip_id(doc)


@router.delete("/fields/{field_id}", status_code=204)
async def delete_field(
    field_id: str,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("fields.manage")),
):
    db = get_db()
    now = _now()
    res = await db.field_definitions.update_one(
        tenant_filter(ctx.org_id, {"_id": field_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="field not found")
    audit(bg, action="field.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="field", target_id=field_id, request=request)
    return None


@router.post("/entity-types/{et_id}/fields/reorder")
async def reorder_fields(
    et_id: str,
    payload: ReorderPayload,
    ctx: AuthContext = Depends(require_permission("fields.manage")),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    now = _now()
    for idx, fid in enumerate(payload.order, start=1):
        await db.field_definitions.update_one(
            tenant_filter(ctx.org_id, {"_id": fid, "entity_type_id": et_id}),
            {"$set": {"order": idx, "updated_at": now}},
        )
    cursor = db.field_definitions.find(
        tenant_filter(ctx.org_id, {"entity_type_id": et_id})
    ).sort("order", 1)
    return [strip_id(d) for d in await cursor.to_list(1000)]


# ─────────────────────── records ───────────────────────
async def _load_field_defs(db, org_id, et_id):
    cursor = db.field_definitions.find(tenant_filter(org_id, {"entity_type_id": et_id}))
    return await cursor.to_list(1000)


async def _next_record_number(db, org_id, et_id) -> str:
    doc = await db.entity_types.find_one_and_update(
        tenant_filter(org_id, {"_id": et_id}),
        {"$inc": {"record_counter": 1}, "$set": {"updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    n = int(doc.get("record_counter", 1))
    return f"REC-{n:06d}"


def _derive_title(field_defs, values):
    priority = ("text", "email", "url", "phone", "longtext")
    for ftype in priority:
        for fd in field_defs:
            if fd["type"] == ftype:
                v = values.get(fd["key"])
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return None


@router.get("/entity-types/{et_id}/records")
async def list_records(
    et_id: str,
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    filt = tenant_filter(ctx.org_id, {"entity_type_id": et_id})
    if q:
        filt["$text"] = {"$search": q}
    total = await db.records.count_documents(filt)
    cursor = db.records.find(filt).sort("created_at", -1).skip(skip).limit(limit)
    items = [strip_id(d) for d in await cursor.to_list(limit)]
    return {"total": total, "items": items}


@router.post("/entity-types/{et_id}/records", status_code=201)
async def create_record(
    et_id: str,
    payload: RecordCreate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("records.create")),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    field_defs = await _load_field_defs(db, ctx.org_id, et_id)
    validator = FieldValidator(db, ctx.org_id, et_id)
    try:
        coerced, search_text = await validator.validate(field_defs, payload.fields or {})
    except ValidationErrors as e:
        raise HTTPException(status_code=422, detail={"errors": e.errors})
    record_number = await _next_record_number(db, ctx.org_id, et_id)
    title = payload.title or _derive_title(field_defs, coerced) or record_number
    search_text = f"{title} {payload.description or ''} {search_text}".strip()
    rec = Record(
        org_id=ctx.org_id, entity_type_id=et_id,
        title=title, description=payload.description,
        fields=coerced, record_number=record_number, search_text=search_text,
    )
    doc = rec.model_dump(by_alias=True)
    await db.records.insert_one(doc)
    audit(bg, action="record.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="record", target_id=doc["_id"],
          diff={"entity_type_id": et_id, "record_number": record_number}, request=request)
    return strip_id(doc)


@router.get("/records/{rec_id}")
async def get_record(
    rec_id: str, ctx: AuthContext = Depends(require_permission("records.read"))
):
    db = get_db()
    doc = await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rec_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="record not found")
    return strip_id(doc)


@router.patch("/records/{rec_id}")
async def update_record(
    rec_id: str,
    payload: RecordUpdate,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    db = get_db()
    current = await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rec_id}))
    if not current:
        raise HTTPException(status_code=404, detail="record not found")
    updates: dict = {"updated_at": _now()}
    if payload.fields is not None:
        et_id = current["entity_type_id"]
        field_defs = await _load_field_defs(db, ctx.org_id, et_id)
        validator = FieldValidator(db, ctx.org_id, et_id)
        merged = {**current.get("fields", {}), **payload.fields}
        try:
            coerced, search_text = await validator.validate(field_defs, merged, exclude_record_id=rec_id)
        except ValidationErrors as e:
            raise HTTPException(status_code=422, detail={"errors": e.errors})
        updates["fields"] = coerced
        title = payload.title or current.get("title") or _derive_title(field_defs, coerced) or current.get("record_number")
        updates["title"] = title
        updates["search_text"] = f"{title} {payload.description or current.get('description') or ''} {search_text}".strip()
    if payload.title is not None and "title" not in updates:
        updates["title"] = payload.title
    if payload.description is not None:
        updates["description"] = payload.description
    updates["version"] = int(current.get("version", 1)) + 1
    doc = await db.records.find_one_and_update(
        tenant_filter(ctx.org_id, {"_id": rec_id}),
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    audit(bg, action="record.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="record", target_id=rec_id, diff={"version": updates["version"]}, request=request)
    return strip_id(doc)


@router.delete("/records/{rec_id}", status_code=204)
async def delete_record(
    rec_id: str,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("records.delete")),
):
    db = get_db()
    now = _now()
    res = await db.records.update_one(
        tenant_filter(ctx.org_id, {"_id": rec_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="record not found")
    audit(bg, action="record.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="record", target_id=rec_id, request=request)
    return None
