"""Category tree utilities — materialized path + move + descendant recompute.

Public API:
- create_category(db, org_id, et_id, name, parent_id, ...) -> dict
- move_category(db, org_id, cat_id, new_parent_id) -> dict
- rename_category(db, org_id, cat_id, new_name) -> dict
- soft_delete_category(db, org_id, cat_id, cascade: bool) -> None
- get_tree(db, org_id, et_id) -> list[dict]  # nested {..., children:[...]}
- descendant_ids_including_self(db, org_id, et_id, cat_id) -> list[str]
- ensure_slug_unique(...) helper

All operations write path + path_names + depth denormalized fields.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from db import tenant_filter

MAX_DEPTH = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower().strip())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80] or "category"


async def _unique_slug(db, org_id: str, et_id: str, parent_id: str | None, base: str) -> str:
    slug = base
    i = 1
    while await db.categories.find_one(tenant_filter(org_id, {
        "entity_type_id": et_id,
        "parent_id": parent_id,
        "slug": slug,
    })):
        i += 1
        slug = f"{base}-{i}"
    return slug


async def create_category(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    entity_type_id: str,
    name: str,
    parent_id: str | None = None,
    description: str | None = None,
    color: str | None = None,
    icon: str | None = None,
) -> dict:
    parent = None
    if parent_id:
        parent = await db.categories.find_one(tenant_filter(org_id, {
            "_id": parent_id, "entity_type_id": entity_type_id,
        }))
        if not parent:
            raise HTTPException(status_code=404, detail="parent category not found")
        if len(parent["path"]) >= MAX_DEPTH:
            raise HTTPException(status_code=400, detail=f"max category depth of {MAX_DEPTH} reached")

    cid = str(uuid.uuid4())
    path = (parent["path"] if parent else []) + [cid]
    path_names = (parent["path_names"] if parent else []) + [name.strip()]

    # next order among siblings
    last = await db.categories.find(tenant_filter(org_id, {
        "entity_type_id": entity_type_id, "parent_id": parent_id,
    })).sort("order", -1).limit(1).to_list(1)
    order = (last[0]["order"] + 1) if last else 1

    doc = {
        "_id": cid,
        "org_id": org_id,
        "entity_type_id": entity_type_id,
        "name": name.strip(),
        "slug": await _unique_slug(db, org_id, entity_type_id, parent_id, _slug(name)),
        "parent_id": parent_id,
        "path": path,
        "path_names": path_names,
        "depth": len(path) - 1,
        "order": order,
        "description": description,
        "color": color,
        "icon": icon,
        "record_count": 0,
        "created_at": _now(),
        "updated_at": _now(),
        "deleted_at": None,
    }
    await db.categories.insert_one(doc)
    return doc


async def _recompute_descendants(
    db, *, org_id: str, entity_type_id: str, cat_id: str,
    new_path: list[str], new_path_names: list[str],
) -> None:
    """After a category is renamed / moved, propagate the change to all descendants."""
    descendants = await db.categories.find(tenant_filter(org_id, {
        "entity_type_id": entity_type_id,
        "path": cat_id,
        "_id": {"$ne": cat_id},
    })).to_list(10000)
    for d in descendants:
        try:
            idx = d["path"].index(cat_id)
        except ValueError:
            continue
        d_new_path = new_path + d["path"][idx + 1:]
        d_new_names = new_path_names + d["path_names"][idx + 1:]
        await db.categories.update_one(
            {"_id": d["_id"]},
            {"$set": {
                "path": d_new_path,
                "path_names": d_new_names,
                "depth": len(d_new_path) - 1,
                "updated_at": _now(),
            }},
        )


async def rename_category(db, *, org_id: str, cat_id: str, new_name: str) -> dict:
    cat = await db.categories.find_one(tenant_filter(org_id, {"_id": cat_id}))
    if not cat:
        raise HTTPException(status_code=404, detail="category not found")
    new_name = new_name.strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="name cannot be empty")
    new_path_names = cat["path_names"][:-1] + [new_name]
    new_slug = await _unique_slug(
        db, org_id, cat["entity_type_id"], cat["parent_id"], _slug(new_name)
    )
    await db.categories.update_one(
        {"_id": cat_id},
        {"$set": {"name": new_name, "slug": new_slug, "path_names": new_path_names,
                  "updated_at": _now()}},
    )
    await _recompute_descendants(
        db, org_id=org_id, entity_type_id=cat["entity_type_id"], cat_id=cat_id,
        new_path=cat["path"], new_path_names=new_path_names,
    )
    return await db.categories.find_one({"_id": cat_id})


async def move_category(db, *, org_id: str, cat_id: str, new_parent_id: str | None) -> dict:
    cat = await db.categories.find_one(tenant_filter(org_id, {"_id": cat_id}))
    if not cat:
        raise HTTPException(status_code=404, detail="category not found")
    if new_parent_id == cat.get("parent_id"):
        return cat
    if new_parent_id == cat_id:
        raise HTTPException(status_code=400, detail="cannot move a category into itself")

    new_parent = None
    if new_parent_id:
        new_parent = await db.categories.find_one(tenant_filter(org_id, {
            "_id": new_parent_id,
            "entity_type_id": cat["entity_type_id"],
        }))
        if not new_parent:
            raise HTTPException(status_code=404, detail="new parent not found")
        # circular check: new_parent's path must NOT include cat_id
        if cat_id in new_parent["path"]:
            raise HTTPException(status_code=400, detail="cannot move a category under its own descendant")
        if len(new_parent["path"]) + 1 > MAX_DEPTH:
            raise HTTPException(status_code=400, detail=f"move would exceed max depth of {MAX_DEPTH}")

    new_path = (new_parent["path"] if new_parent else []) + [cat_id]
    new_path_names = (new_parent["path_names"] if new_parent else []) + [cat["name"]]

    # next order under new parent
    last = await db.categories.find(tenant_filter(org_id, {
        "entity_type_id": cat["entity_type_id"], "parent_id": new_parent_id,
    })).sort("order", -1).limit(1).to_list(1)
    order = (last[0]["order"] + 1) if last else 1

    # slug uniqueness under new parent
    new_slug = await _unique_slug(
        db, org_id, cat["entity_type_id"], new_parent_id, _slug(cat["name"])
    )

    await db.categories.update_one(
        {"_id": cat_id},
        {"$set": {
            "parent_id": new_parent_id,
            "path": new_path,
            "path_names": new_path_names,
            "depth": len(new_path) - 1,
            "order": order,
            "slug": new_slug,
            "updated_at": _now(),
        }},
    )
    await _recompute_descendants(
        db, org_id=org_id, entity_type_id=cat["entity_type_id"], cat_id=cat_id,
        new_path=new_path, new_path_names=new_path_names,
    )
    return await db.categories.find_one({"_id": cat_id})


async def descendant_ids_including_self(
    db, *, org_id: str, entity_type_id: str, cat_id: str,
) -> list[str]:
    cursor = db.categories.find(
        tenant_filter(org_id, {"entity_type_id": entity_type_id, "path": cat_id}),
        {"_id": 1},
    )
    return [d["_id"] for d in await cursor.to_list(10000)]


async def soft_delete_category(
    db, *, org_id: str, cat_id: str, cascade: bool = False,
) -> None:
    cat = await db.categories.find_one(tenant_filter(org_id, {"_id": cat_id}))
    if not cat:
        raise HTTPException(status_code=404, detail="category not found")
    now = _now()
    if cascade:
        ids = await descendant_ids_including_self(
            db, org_id=org_id, entity_type_id=cat["entity_type_id"], cat_id=cat_id,
        )
        await db.categories.update_many(
            {"_id": {"$in": ids}},
            {"$set": {"deleted_at": now, "updated_at": now}},
        )
        # also remove them from any records
        await db.records.update_many(
            tenant_filter(org_id, {"entity_type_id": cat["entity_type_id"],
                                    "category_ids": {"$in": ids}}),
            {"$pull": {"category_ids": {"$in": ids}}},
        )
    else:
        # orphan: reparent direct children to cat's parent
        children = await db.categories.find(tenant_filter(org_id, {
            "entity_type_id": cat["entity_type_id"], "parent_id": cat_id,
        })).to_list(10000)
        for ch in children:
            await move_category(db, org_id=org_id, cat_id=ch["_id"],
                                 new_parent_id=cat["parent_id"])
        # soft delete just this node
        await db.categories.update_one(
            {"_id": cat_id},
            {"$set": {"deleted_at": now, "updated_at": now}},
        )
        # remove this cat id from any records
        await db.records.update_many(
            tenant_filter(org_id, {"entity_type_id": cat["entity_type_id"],
                                    "category_ids": cat_id}),
            {"$pull": {"category_ids": cat_id}},
        )


async def get_tree(db, *, org_id: str, entity_type_id: str) -> list[dict]:
    cursor = db.categories.find(
        tenant_filter(org_id, {"entity_type_id": entity_type_id})
    ).sort([("depth", 1), ("order", 1)])
    docs = await cursor.to_list(10000)
    by_id: dict[str, dict] = {}
    roots: list[dict] = []
    for d in docs:
        d["id"] = d.pop("_id")
        d["children"] = []
        by_id[d["id"]] = d
    for d in docs:
        pid = d.get("parent_id")
        if pid and pid in by_id:
            by_id[pid]["children"].append(d)
        else:
            roots.append(d)
    return roots
