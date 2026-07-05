"""TemplateApplier — apply a bundled template JSON to an org.

Templates ship as JSON under /app/backend/modules/templates/library/*.json.

Contract (see library/*.json for real examples):
{
  "key": "...",             # required, unique per library
  "name": "...",
  "description": "...",
  "icon": "...",
  "cover_image": "...",
  "entity_types": [ { key, name_singular, name_plural, icon, color,
                     fields: [ {key, label, type, required, unique, order, config?} ],
                     categories?: [ { name, children?:[...] } ] } ],
  "relationships": [ { from_key, to_key, key, from_label, to_label, cardinality, required, cascade_delete? } ],
  "tags": [ { name, entity_type_key?, color? } ]   # entity-scoped when key given, else org-wide
}
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from db import tenant_filter
from models import EntityType, FieldDef
from services.categories import create_category

LIBRARY_DIR = Path(__file__).parent.parent / "modules" / "templates" / "library"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tag_slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80] or "tag"


def list_library() -> list[dict]:
    out: list[dict] = []
    if not LIBRARY_DIR.exists():
        return out
    for f in sorted(LIBRARY_DIR.glob("*.json")):
        try:
            spec = json.loads(f.read_text())
        except json.JSONDecodeError:
            continue
        out.append({
            "key": spec.get("key"),
            "name": spec.get("name"),
            "description": spec.get("description"),
            "icon": spec.get("icon"),
            "cover_image": spec.get("cover_image"),
            "entity_type_count": len(spec.get("entity_types") or []),
            "relationship_count": len(spec.get("relationships") or []),
            "tag_count": len(spec.get("tags") or []),
        })
    return out


def load_spec(key: str) -> dict:
    f = LIBRARY_DIR / f"{key}.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"template '{key}' not found")
    return json.loads(f.read_text())


async def _ensure_entity_type(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    spec: dict,
    conflict_policy: str,
    inserted: list[tuple[str, str]],  # (collection, _id)
) -> tuple[dict | None, bool]:
    """Return (et_doc, created_new_bool). May return None on skip conflict."""
    key = spec["key"]
    exists = await db.entity_types.find_one(tenant_filter(org_id, {"key": key}))
    if exists:
        if conflict_policy == "skip":
            return exists, False
        if conflict_policy == "error":
            raise HTTPException(status_code=409, detail=f"entity type '{key}' already exists")
        # rename: find next available key
        i = 2
        new_key = f"{key}_{i}"
        while await db.entity_types.find_one(tenant_filter(org_id, {"key": new_key})):
            i += 1
            new_key = f"{key}_{i}"
        key = new_key

    et = EntityType(
        org_id=org_id,
        key=key,
        name_singular=spec.get("name_singular") or spec.get("name", "Record"),
        name_plural=spec.get("name_plural") or spec.get("name", "Records") + "s",
        icon=spec.get("icon") or "Box",
        color=spec.get("color") or "#0f766e",
        description=spec.get("description"),
    )
    doc = et.model_dump(by_alias=True)
    await db.entity_types.insert_one(doc)
    inserted.append(("entity_types", doc["_id"]))
    return doc, True


async def _seed_fields(db, *, org_id: str, et_id: str, fields: list[dict],
                       inserted: list[tuple[str, str]]) -> None:
    for i, f in enumerate(fields, start=1):
        exists = await db.field_definitions.find_one(tenant_filter(org_id, {
            "entity_type_id": et_id, "key": f["key"],
        }))
        if exists:
            continue
        payload = {
            "key": f["key"],
            "label": f.get("label", f["key"]),
            "type": f["type"],
            "required": bool(f.get("required")),
            "unique": bool(f.get("unique")),
            "order": f.get("order", i),
            "config": f.get("config") or {},
            "help_text": f.get("help_text"),
            "group": f.get("group"),
        }
        fd = FieldDef(org_id=org_id, entity_type_id=et_id, **payload)
        doc = fd.model_dump(by_alias=True)
        await db.field_definitions.insert_one(doc)
        inserted.append(("field_definitions", doc["_id"]))


async def _seed_categories(db, *, org_id: str, et_id: str, nodes: list[dict],
                           inserted: list[tuple[str, str]],
                           parent_id: str | None = None) -> None:
    for n in nodes:
        # dedupe by (parent, name) — idempotent
        existing = await db.categories.find_one(tenant_filter(org_id, {
            "entity_type_id": et_id, "parent_id": parent_id, "name": n["name"],
        }))
        if existing:
            cat = existing
        else:
            cat = await create_category(
                db, org_id=org_id, entity_type_id=et_id,
                name=n["name"], parent_id=parent_id,
                description=n.get("description"),
                color=n.get("color"), icon=n.get("icon"),
            )
            inserted.append(("categories", cat["_id"]))
        for child in n.get("children") or []:
            await _seed_categories(db, org_id=org_id, et_id=et_id,
                                    nodes=[child], inserted=inserted,
                                    parent_id=cat["_id"])


async def _seed_tags(db, *, org_id: str, tags: list[dict],
                     et_by_key: dict[str, str],
                     inserted: list[tuple[str, str]]) -> None:
    for t in tags:
        et_id = et_by_key.get(t.get("entity_type_key")) if t.get("entity_type_key") else None
        slug = _tag_slug(t["name"])
        exists = await db.tags.find_one(tenant_filter(org_id, {
            "entity_type_id": et_id, "slug": slug,
        }))
        if exists:
            continue
        tid = str(uuid.uuid4())
        doc = {
            "_id": tid, "org_id": org_id, "entity_type_id": et_id,
            "name": t["name"], "slug": slug,
            "color": t.get("color"),
            "usage_count": 0,
            "created_at": _now(), "updated_at": _now(), "deleted_at": None,
        }
        await db.tags.insert_one(doc)
        inserted.append(("tags", tid))


async def _seed_relationships(db, *, org_id: str, rels: list[dict],
                              et_by_key: dict[str, str],
                              inserted: list[tuple[str, str]]) -> None:
    for r in rels:
        from_id = et_by_key.get(r["from_key"])
        to_id = et_by_key.get(r["to_key"])
        if not from_id or not to_id:
            continue
        exists = await db.relationship_definitions.find_one(tenant_filter(org_id, {
            "from_entity_type_id": from_id, "key": r["key"],
        }))
        if exists:
            continue
        rid = str(uuid.uuid4())
        doc = {
            "_id": rid, "org_id": org_id,
            "from_entity_type_id": from_id,
            "to_entity_type_id": to_id,
            "key": r["key"],
            "from_label": r["from_label"],
            "to_label": r["to_label"],
            "cardinality": r.get("cardinality", "one_to_many"),
            "required": bool(r.get("required")),
            "cascade_delete": bool(r.get("cascade_delete")),
            "description": r.get("description"),
            "created_at": _now(), "updated_at": _now(), "deleted_at": None,
        }
        await db.relationship_definitions.insert_one(doc)
        inserted.append(("relationship_definitions", rid))


async def apply_template(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    key: str,
    conflict_policy: str = "skip",
    dry_run: bool = False,
) -> dict:
    spec = load_spec(key)
    # dry-run: return the plan (no writes)
    if dry_run:
        return {
            "dry_run": True,
            "template": {"key": spec.get("key"), "name": spec.get("name")},
            "entity_types": [
                {"key": e["key"], "name_plural": e.get("name_plural", e["key"]),
                 "fields": len(e.get("fields") or []),
                 "categories": _count_nodes(e.get("categories") or [])}
                for e in (spec.get("entity_types") or [])
            ],
            "relationships": len(spec.get("relationships") or []),
            "tags": len(spec.get("tags") or []),
        }

    inserted: list[tuple[str, str]] = []
    et_by_key: dict[str, str] = {}
    try:
        for et_spec in spec.get("entity_types") or []:
            et_doc, _ = await _ensure_entity_type(
                db, org_id=org_id, spec=et_spec, conflict_policy=conflict_policy,
                inserted=inserted,
            )
            if not et_doc:
                continue
            et_by_key[et_spec["key"]] = et_doc["_id"]
            await _seed_fields(db, org_id=org_id, et_id=et_doc["_id"],
                                fields=et_spec.get("fields") or [], inserted=inserted)
            await _seed_categories(db, org_id=org_id, et_id=et_doc["_id"],
                                    nodes=et_spec.get("categories") or [], inserted=inserted)

        await _seed_relationships(db, org_id=org_id,
                                   rels=spec.get("relationships") or [],
                                   et_by_key=et_by_key, inserted=inserted)
        await _seed_tags(db, org_id=org_id, tags=spec.get("tags") or [],
                          et_by_key=et_by_key, inserted=inserted)

    except HTTPException:
        # rollback everything we inserted but preserve the intended status code
        for coll, _id in reversed(inserted):
            try:
                await db[coll].delete_one({"_id": _id})
            except Exception:
                pass
        raise
    except Exception as e:
        for coll, _id in reversed(inserted):
            try:
                await db[coll].delete_one({"_id": _id})
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"template apply failed: {e}") from e

    return {
        "dry_run": False,
        "template": {"key": spec.get("key"), "name": spec.get("name")},
        "inserted": {
            coll: sum(1 for c, _ in inserted if c == coll)
            for coll in {c for c, _ in inserted}
        },
        "entity_type_ids": list(et_by_key.values()),
    }


def _count_nodes(nodes: list[dict]) -> int:
    total = 0
    for n in nodes:
        total += 1 + _count_nodes(n.get("children") or [])
    return total
