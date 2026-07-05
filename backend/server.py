"""UBOS Phase 0 — Metadata Engine + Dynamic Records POC.

Single-file FastAPI app that exposes:
- entity_types CRUD
- field_definitions CRUD (+ reorder)
- records CRUD (dynamic, validated by FieldValidator)
- /api/dev/seed-demo (Products + Machines)
- /api/health
- OpenAPI at /api/openapi.json

All queries are tenant-scoped via `tenant_filter(org_id)`. The `org_id` comes
from the `X-Org-Id` header and defaults to `demo-org` (Phase 0 has no auth).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pymongo import ReturnDocument
from starlette.middleware.cors import CORSMiddleware

from db import ensure_indexes, get_db, tenant_filter
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

DEFAULT_ORG_ID = "demo-org"

app = FastAPI(
    title="UBOS API",
    version="0.1.0-phase0",
    description="Universal Business Operating System — Phase 0 (metadata engine + dynamic records).",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ubos")


# ─────────────────────── tenant dependency ───────────────────────
async def get_org(x_org_id: str | None = Header(default=None, alias="X-Org-Id")) -> str:
    return (x_org_id or "").strip() or DEFAULT_ORG_ID


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────── health ───────────────────────
@router.get("/health")
async def health():
    db = get_db()
    try:
        await db.command("ping")
        return {"status": "ok", "db": "up"}
    except Exception as e:  # pragma: no cover
        return JSONResponse({"status": "degraded", "db": "down", "error": str(e)}, status_code=503)


# ─────────────────────── entity_types ───────────────────────
@router.get("/entity-types")
async def list_entity_types(org_id: str = Depends(get_org)):
    db = get_db()
    cursor = db.entity_types.find(tenant_filter(org_id)).sort("created_at", 1)
    return [strip_id(d) for d in await cursor.to_list(1000)]


@router.post("/entity-types", status_code=201)
async def create_entity_type(payload: EntityTypeCreate, org_id: str = Depends(get_org)):
    db = get_db()
    existing = await db.entity_types.find_one(tenant_filter(org_id, {"key": payload.key}))
    if existing:
        raise HTTPException(status_code=409, detail=f"entity type with key '{payload.key}' already exists")
    et = EntityType(org_id=org_id, **payload.model_dump())
    doc = et.model_dump(by_alias=True)
    await db.entity_types.insert_one(doc)
    return strip_id(doc)


@router.get("/entity-types/{et_id}")
async def get_entity_type(et_id: str, org_id: str = Depends(get_org)):
    db = get_db()
    doc = await db.entity_types.find_one(tenant_filter(org_id, {"_id": et_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="entity type not found")
    return strip_id(doc)


@router.patch("/entity-types/{et_id}")
async def update_entity_type(et_id: str, payload: EntityTypeUpdate, org_id: str = Depends(get_org)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        doc = await db.entity_types.find_one(tenant_filter(org_id, {"_id": et_id}))
        if not doc:
            raise HTTPException(status_code=404, detail="entity type not found")
        return strip_id(doc)
    updates["updated_at"] = _now()
    doc = await db.entity_types.find_one_and_update(
        tenant_filter(org_id, {"_id": et_id}),
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="entity type not found")
    return strip_id(doc)


@router.delete("/entity-types/{et_id}", status_code=204)
async def delete_entity_type(et_id: str, org_id: str = Depends(get_org)):
    db = get_db()
    now = _now()
    res = await db.entity_types.update_one(
        tenant_filter(org_id, {"_id": et_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="entity type not found")
    # cascade soft-delete fields + records
    await db.field_definitions.update_many(
        tenant_filter(org_id, {"entity_type_id": et_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    await db.records.update_many(
        tenant_filter(org_id, {"entity_type_id": et_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    return None


# ─────────────────────── field_definitions ───────────────────────
@router.get("/entity-types/{et_id}/fields")
async def list_fields(et_id: str, org_id: str = Depends(get_org)):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    cursor = db.field_definitions.find(
        tenant_filter(org_id, {"entity_type_id": et_id})
    ).sort([("order", 1), ("created_at", 1)])
    return [strip_id(d) for d in await cursor.to_list(1000)]


@router.post("/entity-types/{et_id}/fields", status_code=201)
async def create_field(et_id: str, payload: FieldDefCreate, org_id: str = Depends(get_org)):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    conflict = await db.field_definitions.find_one(
        tenant_filter(org_id, {"entity_type_id": et_id, "key": payload.key})
    )
    if conflict:
        raise HTTPException(
            status_code=409, detail=f"field with key '{payload.key}' already exists"
        )
    # If no explicit order supplied, append to end
    if not payload.order:
        last = await db.field_definitions.find(
            tenant_filter(org_id, {"entity_type_id": et_id})
        ).sort("order", -1).limit(1).to_list(1)
        next_order = (last[0]["order"] + 1) if last else 1
    else:
        next_order = payload.order
    fd = FieldDef(
        org_id=org_id,
        entity_type_id=et_id,
        **{**payload.model_dump(), "order": next_order},
    )
    doc = fd.model_dump(by_alias=True)
    await db.field_definitions.insert_one(doc)
    return strip_id(doc)


@router.patch("/fields/{field_id}")
async def update_field(field_id: str, payload: FieldDefUpdate, org_id: str = Depends(get_org)):
    db = get_db()
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        doc = await db.field_definitions.find_one(tenant_filter(org_id, {"_id": field_id}))
        if not doc:
            raise HTTPException(status_code=404, detail="field not found")
        return strip_id(doc)
    updates["updated_at"] = _now()
    doc = await db.field_definitions.find_one_and_update(
        tenant_filter(org_id, {"_id": field_id}),
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="field not found")
    return strip_id(doc)


@router.delete("/fields/{field_id}", status_code=204)
async def delete_field(field_id: str, org_id: str = Depends(get_org)):
    db = get_db()
    now = _now()
    res = await db.field_definitions.update_one(
        tenant_filter(org_id, {"_id": field_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="field not found")
    return None


@router.post("/entity-types/{et_id}/fields/reorder")
async def reorder_fields(
    et_id: str, payload: ReorderPayload, org_id: str = Depends(get_org)
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    now = _now()
    for idx, fid in enumerate(payload.order, start=1):
        await db.field_definitions.update_one(
            tenant_filter(org_id, {"_id": fid, "entity_type_id": et_id}),
            {"$set": {"order": idx, "updated_at": now}},
        )
    cursor = db.field_definitions.find(
        tenant_filter(org_id, {"entity_type_id": et_id})
    ).sort("order", 1)
    return [strip_id(d) for d in await cursor.to_list(1000)]


# ─────────────────────── records ───────────────────────
async def _load_field_defs(db, org_id: str, et_id: str) -> list[dict]:
    cursor = db.field_definitions.find(tenant_filter(org_id, {"entity_type_id": et_id}))
    return await cursor.to_list(1000)


async def _next_record_number(db, org_id: str, et_id: str) -> str:
    doc = await db.entity_types.find_one_and_update(
        tenant_filter(org_id, {"_id": et_id}),
        {"$inc": {"record_counter": 1}, "$set": {"updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    n = int(doc.get("record_counter", 1))
    return f"REC-{n:06d}"


@router.get("/entity-types/{et_id}/records")
async def list_records(
    et_id: str,
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
    org_id: str = Depends(get_org),
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    filt = tenant_filter(org_id, {"entity_type_id": et_id})
    if q:
        filt["$text"] = {"$search": q}
    total = await db.records.count_documents(filt)
    cursor = db.records.find(filt).sort("created_at", -1).skip(skip).limit(limit)
    items = [strip_id(d) for d in await cursor.to_list(limit)]
    return {"total": total, "items": items}


@router.post("/entity-types/{et_id}/records", status_code=201)
async def create_record(
    et_id: str, payload: RecordCreate, org_id: str = Depends(get_org)
):
    db = get_db()
    et = await db.entity_types.find_one(tenant_filter(org_id, {"_id": et_id}), {"_id": 1})
    if not et:
        raise HTTPException(status_code=404, detail="entity type not found")
    field_defs = await _load_field_defs(db, org_id, et_id)
    validator = FieldValidator(db, org_id, et_id)
    try:
        coerced, search_text = await validator.validate(field_defs, payload.fields or {})
    except ValidationErrors as e:
        raise HTTPException(status_code=422, detail={"errors": e.errors})

    record_number = await _next_record_number(db, org_id, et_id)
    title = payload.title or _derive_title(field_defs, coerced) or record_number
    search_text = f"{title} {payload.description or ''} {search_text}".strip()

    rec = Record(
        org_id=org_id,
        entity_type_id=et_id,
        title=title,
        description=payload.description,
        fields=coerced,
        record_number=record_number,
        search_text=search_text,
    )
    doc = rec.model_dump(by_alias=True)
    await db.records.insert_one(doc)
    return strip_id(doc)


@router.get("/records/{rec_id}")
async def get_record(rec_id: str, org_id: str = Depends(get_org)):
    db = get_db()
    doc = await db.records.find_one(tenant_filter(org_id, {"_id": rec_id}))
    if not doc:
        raise HTTPException(status_code=404, detail="record not found")
    return strip_id(doc)


@router.patch("/records/{rec_id}")
async def update_record(rec_id: str, payload: RecordUpdate, org_id: str = Depends(get_org)):
    db = get_db()
    current = await db.records.find_one(tenant_filter(org_id, {"_id": rec_id}))
    if not current:
        raise HTTPException(status_code=404, detail="record not found")

    updates: dict = {"updated_at": _now()}

    if payload.fields is not None:
        et_id = current["entity_type_id"]
        field_defs = await _load_field_defs(db, org_id, et_id)
        validator = FieldValidator(db, org_id, et_id)
        merged = {**current.get("fields", {}), **payload.fields}
        try:
            coerced, search_text = await validator.validate(
                field_defs, merged, exclude_record_id=rec_id
            )
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
        tenant_filter(org_id, {"_id": rec_id}),
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    return strip_id(doc)


@router.delete("/records/{rec_id}", status_code=204)
async def delete_record(rec_id: str, org_id: str = Depends(get_org)):
    db = get_db()
    now = _now()
    res = await db.records.update_one(
        tenant_filter(org_id, {"_id": rec_id}),
        {"$set": {"deleted_at": now, "updated_at": now}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="record not found")
    return None


def _derive_title(field_defs: list[dict], values: dict) -> str | None:
    """Pick the first non-empty text-ish field to use as the record title."""
    priority = ("text", "email", "url", "phone", "longtext")
    for ftype in priority:
        for fd in field_defs:
            if fd["type"] == ftype:
                v = values.get(fd["key"])
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return None


# ─────────────────────── dev seed ───────────────────────
@router.post("/dev/seed-demo")
async def seed_demo(org_id: str = Depends(get_org)):
    """Idempotent-ish demo seed: Products + Machines entity types with fields
    and a few sample records. Safe to call more than once (only creates missing)."""
    db = get_db()
    result = {"entity_types": [], "created_records": 0}

    async def upsert_et(spec: dict) -> dict:
        existing = await db.entity_types.find_one(
            tenant_filter(org_id, {"key": spec["key"]})
        )
        if existing:
            result["entity_types"].append({"key": spec["key"], "created": False, "id": existing["_id"]})
            return existing
        et = EntityType(org_id=org_id, **spec)
        doc = et.model_dump(by_alias=True)
        await db.entity_types.insert_one(doc)
        result["entity_types"].append({"key": spec["key"], "created": True, "id": doc["_id"]})
        return doc

    async def upsert_field(et_id: str, spec: dict) -> dict:
        existing = await db.field_definitions.find_one(
            tenant_filter(org_id, {"entity_type_id": et_id, "key": spec["key"]})
        )
        if existing:
            return existing
        fd = FieldDef(org_id=org_id, entity_type_id=et_id, **spec)
        doc = fd.model_dump(by_alias=True)
        await db.field_definitions.insert_one(doc)
        return doc

    # Products
    products_et = await upsert_et({
        "key": "products",
        "name_singular": "Product",
        "name_plural": "Products",
        "icon": "Package",
        "color": "#0f766e",
        "description": "Physical products in the catalog",
    })
    products_fields = [
        {"key": "sku", "label": "SKU", "type": "text", "required": True, "unique": True, "order": 1},
        {"key": "price", "label": "Price", "type": "currency", "required": True, "config": {"min": 0}, "order": 2},
        {"key": "in_stock", "label": "In stock", "type": "boolean", "order": 3},
        {"key": "category", "label": "Category", "type": "dropdown",
         "config": {"options": ["chair", "table", "sofa"]}, "order": 4},
        {"key": "launch_date", "label": "Launch date", "type": "date", "order": 5},
        {"key": "notes", "label": "Notes", "type": "longtext", "order": 6},
    ]
    for spec in products_fields:
        await upsert_field(products_et["_id"], spec)

    # Sample product records (only if none exist yet)
    existing_products = await db.records.count_documents(
        tenant_filter(org_id, {"entity_type_id": products_et["_id"]})
    )
    if existing_products == 0:
        samples = [
            {"sku": "CHR-001", "price": 249.99, "in_stock": True, "category": "chair",
             "launch_date": "2025-03-14", "notes": "Ergonomic office chair"},
            {"sku": "TBL-101", "price": 599.00, "in_stock": True, "category": "table",
             "launch_date": "2025-06-01", "notes": "Solid oak dining table"},
            {"sku": "SOF-777", "price": 1299.50, "in_stock": False, "category": "sofa",
             "launch_date": "2024-11-20", "notes": "Modular sectional"},
        ]
        for s in samples:
            defs = await _load_field_defs(db, org_id, products_et["_id"])
            validator = FieldValidator(db, org_id, products_et["_id"])
            coerced, search_text = await validator.validate(defs, s)
            record_number = await _next_record_number(db, org_id, products_et["_id"])
            title = _derive_title(defs, coerced) or record_number
            rec = Record(
                org_id=org_id, entity_type_id=products_et["_id"],
                title=title, fields=coerced, record_number=record_number,
                search_text=f"{title} {search_text}",
            )
            await db.records.insert_one(rec.model_dump(by_alias=True))
            result["created_records"] += 1

    # Machines
    machines_et = await upsert_et({
        "key": "machines",
        "name_singular": "Machine",
        "name_plural": "Machines",
        "icon": "Cog",
        "color": "#b45309",
        "description": "Equipment / machinery inventory",
    })
    machines_fields = [
        {"key": "serial_no", "label": "Serial No.", "type": "text", "required": True, "unique": True, "order": 1},
        {"key": "manufacturer", "label": "Manufacturer", "type": "text", "required": True, "order": 2},
        {"key": "installed_at", "label": "Installed at", "type": "date", "order": 3},
    ]
    for spec in machines_fields:
        await upsert_field(machines_et["_id"], spec)

    existing_machines = await db.records.count_documents(
        tenant_filter(org_id, {"entity_type_id": machines_et["_id"]})
    )
    if existing_machines == 0:
        samples = [
            {"serial_no": "M-100-A", "manufacturer": "Acme Corp", "installed_at": "2024-01-10"},
            {"serial_no": "M-100-B", "manufacturer": "Globex", "installed_at": "2024-05-22"},
        ]
        for s in samples:
            defs = await _load_field_defs(db, org_id, machines_et["_id"])
            validator = FieldValidator(db, org_id, machines_et["_id"])
            coerced, search_text = await validator.validate(defs, s)
            record_number = await _next_record_number(db, org_id, machines_et["_id"])
            title = _derive_title(defs, coerced) or record_number
            rec = Record(
                org_id=org_id, entity_type_id=machines_et["_id"],
                title=title, fields=coerced, record_number=record_number,
                search_text=f"{title} {search_text}",
            )
            await db.records.insert_one(rec.model_dump(by_alias=True))
            result["created_records"] += 1

    return result


app.include_router(router)


@app.on_event("startup")
async def _startup():
    await ensure_indexes()
    log.info("UBOS Phase 0 backend ready — default org=%s", DEFAULT_ORG_ID)


@app.on_event("shutdown")
async def _shutdown():
    from db import get_client
    get_client().close()
