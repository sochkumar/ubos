"""Relationship instance CRUD helpers (bidirectional, cardinality-enforced).

Instances live embedded on `records.relationships[]` — one row per relationship,
so a single link is written on both source and target records. `direction`
indicates which side of the rel_def the record sits on ("from" or "to")."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from db import tenant_filter


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _record_by_id(db, org_id: str, rid: str) -> dict | None:
    return await db.records.find_one(tenant_filter(org_id, {"_id": rid}))


async def _rel_def(db, org_id: str, rd_id: str) -> dict | None:
    return await db.relationship_definitions.find_one(
        tenant_filter(org_id, {"_id": rd_id}),
    )


def _count_links(record: dict, rel_def_id: str, direction: str) -> int:
    return sum(
        1 for r in (record.get("relationships") or [])
        if r.get("rel_def_id") == rel_def_id and r.get("direction") == direction
    )


def _has_link(record: dict, rel_def_id: str, target_id: str, direction: str) -> bool:
    return any(
        r.get("rel_def_id") == rel_def_id
        and r.get("target_record_id") == target_id
        and r.get("direction") == direction
        for r in (record.get("relationships") or [])
    )


async def link_records(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    source_id: str,
    rel_def_id: str,
    target_id: str,
) -> dict:
    """Create a bidirectional link. Enforces cardinality + entity_type match.
    `source_id` is the record whose entity_type matches rel_def.from_entity_type_id;
    resolution is direction-aware — if source matches the `to` side, we still
    write the link with the correct directions on both sides."""
    if source_id == target_id:
        raise HTTPException(409, "cannot link a record to itself")

    rdef = await _rel_def(db, org_id, rel_def_id)
    if not rdef or rdef.get("deleted_at"):
        raise HTTPException(404, "relationship definition not found")

    src = await _record_by_id(db, org_id, source_id)
    tgt = await _record_by_id(db, org_id, target_id)
    if not src:
        raise HTTPException(404, "source record not found")
    if not tgt:
        raise HTTPException(404, "target record not found")

    from_et = rdef["from_entity_type_id"]
    to_et = rdef["to_entity_type_id"]
    # Figure out which side is which.
    if src["entity_type_id"] == from_et and tgt["entity_type_id"] == to_et:
        src_dir, tgt_dir = "from", "to"
    elif src["entity_type_id"] == to_et and tgt["entity_type_id"] == from_et:
        src_dir, tgt_dir = "to", "from"
    else:
        raise HTTPException(
            422,
            f"records don't match the relationship's entity types "
            f"(expected {from_et} ↔ {to_et})",
        )

    # Idempotency
    if _has_link(src, rel_def_id, target_id, src_dir):
        return {"already_linked": True, "rel_def_id": rel_def_id,
                "target_record_id": target_id}

    # Cardinality: enforce on BOTH sides.
    card = rdef.get("cardinality", "one_to_many")
    if card == "one_to_one":
        if _count_links(src, rel_def_id, src_dir) >= 1:
            raise HTTPException(409, "one_to_one: source is already linked")
        if _count_links(tgt, rel_def_id, tgt_dir) >= 1:
            raise HTTPException(409, "one_to_one: target is already linked")
    elif card == "one_to_many":
        # The 'from' side may fan out to many, the 'to' side is 1:1. We check
        # the target (whichever side plays the 'to' role) has no prior link.
        if src_dir == "from":
            if _count_links(tgt, rel_def_id, "to") >= 1:
                raise HTTPException(409, "one_to_many: target is already linked to another source")
        else:
            # src plays the 'to' role; if it already has an existing 'to' link,
            # that means it's already claimed by another source.
            if _count_links(src, rel_def_id, "to") >= 1:
                raise HTTPException(409, "one_to_many: this record is already linked to another source")

    now = _now()
    src_link = {"rel_def_id": rel_def_id, "target_record_id": target_id,
                "direction": src_dir, "created_at": now}
    tgt_link = {"rel_def_id": rel_def_id, "target_record_id": source_id,
                "direction": tgt_dir, "created_at": now}
    await db.records.update_one(
        {"_id": source_id, "org_id": org_id},
        {"$push": {"relationships": src_link}, "$set": {"updated_at": now}},
    )
    await db.records.update_one(
        {"_id": target_id, "org_id": org_id},
        {"$push": {"relationships": tgt_link}, "$set": {"updated_at": now}},
    )
    return {"already_linked": False, "rel_def_id": rel_def_id,
            "target_record_id": target_id, "direction": src_dir}


async def unlink_records(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    source_id: str,
    rel_def_id: str,
    target_id: str,
) -> None:
    now = _now()
    await db.records.update_one(
        {"_id": source_id, "org_id": org_id},
        {"$pull": {"relationships": {
            "rel_def_id": rel_def_id, "target_record_id": target_id,
        }}, "$set": {"updated_at": now}},
    )
    await db.records.update_one(
        {"_id": target_id, "org_id": org_id},
        {"$pull": {"relationships": {
            "rel_def_id": rel_def_id, "target_record_id": source_id,
        }}, "$set": {"updated_at": now}},
    )


async def cascade_on_delete(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    record: dict,
) -> list[str]:
    """Called AFTER a record is soft-deleted. For each rel_def with
    cascade_delete=true where this record is the 'from' side, soft-delete the
    linked targets and remove reverse links from surviving records.

    Returns the list of target record ids that were cascade-deleted."""
    cascaded: list[str] = []
    links = record.get("relationships") or []
    rel_ids = list({l["rel_def_id"] for l in links if l.get("direction") == "from"})
    if not rel_ids:
        # Still remove reverse links pointing at us
        await _cleanup_reverse_links(db, org_id, record["_id"], links)
        return cascaded
    rdefs = {
        d["_id"]: d
        async for d in db.relationship_definitions.find(
            tenant_filter(org_id, {"_id": {"$in": rel_ids}}),
        )
    }
    now = _now()
    for l in links:
        if l.get("direction") != "from":
            continue
        rdef = rdefs.get(l["rel_def_id"])
        if not rdef:
            continue
        if rdef.get("cascade_delete"):
            tgt_id = l["target_record_id"]
            await db.records.update_one(
                {"_id": tgt_id, "org_id": org_id, "deleted_at": None},
                {"$set": {"deleted_at": now, "updated_at": now}},
            )
            cascaded.append(tgt_id)

    # Always clean up reverse pointers on surviving records
    await _cleanup_reverse_links(db, org_id, record["_id"], links)
    return cascaded


async def _cleanup_reverse_links(db, org_id: str, my_id: str, links) -> None:
    # For every target that still exists, remove its link pointing at `my_id`.
    target_ids = list({l["target_record_id"] for l in (links or [])})
    if not target_ids:
        return
    await db.records.update_many(
        {"_id": {"$in": target_ids}, "org_id": org_id},
        {"$pull": {"relationships": {"target_record_id": my_id}}},
    )


async def list_relationships_for_record(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    record_id: str,
) -> dict:
    """Grouped-by-rel_def response with target hydration."""
    rec = await _record_by_id(db, org_id, record_id)
    if not rec:
        raise HTTPException(404, "record not found")

    links = rec.get("relationships") or []
    if not links:
        return {"record_id": record_id, "groups": []}

    rd_ids = list({l["rel_def_id"] for l in links})
    tgt_ids = list({l["target_record_id"] for l in links})
    rdefs = {d["_id"]: d async for d in db.relationship_definitions.find(
        tenant_filter(org_id, {"_id": {"$in": rd_ids}}),
    )}
    targets = {t["_id"]: t async for t in db.records.find(
        tenant_filter(org_id, {"_id": {"$in": tgt_ids}}),
        {"title": 1, "record_number": 1, "entity_type_id": 1, "fields": 1},
    )}
    et_ids = list({t.get("entity_type_id") for t in targets.values() if t.get("entity_type_id")})
    ets = {e["_id"]: e for e in await db.entity_types.find(
        tenant_filter(org_id, {"_id": {"$in": et_ids}}),
        {"name_singular": 1, "name_plural": 1, "icon": 1, "color": 1},
    ).to_list(1000)}

    groups: dict[str, dict] = {}
    for l in links:
        rd_id = l["rel_def_id"]
        rdef = rdefs.get(rd_id)
        if not rdef:
            continue
        # is this record on the from or to side of the def?
        my_direction = l["direction"]
        key = f"{rd_id}:{my_direction}"
        if key not in groups:
            other_label = rdef["to_label"] if my_direction == "from" else rdef["from_label"]
            other_et_id = rdef["to_entity_type_id"] if my_direction == "from" else rdef["from_entity_type_id"]
            groups[key] = {
                "rel_def_id": rd_id,
                "direction": my_direction,
                "label": other_label,
                "cardinality": rdef.get("cardinality", "one_to_many"),
                "target_entity_type_id": other_et_id,
                "target_entity_type_name": (ets.get(other_et_id) or {}).get("name_plural"),
                "cascade_delete": bool(rdef.get("cascade_delete")),
                "items": [],
            }
        t = targets.get(l["target_record_id"])
        if not t:
            continue
        groups[key]["items"].append({
            "id": t["_id"],
            "title": t.get("title"),
            "record_number": t.get("record_number"),
            "entity_type_id": t.get("entity_type_id"),
            "entity_type_name": (ets.get(t.get("entity_type_id")) or {}).get("name_singular"),
            "created_at": l.get("created_at"),
        })

    return {"record_id": record_id, "groups": list(groups.values())}
