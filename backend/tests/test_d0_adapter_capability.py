"""
Phase D0 — Adapter capability matrix.

Runs UBOS's three most-representative query patterns against BOTH
adapters (`MotorAdapter` on the running MongoDB and `MongitaAdapter`
on a tmp dir) via parametrized fixtures. Every test executes twice.

Target patterns (mirrors the 3 code paths named in the D0 brief):
    1. Records CRUD           — insert_one / find / find_one / update_one / delete_one
    2. Browse aggregate       — the exact _facet_group pipelines from routes/browse.py
    3. Category descendants   — the `path` array `$in` lookup from services/categories.py

Failures on the mongita adapter are EXPECTED for aggregate + text — they
prove the incompatibilities called out in the D0 report. Motor must
remain green (regression guard).
"""
from __future__ import annotations

import asyncio
import os
import uuid
import pytest

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from core.db_adapter import (
    MotorAdapter, MongitaAdapter, MontyDBAdapter, DatabaseAdapter,
    reset_adapter_for_tests,
)


# ─────────────────── adapter fixture (factory pattern) ───────────────────
# Motor's AsyncIOMotorClient binds to whichever event loop is running at
# construction time. Using a factory that instantiates the adapter INSIDE
# the test's asyncio.run() keeps Motor + the test on the same loop.
@pytest.fixture(params=["motor", "mongita", "montydb"])
def make_adapter(request, tmp_path):
    kind = request.param

    def factory() -> DatabaseAdapter:
        reset_adapter_for_tests()
        if kind == "motor":
            from motor.motor_asyncio import AsyncIOMotorClient
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            db = client[os.environ["DB_NAME"] + "_d0test"]
            return MotorAdapter(db)
        if kind == "mongita":
            d = tmp_path / f"mongita_{uuid.uuid4().hex[:6]}"
            return MongitaAdapter(d, db_name="ubos_d0test")
        # montydb
        d = tmp_path / f"montydb_{uuid.uuid4().hex[:6]}"
        return MontyDBAdapter(d, db_name="ubos_d0test")

    factory.kind = kind
    return factory


async def _wipe_motor(adapter):
    """Blow away test collections between tests so we start clean."""
    if adapter.mode != "online":
        return
    for c in await adapter.list_collection_names():
        if c in ("records", "categories", "entity_types", "field_definitions"):
            await adapter[c].delete_many({"org_id": ORG})


ORG = "d0-org"


