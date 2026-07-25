"""
Phase D0.6 — bundled `mongod` integration test.

Spins up a `MongodLauncher` on a random port pointed at `tmp_path`, then
runs UBOS's 11 capability tests against it via a `MotorAdapter`. The
launched process is torn down in fixture teardown.

Expected: 11/11 pass — behaviorally identical to Atlas Motor, because
we're using the real MongoDB engine. If any test fails, the mongod
bundle story is broken (config wrong, version incompatible, etc.).

Skips itself if `mongod` isn't on PATH or `UBOS_MONGOD_BIN` isn't set —
CI without mongod installed doesn't error, just skips.
"""
from __future__ import annotations

import asyncio
import shutil
import uuid
import pytest

from core.mongod_launcher import (
    MongodLauncher, MongodLauncherError, reset_bundled_launcher_for_tests,
)
from core.db_adapter import MotorAdapter

_MONGOD_AVAILABLE = shutil.which("mongod") is not None
pytestmark = pytest.mark.skipif(
    not _MONGOD_AVAILABLE,
    reason="mongod binary not available on this host — skipping D0.6 bundled tests",
)

ORG = "d0-6-bundled"


# ─────────────────── fixtures ───────────────────
@pytest.fixture(scope="module")
def bundled_mongod(tmp_path_factory):
    """Module-scoped: one mongod for the whole file, torn down at end."""
    reset_bundled_launcher_for_tests()
    data = tmp_path_factory.mktemp("mongod_data")
    logs = tmp_path_factory.mktemp("mongod_logs")
    launcher = MongodLauncher(data_dir=data, log_dir=logs)
    launcher.start()
    try:
        launcher.wait_until_ready(timeout=30)
    except MongodLauncherError:
        launcher.stop()
        raise
    yield launcher
    launcher.stop()


@pytest.fixture
def make_adapter(bundled_mongod):
    """Factory that returns a fresh `MotorAdapter` inside the caller's
    event loop, matching the D0/D0.5 test contract."""
    def factory():
        from motor.motor_asyncio import AsyncIOMotorClient
        # Fresh db per test to avoid cross-test pollution.
        client = AsyncIOMotorClient(bundled_mongod.uri)
        return MotorAdapter(client[f"ubos_d0_6_{uuid.uuid4().hex[:6]}"])
    factory.kind = "bundled"
    return factory


