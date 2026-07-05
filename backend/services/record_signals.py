"""Denormalized-counter maintenance for records ↔ categories / tags.

Called by the records routes on save/delete. Uses set-diff so patching a record
with new category/tag lists correctly increments the joined and decrements the
removed.

All operations are best-effort — counters are advisory, not source of truth.
The authoritative test is always the actual `records` query.
"""
from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from db import tenant_filter


async def apply_record_diff(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    old_category_ids: list[str],
    new_category_ids: list[str],
    old_tag_ids: list[str],
    new_tag_ids: list[str],
) -> None:
    added_cats = set(new_category_ids) - set(old_category_ids)
    removed_cats = set(old_category_ids) - set(new_category_ids)
    if added_cats:
        await db.categories.update_many(
            tenant_filter(org_id, {"_id": {"$in": list(added_cats)}}),
            {"$inc": {"record_count": 1}},
        )
    if removed_cats:
        await db.categories.update_many(
            tenant_filter(org_id, {"_id": {"$in": list(removed_cats)}}),
            {"$inc": {"record_count": -1}},
        )

    added_tags = set(new_tag_ids) - set(old_tag_ids)
    removed_tags = set(old_tag_ids) - set(new_tag_ids)
    if added_tags:
        await db.tags.update_many(
            tenant_filter(org_id, {"_id": {"$in": list(added_tags)}}),
            {"$inc": {"usage_count": 1}},
        )
    if removed_tags:
        await db.tags.update_many(
            tenant_filter(org_id, {"_id": {"$in": list(removed_tags)}}),
            {"$inc": {"usage_count": -1}},
        )


async def on_record_deleted(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    category_ids: list[str],
    tag_ids: list[str],
) -> None:
    """Full decrement — record moved to deleted_at."""
    await apply_record_diff(
        db,
        org_id=org_id,
        old_category_ids=list(category_ids or []),
        new_category_ids=[],
        old_tag_ids=list(tag_ids or []),
        new_tag_ids=[],
    )


async def validate_ids_belong_to_org_and_et(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    entity_type_id: str,
    category_ids: list[str],
    tag_ids: list[str],
) -> tuple[list[str], list[str]]:
    """Filter category_ids + tag_ids to those that actually exist under this org/et.
    Silently drops unknown ids (400 would be noisier for very little value here)."""
    valid_cats: list[str] = []
    if category_ids:
        cursor = db.categories.find(
            tenant_filter(org_id, {
                "entity_type_id": entity_type_id,
                "_id": {"$in": category_ids},
            }),
            {"_id": 1},
        )
        valid_cats = [d["_id"] for d in await cursor.to_list(1000)]

    valid_tags: list[str] = []
    if tag_ids:
        cursor = db.tags.find(
            tenant_filter(org_id, {
                "_id": {"$in": tag_ids},
                # tag must be org-wide (null entity_type_id) OR match this entity type
                "$or": [
                    {"entity_type_id": None},
                    {"entity_type_id": entity_type_id},
                ],
            }),
            {"_id": 1},
        )
        valid_tags = [d["_id"] for d in await cursor.to_list(1000)]

    return valid_cats, valid_tags
