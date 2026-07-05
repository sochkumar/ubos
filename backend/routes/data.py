"""Phase 0 endpoints migrated to JWT-derived org context + RBAC.
Phase 2: adds category_ids + tag_ids on records, denormalized counters, and
        filter query params (category_id, tag_ids).
Phase 3-A: query_builder integration, activity + version snapshots, bulk actions,
           qr_payload materialisation, and a `POST records/search` endpoint."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pymongo import ReturnDocument

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import (
    BulkAction,
    EntityType, EntityTypeCreate, EntityTypeUpdate,
    FieldDef, FieldDefCreate, FieldDefUpdate,
    Record, RecordCreate, RecordSearchBody, RecordUpdate, ReorderPayload,
    strip_id,
)
from services.categories import descendant_ids_including_self
from services.history import emit_activity, snapshot_version
from services.query_builder import build_filter_query, build_sort_spec
from services.record_signals import (
    apply_record_diff, on_record_deleted, validate_ids_belong_to_org_and_et,
)
from validator import FieldValidator, ValidationErrors

router = APIRouter(tags=["data"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────── entity_types ───────────────────────
@router.get("/entity-types")
async def list_entity_types(ctx: AuthContext = Depends(require_permission("entity_types.read"))):
    db = get_db()
    cursor = db.entity_types.find(tenant_filter(ctx.org_id)).sort("created_at", 1)
    return [strip_id(d) for d in await cursor.to_list(1000)]


@router.post("/entity-types", status_code=201)
async def create_entity_type(
    payload: EntityTypeCreate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    if await db.entity_types.find_one(tenant_filter(ctx.org_id, {"key": payload.key})):
        raise HTTPException(status_code=409, detail=f"entity type with key '{payload.key}' already exists")
    et = EntityType(org_id=ctx.org_id, **payload.model_dump())
    doc = et.model_dump(by_alias=True)
    await db.entity_types.insert_one(doc)
    audit(bg, action="entity_type.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="entity_type", target_id=doc["_id"],
          diff={"key": payload.key, "name": payload.name_plural}, request=request)
    return strip_id(doc)


@router.get("/entity-types/{et_id}")
async def get_entity_type(et_id: str, ctx: AuthContext = Depends(require_permission("entity_types.read"))):
    doc = await get_db().entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="entity type not found")
    return strip_id(doc)


@router.patch("/entity-types/{et_id}")
async def update_entity_type(
    et_id: str, payload: EntityTypeUpdate, bg: BackgroundTasks, request: Request,
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
        {"$set": updates}, return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="entity type not found")
    audit(bg, action="entity_type.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="entity_type", target_id=et_id, diff=updates, request=request)
    return strip_id(doc)


@router.delete("/entity-types/{et_id}", status_code=204)
async def delete_entity_type(
    et_id: str, bg: BackgroundTasks, request: Request,
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
    for coll in ("field_definitions", "records", "categories", "relationship_definitions"):
        # relationship: cascade both from- and to- side
        if coll == "relationship_definitions":
            await db[coll].update_many(
                {"org_id": ctx.org_id, "deleted_at": None,
                 "$or": [{"from_entity_type_id": et_id}, {"to_entity_type_id": et_id}]},
                {"$set": {"deleted_at": now, "updated_at": now}},
            )
        else:
            await db[coll].update_many(
                tenant_filter(ctx.org_id, {"entity_type_id": et_id}),
                {"$set": {"deleted_at": now, "updated_at": now}},
            )
    audit(bg, action="entity_type.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="entity_type", target_id=et_id, request=request)
    return None


# ─────────────────────── fields ───────────────────────
@router.get("/entity-types/{et_id}/fields")
async def list_fields(et_id: str, ctx: AuthContext = Depends(require_permission("fields.read"))):
    db = get_db()
    if not await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1}):
        raise HTTPException(status_code=404, detail="entity type not found")
    cursor = db.field_definitions.find(
        tenant_filter(ctx.org_id, {"entity_type_id": et_id})
    ).sort([("order", 1), ("created_at", 1)])
    return [strip_id(d) for d in await cursor.to_list(1000)]


@router.post("/entity-types/{et_id}/fields", status_code=201)
async def create_field(
    et_id: str, payload: FieldDefCreate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("fields.manage")),
):
    db = get_db()
    if not await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1}):
        raise HTTPException(status_code=404, detail="entity type not found")
    if await db.field_definitions.find_one(tenant_filter(ctx.org_id, {"entity_type_id": et_id, "key": payload.key})):
        raise HTTPException(status_code=409, detail=f"field with key '{payload.key}' already exists")
    if not payload.order:
        last = await db.field_definitions.find(
            tenant_filter(ctx.org_id, {"entity_type_id": et_id})
        ).sort("order", -1).limit(1).to_list(1)
        next_order = (last[0]["order"] + 1) if last else 1
    else:
        next_order = payload.order
    fd = FieldDef(org_id=ctx.org_id, entity_type_id=et_id,
                  **{**payload.model_dump(), "order": next_order})
    doc = fd.model_dump(by_alias=True)
    await db.field_definitions.insert_one(doc)
    audit(bg, action="field.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="field", target_id=doc["_id"],
          diff={"key": payload.key, "type": payload.type, "entity_type_id": et_id}, request=request)
    return strip_id(doc)


@router.patch("/fields/{field_id}")
async def update_field(
    field_id: str, payload: FieldDefUpdate, bg: BackgroundTasks, request: Request,
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
        tenant_filter(ctx.org_id, {"_id": field_id}), {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="field not found")
    audit(bg, action="field.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="field", target_id=field_id, diff=updates, request=request)
    return strip_id(doc)


@router.delete("/fields/{field_id}", status_code=204)
async def delete_field(
    field_id: str, bg: BackgroundTasks, request: Request,
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
    et_id: str, payload: ReorderPayload,
    ctx: AuthContext = Depends(require_permission("fields.manage")),
):
    db = get_db()
    if not await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1}):
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
    return await db.field_definitions.find(tenant_filter(org_id, {"entity_type_id": et_id})).to_list(1000)


async def _next_record_number(db, org_id, et_id) -> str:
    doc = await db.entity_types.find_one_and_update(
        tenant_filter(org_id, {"_id": et_id}),
        {"$inc": {"record_counter": 1}, "$set": {"updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    return f"REC-{int(doc.get('record_counter', 1)):06d}"


def _derive_title(field_defs, values):
    for ftype in ("text", "email", "url", "phone", "longtext"):
        for fd in field_defs:
            if fd["type"] == ftype:
                v = values.get(fd["key"])
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return None


def _public_base() -> str:
    return (
        os.environ.get("PUBLIC_APP_URL")
        or os.environ.get("APP_BASE_URL")
        or ""
    ).rstrip("/")


async def _build_records_query(
    db, ctx: AuthContext, et_id: str,
    q: str | None,
    category_id: str | None,
    tag_ids: list[str] | None,
    filters: list[dict],
) -> dict:
    filt = tenant_filter(ctx.org_id, {"entity_type_id": et_id})
    if q:
        filt["$text"] = {"$search": q}
    if category_id:
        cat_ids = await descendant_ids_including_self(
            db, org_id=ctx.org_id, entity_type_id=et_id, cat_id=category_id,
        )
        filt["category_ids"] = {"$in": cat_ids} if cat_ids else category_id
    if tag_ids:
        filt["tag_ids"] = {"$in": tag_ids}
    if filters:
        defs = await _load_field_defs(db, ctx.org_id, et_id)
        defs_by_key = {d["key"]: d for d in defs}
        extra = build_filter_query(filters, defs_by_key)
        if extra:
            filt = {"$and": [filt, extra]}
    return filt


@router.get("/entity-types/{et_id}/records")
async def list_records(
    et_id: str,
    q: str | None = Query(default=None),
    category_id: str | None = Query(default=None),
    tag_ids: list[str] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    if not await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1}):
        raise HTTPException(status_code=404, detail="entity type not found")
    filt = await _build_records_query(db, ctx, et_id, q, category_id, tag_ids, [])
    total = await db.records.count_documents(filt)
    cursor = db.records.find(filt).sort("created_at", -1).skip(skip).limit(limit)
    items = [strip_id(d) for d in await cursor.to_list(limit)]
    return {"total": total, "items": items}


@router.post("/entity-types/{et_id}/records/search")
async def search_records(
    et_id: str, body: RecordSearchBody,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    if not await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1}):
        raise HTTPException(status_code=404, detail="entity type not found")

    # If a view_id is provided we hydrate the view's saved state as *base*, then
    # apply any additional runtime overrides from the body (so users can tweak
    # while staying on a view).
    base_q = body.q
    base_cat = body.category_id
    base_tags = list(body.tag_ids or [])
    base_filters = [f.model_dump() for f in body.filters]
    base_sort = [s.model_dump() for s in body.sort]
    if body.view_id:
        view = await db.views.find_one({
            "_id": body.view_id, "org_id": ctx.org_id, "entity_type_id": et_id,
            "deleted_at": None,
            "$or": [{"user_id": ctx.user["_id"]}, {"is_shared": True}],
        })
        if not view:
            raise HTTPException(404, "view not found")
        if not body.q:
            base_q = view.get("q")
        if not base_cat:
            base_cat = (view.get("category_ids") or [None])[0]
        if not base_tags:
            base_tags = view.get("tag_ids") or []
        if not base_filters:
            base_filters = view.get("filters") or []
        if not base_sort:
            base_sort = view.get("sort") or []

    filt = await _build_records_query(db, ctx, et_id, base_q, base_cat, base_tags, base_filters)
    sort_spec = build_sort_spec(base_sort)
    total = await db.records.count_documents(filt)
    cursor = db.records.find(filt).sort(sort_spec).skip(body.skip).limit(body.limit)
    items = [strip_id(d) for d in await cursor.to_list(body.limit)]
    return {"total": total, "items": items}


@router.post("/entity-types/{et_id}/records", status_code=201)
async def create_record(
    et_id: str, payload: RecordCreate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.create")),
):
    db = get_db()
    if not await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1}):
        raise HTTPException(status_code=404, detail="entity type not found")
    field_defs = await _load_field_defs(db, ctx.org_id, et_id)
    validator = FieldValidator(db, ctx.org_id, et_id)
    try:
        coerced, search_text = await validator.validate(field_defs, payload.fields or {})
    except ValidationErrors as e:
        raise HTTPException(status_code=422, detail={"errors": e.errors})

    cats, tags = await validate_ids_belong_to_org_and_et(
        db, org_id=ctx.org_id, entity_type_id=et_id,
        category_ids=payload.category_ids or [], tag_ids=payload.tag_ids or [],
    )

    record_number = await _next_record_number(db, ctx.org_id, et_id)
    title = payload.title or _derive_title(field_defs, coerced) or record_number
    search_text = f"{title} {payload.description or ''} {search_text}".strip()

    rec = Record(
        org_id=ctx.org_id, entity_type_id=et_id, title=title,
        description=payload.description, fields=coerced,
        category_ids=cats, tag_ids=tags,
        record_number=record_number, search_text=search_text,
    )
    doc = rec.model_dump(by_alias=True)
    base = _public_base()
    doc["qr_payload"] = f"{base}/r/{doc['_id']}" if base else f"/r/{doc['_id']}"
    await db.records.insert_one(doc)

    await apply_record_diff(
        db, org_id=ctx.org_id,
        old_category_ids=[], new_category_ids=cats,
        old_tag_ids=[], new_tag_ids=tags,
    )
    # v1 snapshot + created activity
    await snapshot_version(db, record=doc, actor_id=ctx.user["_id"], reason="created")
    await emit_activity(
        db, record=doc, actor_id=ctx.user["_id"],
        actor_name=ctx.user.get("name") or ctx.user.get("email"),
        type="created", payload={"record_number": record_number},
    )
    audit(bg, action="record.created", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="record", target_id=doc["_id"],
          diff={"entity_type_id": et_id, "record_number": record_number,
                "categories": len(cats), "tags": len(tags)}, request=request)
    return strip_id(doc)


@router.get("/records/{rec_id}")
async def get_record(rec_id: str, ctx: AuthContext = Depends(require_permission("records.read"))):
    doc = await get_db().records.find_one(tenant_filter(ctx.org_id, {"_id": rec_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="record not found")
    return strip_id(doc)


def _compute_diff(old_fields: dict, new_fields: dict) -> dict:
    changed = {}
    keys = set(old_fields or {}) | set(new_fields or {})
    for k in keys:
        a = (old_fields or {}).get(k)
        b = (new_fields or {}).get(k)
        if a != b:
            changed[k] = {"before": a, "after": b}
    return changed


@router.patch("/records/{rec_id}")
async def update_record(
    rec_id: str, payload: RecordUpdate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    db = get_db()
    current = await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rec_id}))
    if not current:
        raise HTTPException(status_code=404, detail="record not found")

    # Snapshot pre-update state so restore-to-previous works
    await snapshot_version(db, record=current, actor_id=ctx.user["_id"], reason="pre-update")

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

    old_cats = current.get("category_ids", []) or []
    old_tags = current.get("tag_ids", []) or []
    new_cats, new_tags = old_cats, old_tags
    if payload.category_ids is not None or payload.tag_ids is not None:
        req_cats = payload.category_ids if payload.category_ids is not None else old_cats
        req_tags = payload.tag_ids if payload.tag_ids is not None else old_tags
        new_cats, new_tags = await validate_ids_belong_to_org_and_et(
            db, org_id=ctx.org_id, entity_type_id=current["entity_type_id"],
            category_ids=req_cats, tag_ids=req_tags,
        )
        updates["category_ids"] = new_cats
        updates["tag_ids"] = new_tags

    updates["version"] = int(current.get("version", 1)) + 1
    doc = await db.records.find_one_and_update(
        tenant_filter(ctx.org_id, {"_id": rec_id}),
        {"$set": updates}, return_document=ReturnDocument.AFTER,
    )

    if new_cats != old_cats or new_tags != old_tags:
        await apply_record_diff(
            db, org_id=ctx.org_id,
            old_category_ids=old_cats, new_category_ids=new_cats,
            old_tag_ids=old_tags, new_tag_ids=new_tags,
        )

    field_diff = _compute_diff(current.get("fields", {}), doc.get("fields", {}))
    await emit_activity(
        db, record=doc, actor_id=ctx.user["_id"],
        actor_name=ctx.user.get("name") or ctx.user.get("email"),
        type="updated",
        payload={"diff": field_diff, "version": doc.get("version")},
    )
    audit(bg, action="record.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="record", target_id=rec_id,
          diff={"version": updates["version"]}, request=request)
    return strip_id(doc)


@router.delete("/records/{rec_id}", status_code=204)
async def delete_record(
    rec_id: str, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.delete")),
):
    db = get_db()
    now = _now()
    current = await db.records.find_one(tenant_filter(ctx.org_id, {"_id": rec_id}))
    if not current:
        raise HTTPException(status_code=404, detail="record not found")
    await db.records.update_one(
        {"_id": rec_id}, {"$set": {"deleted_at": now, "updated_at": now}}
    )
    await on_record_deleted(
        db, org_id=ctx.org_id,
        category_ids=current.get("category_ids") or [],
        tag_ids=current.get("tag_ids") or [],
    )
    await emit_activity(
        db, record=current, actor_id=ctx.user["_id"],
        actor_name=ctx.user.get("name") or ctx.user.get("email"),
        type="deleted", payload={"record_number": current.get("record_number")},
    )
    audit(bg, action="record.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="record", target_id=rec_id, request=request)
    return None


# ─────────────────────── bulk actions ───────────────────────
@router.post("/entity-types/{et_id}/records/bulk")
async def bulk_records(
    et_id: str, body: BulkAction, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(ctx.org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(404, "entity type not found")
    ids = list(dict.fromkeys(body.ids))  # dedupe
    if not ids:
        raise HTTPException(422, "ids is required")

    records = await db.records.find(
        tenant_filter(ctx.org_id, {"_id": {"$in": ids}, "entity_type_id": et_id}),
    ).to_list(1000)
    if not records:
        return {"updated": 0, "skipped": len(ids)}

    actor_name = ctx.user.get("name") or ctx.user.get("email")
    now = _now()

    if body.action == "delete":
        if "records.delete" not in ctx.permissions:
            raise HTTPException(403, "missing permission: records.delete")
        rids = [r["_id"] for r in records]
        await db.records.update_many(
            {"_id": {"$in": rids}, "org_id": ctx.org_id},
            {"$set": {"deleted_at": now, "updated_at": now}},
        )
        for r in records:
            await on_record_deleted(
                db, org_id=ctx.org_id,
                category_ids=r.get("category_ids") or [],
                tag_ids=r.get("tag_ids") or [],
            )
            await emit_activity(
                db, record=r, actor_id=ctx.user["_id"], actor_name=actor_name,
                type="deleted", payload={"bulk": True},
            )
        audit(bg, action="record.bulk_deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
              target_type="entity_type", target_id=et_id,
              diff={"count": len(rids)}, request=request)
        return {"updated": len(rids), "skipped": len(ids) - len(rids)}

    if body.action == "assign_categories":
        mode = body.payload.get("mode", "add")  # add | remove | replace
        raw_ids = body.payload.get("category_ids") or []
        # validate that all cat ids belong to this org+et
        valid = await db.categories.find(
            tenant_filter(ctx.org_id, {"entity_type_id": et_id, "_id": {"$in": raw_ids}}),
            {"_id": 1},
        ).to_list(1000)
        cat_ids = [d["_id"] for d in valid]
        updated = 0
        for r in records:
            old = r.get("category_ids") or []
            if mode == "replace":
                new = list(cat_ids)
            elif mode == "remove":
                new = [x for x in old if x not in cat_ids]
            else:
                new = list(dict.fromkeys([*old, *cat_ids]))
            if set(new) == set(old):
                continue
            await db.records.update_one(
                {"_id": r["_id"], "org_id": ctx.org_id},
                {"$set": {"category_ids": new, "updated_at": now,
                          "version": int(r.get("version", 1)) + 1}},
            )
            await apply_record_diff(
                db, org_id=ctx.org_id,
                old_category_ids=old, new_category_ids=new,
                old_tag_ids=r.get("tag_ids") or [], new_tag_ids=r.get("tag_ids") or [],
            )
            await emit_activity(
                db, record=r, actor_id=ctx.user["_id"], actor_name=actor_name,
                type="updated", payload={"bulk": True, "categories": {"before": old, "after": new}},
            )
            updated += 1
        audit(bg, action="record.bulk_categorized", actor_id=ctx.user["_id"], org_id=ctx.org_id,
              target_type="entity_type", target_id=et_id,
              diff={"count": updated, "mode": mode}, request=request)
        return {"updated": updated, "skipped": len(ids) - updated}

    if body.action == "assign_tags":
        mode = body.payload.get("mode", "add")
        raw_ids = body.payload.get("tag_ids") or []
        valid = await db.tags.find(
            tenant_filter(ctx.org_id, {
                "_id": {"$in": raw_ids},
                "$or": [{"entity_type_id": None}, {"entity_type_id": et_id}],
            }),
            {"_id": 1},
        ).to_list(1000)
        tag_ids = [d["_id"] for d in valid]
        updated = 0
        for r in records:
            old = r.get("tag_ids") or []
            if mode == "replace":
                new = list(tag_ids)
            elif mode == "remove":
                new = [x for x in old if x not in tag_ids]
            else:
                new = list(dict.fromkeys([*old, *tag_ids]))
            if set(new) == set(old):
                continue
            await db.records.update_one(
                {"_id": r["_id"], "org_id": ctx.org_id},
                {"$set": {"tag_ids": new, "updated_at": now,
                          "version": int(r.get("version", 1)) + 1}},
            )
            await apply_record_diff(
                db, org_id=ctx.org_id,
                old_category_ids=r.get("category_ids") or [], new_category_ids=r.get("category_ids") or [],
                old_tag_ids=old, new_tag_ids=new,
            )
            await emit_activity(
                db, record=r, actor_id=ctx.user["_id"], actor_name=actor_name,
                type="updated", payload={"bulk": True, "tags": {"before": old, "after": new}},
            )
            updated += 1
        audit(bg, action="record.bulk_tagged", actor_id=ctx.user["_id"], org_id=ctx.org_id,
              target_type="entity_type", target_id=et_id,
              diff={"count": updated, "mode": mode}, request=request)
        return {"updated": updated, "skipped": len(ids) - updated}

    if body.action == "update_field":
        BULK_ALLOWED = {"text","longtext","number","currency","boolean","dropdown",
                        "date","datetime","email","phone","url"}
        key = body.payload.get("field_key")
        value = body.payload.get("value")
        if not key:
            raise HTTPException(422, "field_key is required")
        defs = await _load_field_defs(db, ctx.org_id, et_id)
        fdef = next((d for d in defs if d["key"] == key), None)
        if not fdef:
            raise HTTPException(422, f"unknown field '{key}'")
        if fdef["type"] not in BULK_ALLOWED:
            raise HTTPException(422, f"field type '{fdef['type']}' is not supported in Bulk Edit")
        if fdef.get("unique") and len(records) > 1 and value not in (None, ""):
            raise HTTPException(422, "cannot bulk-set a unique field to the same value on multiple records")
        validator = FieldValidator(db, ctx.org_id, et_id)
        updated = 0
        skipped = 0
        for r in records:
            merged = {**r.get("fields", {}), key: value}
            try:
                coerced, search_text = await validator.validate(defs, merged, exclude_record_id=r["_id"])
            except ValidationErrors:
                skipped += 1
                continue
            title = r.get("title") or _derive_title(defs, coerced) or r.get("record_number")
            new_st = f"{title} {r.get('description') or ''} {search_text}".strip()
            await db.records.update_one(
                {"_id": r["_id"], "org_id": ctx.org_id},
                {"$set": {"fields": coerced, "search_text": new_st,
                          "updated_at": now, "version": int(r.get("version", 1)) + 1}},
            )
            await emit_activity(
                db, record=r, actor_id=ctx.user["_id"], actor_name=actor_name,
                type="updated", payload={"bulk": True, "field": key,
                                          "before": (r.get("fields") or {}).get(key), "after": coerced.get(key)},
            )
            updated += 1
        audit(bg, action="record.bulk_field_updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
              target_type="entity_type", target_id=et_id,
              diff={"count": updated, "field": key}, request=request)
        return {"updated": updated, "skipped": skipped + (len(ids) - len(records))}

    raise HTTPException(422, f"unknown action '{body.action}'")