# ─────────────────── the 11 capability tests, verbatim ───────────────────
class TestBundled_RecordsCRUD:
    def test_insert_and_find(self, make_adapter):
        async def run():
            adapter = make_adapter()
            rid = str(uuid.uuid4())
            await adapter.records.insert_one({
                "_id": rid, "org_id": ORG, "entity_type_id": "et1",
                "title": "Chair", "record_number": "REC-000001",
                "fields": {"sku": "SKU-A", "price": 42.5},
                "search_text": "chair sku-a",
                "deleted_at": None,
            })
            got = await adapter.records.find_one({"_id": rid})
            assert got is not None and got["title"] == "Chair"
        asyncio.run(run())

    def test_list_with_sort_skip_limit(self, make_adapter):
        async def run():
            adapter = make_adapter()
            for i in range(5):
                await adapter.records.insert_one({
                    "_id": f"r{i}", "org_id": ORG, "entity_type_id": "et1",
                    "title": f"T{i}", "updated_at": f"2026-02-0{i+1}T00:00:00Z",
                    "deleted_at": None,
                })
            docs = await (
                adapter.records
                .find({"org_id": ORG, "entity_type_id": "et1"})
                .sort([("updated_at", -1)]).skip(0).limit(3).to_list(3)
            )
            assert [d["title"] for d in docs] == ["T4", "T3", "T2"]
        asyncio.run(run())

    def test_update_one(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await adapter.records.insert_one({"_id": "u1", "org_id": ORG, "title": "old", "deleted_at": None})
            r = await adapter.records.update_one({"_id": "u1"}, {"$set": {"title": "new"}})
            assert r.modified_count == 1
            got = await adapter.records.find_one({"_id": "u1"})
            assert got["title"] == "new"
        asyncio.run(run())

    def test_soft_delete(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await adapter.records.insert_one({"_id": "d1", "org_id": ORG, "deleted_at": None})
            await adapter.records.update_one({"_id": "d1"}, {"$set": {"deleted_at": "2026-02-05T00:00:00Z"}})
            got = await adapter.records.find_one({"_id": "d1"})
            assert got["deleted_at"] is not None
        asyncio.run(run())

    def test_count_documents(self, make_adapter):
        async def run():
            adapter = make_adapter()
            n = await adapter.records.count_documents({"org_id": "nobody"})
            assert n == 0
        asyncio.run(run())


class TestBundled_BrowseAggregate:
    def test_entity_type_facet_pipeline(self, make_adapter):
        async def run():
            adapter = make_adapter()
            for et in ("et_a", "et_b", "et_c"):
                for i in range(2):
                    await adapter.records.insert_one({
                        "_id": f"{et}-{i}", "org_id": ORG,
                        "entity_type_id": et, "deleted_at": None,
                    })
            pipe = [
                {"$match": {"org_id": ORG}},
                {"$group": {"_id": "$entity_type_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 50},
            ]
            out = await adapter.records.aggregate(pipe).to_list(100)
            assert len(out) == 3 and all(row["count"] == 2 for row in out)
        asyncio.run(run())

    def test_tag_facet_unwind_pipeline(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await adapter.records.insert_one({"_id": "t1", "org_id": ORG, "tag_ids": ["hot", "new"]})
            await adapter.records.insert_one({"_id": "t2", "org_id": ORG, "tag_ids": ["hot"]})
            pipe = [
                {"$match": {"org_id": ORG}},
                {"$unwind": {"path": "$tag_ids", "preserveNullAndEmptyArrays": False}},
                {"$group": {"_id": "$tag_ids", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
            out = await adapter.records.aggregate(pipe).to_list(50)
            counts = {r["_id"]: r["count"] for r in out}
            assert counts.get("hot") == 2 and counts.get("new") == 1
        asyncio.run(run())


class TestBundled_CategoryDescendants:
    def test_descendants_via_path_array(self, make_adapter):
        async def run():
            adapter = make_adapter()
            for cid, name, path in [
                ("A", "Root", ["A"]),
                ("B", "Child of A", ["A", "B"]),
                ("C", "Child of B", ["A", "B", "C"]),
                ("D", "Sibling of B", ["A", "D"]),
            ]:
                await adapter.categories.insert_one({
                    "_id": cid, "org_id": ORG, "name": name, "path": path, "deleted_at": None,
                })
            docs = await adapter.categories.find(
                {"org_id": ORG, "path": "A", "deleted_at": None},
            ).to_list(100)
            assert sorted(d["_id"] for d in docs) == ["A", "B", "C", "D"]
            docs2 = await adapter.categories.find(
                {"org_id": ORG, "path": "B", "deleted_at": None},
            ).to_list(100)
            assert sorted(d["_id"] for d in docs2) == ["B", "C"]
        asyncio.run(run())


class TestBundled_Indexes:
    def test_simple_index(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await adapter.records.create_index([("org_id", 1)])
        asyncio.run(run())

    def test_compound_index(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await adapter.records.create_index(
                [("org_id", 1), ("entity_type_id", 1), ("updated_at", -1)],
            )
        asyncio.run(run())

    def test_text_index(self, make_adapter):
        async def run():
            adapter = make_adapter()
            await adapter.records.create_index([("search_text", "text")])
        asyncio.run(run())


# ─────────────────── launcher sanity ───────────────────
class TestBundled_LauncherLifecycle:
    def test_launcher_uri_is_local(self, bundled_mongod):
        assert bundled_mongod.uri.startswith("mongodb://127.0.0.1:")
        assert bundled_mongod.is_alive()

    def test_launcher_log_exists(self, bundled_mongod):
        assert bundled_mongod.log_path.exists()
        assert bundled_mongod.log_path.stat().st_size > 0