# ─────────────────── pattern 1 · records CRUD ───────────────────
class TestPattern1_RecordsCRUD:
    """Mirrors the shape of POST/GET/PATCH/DELETE /api/entity-types/{id}/records."""

    def test_insert_and_find(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            rid = str(uuid.uuid4())
            doc = {
                "_id": rid, "org_id": ORG, "entity_type_id": "et1",
                "title": "Chair", "record_number": "REC-000001",
                "fields": {"sku": "SKU-A", "price": 42.5},
                "search_text": "chair sku-a",
                "created_at": "2026-02-01T00:00:00Z",
                "updated_at": "2026-02-01T00:00:00Z",
                "deleted_at": None,
            }
            await adapter.records.insert_one(doc)
            got = await adapter.records.find_one({"_id": rid})
            assert got is not None
            assert got["title"] == "Chair"
            assert got["fields"]["sku"] == "SKU-A"
        asyncio.run(run())

    def test_list_with_sort_skip_limit(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            # Insert 5 records with increasing updated_at
            for i in range(5):
                await adapter.records.insert_one({
                    "_id": f"r{i}", "org_id": ORG, "entity_type_id": "et1",
                    "title": f"T{i}", "updated_at": f"2026-02-0{i+1}T00:00:00Z",
                    "deleted_at": None,
                })
            # Motor pattern: db.records.find({...}).sort([...]).skip(0).limit(3)
            docs = await (
                adapter.records
                .find({"org_id": ORG, "entity_type_id": "et1"})
                .sort([("updated_at", -1)])
                .skip(0)
                .limit(3)
                .to_list(3)
            )
            assert len(docs) == 3
            titles = [d["title"] for d in docs]
            assert titles == ["T4", "T3", "T2"], f"unexpected order: {titles}"
        asyncio.run(run())

    def test_update_one(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            await adapter.records.insert_one({
                "_id": "u1", "org_id": ORG, "title": "old", "deleted_at": None,
            })
            r = await adapter.records.update_one(
                {"_id": "u1"}, {"$set": {"title": "new"}},
            )
            assert r.modified_count == 1
            got = await adapter.records.find_one({"_id": "u1"})
            assert got["title"] == "new"
        asyncio.run(run())

    def test_soft_delete(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            await adapter.records.insert_one({
                "_id": "d1", "org_id": ORG, "deleted_at": None,
            })
            await adapter.records.update_one(
                {"_id": "d1"}, {"$set": {"deleted_at": "2026-02-05T00:00:00Z"}},
            )
            got = await adapter.records.find_one({"_id": "d1"})
            assert got["deleted_at"] is not None
        asyncio.run(run())

    def test_count_documents(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            # Fresh count
            n = await adapter.records.count_documents({"org_id": "nobody"})
            assert n == 0
        asyncio.run(run())


# ─────────────────── pattern 2 · browse aggregate ───────────────────
class TestPattern2_BrowseAggregate:
    """Mirrors routes/browse.py::_facet_group — the aggregate that produces
    per-entity_type counts + per-category counts + per-tag counts."""

    def test_entity_type_facet_pipeline(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            # Seed a mixed dataset (3 types × 2 records)
            for et in ("et_a", "et_b", "et_c"):
                for i in range(2):
                    await adapter.records.insert_one({
                        "_id": f"{et}-{i}", "org_id": ORG,
                        "entity_type_id": et, "title": f"{et}#{i}",
                        "deleted_at": None,
                    })
            pipe = [
                {"$match": {"org_id": ORG}},
                {"$group": {"_id": "$entity_type_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 50},
            ]
            out = await adapter.records.aggregate(pipe).to_list(100)
            assert len(out) == 3
            for row in out:
                assert row["count"] == 2
        asyncio.run(run())

    def test_tag_facet_unwind_pipeline(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            await adapter.records.insert_one({
                "_id": "t1", "org_id": ORG, "tag_ids": ["hot", "new"],
            })
            await adapter.records.insert_one({
                "_id": "t2", "org_id": ORG, "tag_ids": ["hot"],
            })
            pipe = [
                {"$match": {"org_id": ORG}},
                {"$unwind": {"path": "$tag_ids", "preserveNullAndEmptyArrays": False}},
                {"$group": {"_id": "$tag_ids", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
            out = await adapter.records.aggregate(pipe).to_list(50)
            counts = {row["_id"]: row["count"] for row in out}
            assert counts.get("hot") == 2
            assert counts.get("new") == 1
        asyncio.run(run())


# ─────────────────── pattern 3 · category descendant lookup ───────────────────
class TestPattern3_CategoryDescendants:
    """Mirrors services/categories.py::descendant_ids_including_self — uses
    `path` array `$in` (no aggregate, just find with array-membership)."""

    def test_descendants_via_path_array(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            # Build tree:  A ── B ── C
            #                └── D
            for cid, name, path in [
                ("A", "Root", ["A"]),
                ("B", "Child of A", ["A", "B"]),
                ("C", "Child of B", ["A", "B", "C"]),
                ("D", "Sibling of B", ["A", "D"]),
            ]:
                await adapter.categories.insert_one({
                    "_id": cid, "org_id": ORG, "name": name, "path": path,
                    "deleted_at": None,
                })
            # Query: all descendants of "A" (should be A, B, C, D)
            docs = await adapter.categories.find(
                {"org_id": ORG, "path": "A", "deleted_at": None},
            ).to_list(100)
            assert sorted(d["_id"] for d in docs) == ["A", "B", "C", "D"]

            # Query: descendants of "B" (should be B, C)
            docs2 = await adapter.categories.find(
                {"org_id": ORG, "path": "B", "deleted_at": None},
            ).to_list(100)
            assert sorted(d["_id"] for d in docs2) == ["B", "C"]
        asyncio.run(run())


# ─────────────────── index create — smoke test ───────────────────
class TestIndexes:
    def test_simple_index(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            await adapter.records.create_index([("org_id", 1)])
        asyncio.run(run())

    def test_compound_index(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            await adapter.records.create_index(
                [("org_id", 1), ("entity_type_id", 1), ("updated_at", -1)],
            )
        asyncio.run(run())

    def test_text_index(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await _wipe_motor(adapter)
            await adapter.records.create_index([("search_text", "text")])
        asyncio.run(run())
