"""Developer helpers — demo seed scoped to the caller's active org."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import EntityType, FieldDef, Record
from routes.data import _load_field_defs, _next_record_number, _derive_title
from validator import FieldValidator

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/seed-demo")
async def seed_demo(ctx: AuthContext = Depends(require_permission("entity_types.manage"))):
    """Idempotent demo seed scoped to the caller's active org."""
    db = get_db()
    org_id = ctx.org_id
    result = {"entity_types": [], "created_records": 0}

    async def upsert_et(spec):
        existing = await db.entity_types.find_one(tenant_filter(org_id, {"key": spec["key"]}))
        if existing:
            result["entity_types"].append({"key": spec["key"], "created": False, "id": existing["_id"]})
            return existing
        et = EntityType(org_id=org_id, **spec)
        doc = et.model_dump(by_alias=True)
        await db.entity_types.insert_one(doc)
        result["entity_types"].append({"key": spec["key"], "created": True, "id": doc["_id"]})
        return doc

    async def upsert_field(et_id, spec):
        existing = await db.field_definitions.find_one(
            tenant_filter(org_id, {"entity_type_id": et_id, "key": spec["key"]})
        )
        if existing:
            return existing
        fd = FieldDef(org_id=org_id, entity_type_id=et_id, **spec)
        doc = fd.model_dump(by_alias=True)
        await db.field_definitions.insert_one(doc)
        return doc

    products_et = await upsert_et({
        "key": "products", "name_singular": "Product", "name_plural": "Products",
        "icon": "Package", "color": "#0f766e",
        "description": "Physical products in the catalog",
    })
    for spec in [
        {"key": "sku", "label": "SKU", "type": "text", "required": True, "unique": True, "order": 1},
        {"key": "price", "label": "Price", "type": "currency", "required": True, "config": {"min": 0}, "order": 2},
        {"key": "in_stock", "label": "In stock", "type": "boolean", "order": 3},
        {"key": "category", "label": "Category", "type": "dropdown",
         "config": {"options": ["chair", "table", "sofa"]}, "order": 4},
        {"key": "launch_date", "label": "Launch date", "type": "date", "order": 5},
        {"key": "notes", "label": "Notes", "type": "longtext", "order": 6},
    ]:
        await upsert_field(products_et["_id"], spec)

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

    machines_et = await upsert_et({
        "key": "machines", "name_singular": "Machine", "name_plural": "Machines",
        "icon": "Cog", "color": "#b45309",
        "description": "Equipment / machinery inventory",
    })
    for spec in [
        {"key": "serial_no", "label": "Serial No.", "type": "text", "required": True, "unique": True, "order": 1},
        {"key": "manufacturer", "label": "Manufacturer", "type": "text", "required": True, "order": 2},
        {"key": "installed_at", "label": "Installed at", "type": "date", "order": 3},
    ]:
        await upsert_field(machines_et["_id"], spec)

    existing_machines = await db.records.count_documents(
        tenant_filter(org_id, {"entity_type_id": machines_et["_id"]})
    )
    if existing_machines == 0:
        for s in [
            {"serial_no": "M-100-A", "manufacturer": "Acme Corp", "installed_at": "2024-01-10"},
            {"serial_no": "M-100-B", "manufacturer": "Globex", "installed_at": "2024-05-22"},
        ]:
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
