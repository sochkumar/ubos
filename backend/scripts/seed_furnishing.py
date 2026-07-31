"""Furnishing first-run seed for the single-business desktop build.

Creates the canonical users + a 'My Business' org + a ready 'Fabrics' catalogue
with fabric fields, plus Curtains/Blinds/Upholstery categories and a few tags.
No industry starter packs / demo data. Idempotent.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from db import ensure_indexes, get_db
from routes._org_helpers import add_membership, create_organization
from services.categories import create_category
from scripts.seed import CANONICAL_USERS, DEMO_USER, _upsert_user

log = logging.getLogger("ubos.seed_furnishing")

ORG_NAME = "My Business"
ORG_SLUG = "my-business"

# Fabric/furnishing field set (library + attached to the Fabrics catalogue).
FIELDS = [
    {"key": "design", "label": "Design / Name", "type": "text"},
    {"key": "sku", "label": "SKU", "type": "text", "unique": True},
    {"key": "gsm", "label": "GSM", "type": "number", "unit": "GSM"},
    {"key": "width", "label": "Width", "type": "number", "unit": "cm"},
    {"key": "composition", "label": "Composition", "type": "text"},
    {"key": "end_use", "label": "End Use", "type": "multi_select",
     "config": {"options": ["Curtains", "Blinds", "Upholstery"]}},
    {"key": "martindale", "label": "Martindale", "type": "number"},
    {"key": "repeat", "label": "Repeat", "type": "text"},
    {"key": "shade", "label": "Shade", "type": "text"},
    {"key": "price", "label": "Price", "type": "currency"},
    {"key": "photo", "label": "Photo", "type": "image"},
]
CATEGORIES = ["Curtains", "Blinds", "Upholstery"]
TAGS = ["New Arrival", "Bestseller", "Clearance"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_furnishing_seed() -> dict:
    db = get_db()
    await ensure_indexes()

    # users
    users = {}
    for u in CANONICAL_USERS + [DEMO_USER]:
        users[u["email"]] = await _upsert_user(db, u)
    owner = users["owner@ubos.test"]

    # org
    org = await db.organizations.find_one({"slug": ORG_SLUG})
    if not org:
        org = await create_organization(db, name=ORG_NAME, slug=ORG_SLUG, creator_user_id=owner["_id"])
    org_id = org["_id"]

    # memberships + default org
    for u in CANONICAL_USERS:
        udoc = users[u["email"]]
        if not await db.memberships.find_one(
            {"user_id": udoc["_id"], "org_id": org_id, "status": "active"}
        ):
            await add_membership(db, user_id=udoc["_id"], org_id=org_id, role_name=u["role"])
        if not udoc.get("default_org_id"):
            await db.users.update_one(
                {"_id": udoc["_id"]},
                {"$set": {"default_org_id": org_id, "active_org_id": org_id}},
            )

    # Fabrics catalogue
    et = await db.entity_types.find_one({"org_id": org_id, "key": "fabrics", "deleted_at": None})
    if et:
        et_id = et["_id"]
    else:
        et_id = str(uuid.uuid4())
        await db.entity_types.insert_one({
            "_id": et_id, "org_id": org_id, "key": "fabrics",
            "name_singular": "Fabric", "name_plural": "Fabrics",
            "icon": "Package", "color": "#0d9488", "description": None,
            "is_system": False, "record_counter": 0, "record_seq": 0,
            "created_at": _now(), "updated_at": _now(), "deleted_at": None,
        })

    # fields: library entry + field_definition on the catalogue
    order = 1
    for f in FIELDS:
        lib = await db.field_library.find_one({"org_id": org_id, "key": f["key"], "deleted_at": None})
        if lib:
            lib_id = lib["_id"]
        else:
            lib_id = str(uuid.uuid4())
            await db.field_library.insert_one({
                "_id": lib_id, "org_id": org_id, "key": f["key"], "label": f["label"],
                "type": f["type"], "config": f.get("config") or {}, "unit": f.get("unit"),
                "help_text": None, "custom_type_id": None,
                "created_at": _now(), "updated_at": _now(), "deleted_at": None,
            })
        if not await db.field_definitions.find_one(
            {"org_id": org_id, "entity_type_id": et_id, "key": f["key"], "deleted_at": None}
        ):
            await db.field_definitions.insert_one({
                "_id": str(uuid.uuid4()), "org_id": org_id, "entity_type_id": et_id,
                "library_id": lib_id, "key": f["key"], "label": f["label"], "type": f["type"],
                "config": f.get("config") or {}, "unit": f.get("unit"), "help_text": None,
                "custom_type_id": None, "required": False, "unique": bool(f.get("unique")),
                "sensitive": False, "order": order, "group": None,
                "created_at": _now(), "updated_at": _now(), "deleted_at": None,
            })
            order += 1

    # categories (org-global)
    for name in CATEGORIES:
        if not await db.categories.find_one({"org_id": org_id, "name": name, "deleted_at": None}):
            await create_category(db, org_id=org_id, entity_type_id=et_id, name=name)

    # tags (org-global)
    for name in TAGS:
        slug = name.lower().replace(" ", "-")
        if not await db.tags.find_one({"org_id": org_id, "slug": slug, "deleted_at": None}):
            await db.tags.insert_one({
                "_id": str(uuid.uuid4()), "org_id": org_id, "entity_type_id": None,
                "name": name, "slug": slug, "color": "#0d9488", "usage_count": 0,
                "created_at": _now(), "updated_at": _now(), "deleted_at": None,
            })

    log.info("furnishing seed complete: org=%s catalogue=Fabrics fields=%d", org_id, len(FIELDS))
    return {"org": org_id, "catalogue": et_id, "fields": len(FIELDS)}
