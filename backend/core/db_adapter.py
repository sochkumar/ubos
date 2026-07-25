"""
Phase D0 — Database Adapter POC.

Purpose: prove (or disprove) that `mongita` can serve UBOS's real query
patterns. Provides a Motor-DB-shaped facade so existing callsites remain
unchanged: `get_database_adapter().records.insert_one(...)` continues to
work the same way `db.records.insert_one(...)` does today.

Environment:
    UBOS_DB_MODE           = "online" (default) | "offline"
    UBOS_OFFLINE_DATA_DIR  = filesystem path (default: ~/.ubos/data)

Motor is unchanged — the MotorAdapter is a strict passthrough. Mongita
support is emulated: every mongita call runs on `asyncio.to_thread` so
it doesn't block the loop, and cursor chaining (`.sort().skip().limit()`)
is deferred until `to_list()` / iteration.

Known mongita limitations (surfaced during D0 probing):
    - `aggregate()` is not implemented at all
    - No `$text` / `$regex` filters
    - No `projection` argument to `find()`
    - Compound and text indexes rejected
    - Various operator gaps
The adapter surfaces these as clear NotImplementedError / MongitaError,
so calling code fails loudly rather than silently returning wrong data.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Iterable, Optional


# ══════════════════════════════════════════════════════════════════════
# Cursor emulation for mongita — Motor-shaped async cursor
# ══════════════════════════════════════════════════════════════════════
class _MongitaAsyncCursor:
    """Async cursor emulating Motor's cursor API on top of mongita's
    synchronous cursor. Chained `.sort()/.skip()/.limit()` calls are buffered
    and applied at iteration time; the actual DB read happens inside
    `asyncio.to_thread` so the event loop stays responsive.
    """

    def __init__(self, coll, filt: Optional[dict], projection: Any = None):
        # Mongita does NOT support projection — surface that up front rather
        # than silently returning full docs.
        if projection is not None:
            raise NotImplementedError(
                "mongita.find(projection=...) is not supported. Read full docs.",
            )
        self._coll = coll
        self._filt = filt or {}
        self._sort = None
        self._skip = 0
        self._limit = None
        self._materialized: Optional[list] = None
        self._idx = 0

    def sort(self, spec, direction: int | None = None):
        # Motor accepts either a list of tuples or `(key, direction)`.
        if isinstance(spec, str) and direction is not None:
            self._sort = [(spec, direction)]
        else:
            self._sort = list(spec)
        return self

    def skip(self, n: int):
        self._skip = n
        return self

    def limit(self, n: int):
        self._limit = n
        return self

    def _materialize_sync(self) -> list:
        c = self._coll.find(self._filt)
        # Mongita cursor supports .sort(key, dir) for a SINGLE key only.
        if self._sort:
            if len(self._sort) > 1:
                raise NotImplementedError(
                    "mongita cursor supports single-key sort only; "
                    f"got {len(self._sort)} keys: {self._sort}",
                )
            k, d = self._sort[0]
            c = c.sort(k, d)
        docs = list(c)
        # Mongita's cursor .skip()/.limit() also exist but re-applying in
        # Python is safer and matches Motor semantics 1:1.
        if self._skip:
            docs = docs[self._skip:]
        if self._limit is not None:
            docs = docs[: self._limit]
        return docs

    async def _materialize(self) -> list:
        if self._materialized is None:
            self._materialized = await asyncio.to_thread(self._materialize_sync)
        return self._materialized

    async def to_list(self, length: int | None):
        docs = await self._materialize()
        if length is None:
            return docs
        return docs[:length]

    def __aiter__(self):
        return self

    async def __anext__(self):
        docs = await self._materialize()
        if self._idx >= len(docs):
            raise StopAsyncIteration
        d = docs[self._idx]
        self._idx += 1
        return d


class _MotorPassthroughCursor:
    """Wraps a Motor cursor. We don't strictly need this — Motor's own cursor
    is already the right shape — but keeping it explicit makes both adapters
    return the SAME wrapper type from `find()`, which helps testing.
    """

    def __init__(self, motor_cursor):
        self._c = motor_cursor

    def sort(self, *a, **kw):
        self._c = self._c.sort(*a, **kw)
        return self

    def skip(self, n):
        self._c = self._c.skip(n)
        return self

    def limit(self, n):
        self._c = self._c.limit(n)
        return self

    def __aiter__(self):
        return self._c.__aiter__()

    async def to_list(self, length):
        return await self._c.to_list(length)


# ══════════════════════════════════════════════════════════════════════
# Collection adapters
# ══════════════════════════════════════════════════════════════════════
class _MongitaCollection:
    """Async-shaped wrapper around a mongita Collection.

    Every write/read call jumps to `asyncio.to_thread` so the caller can
    `await` uniformly. `find()` returns a lazy async cursor.
    """

    def __init__(self, coll, name: str):
        self._c = coll
        self.name = name

    # ── writes ──
    async def insert_one(self, doc: dict):
        return await asyncio.to_thread(self._c.insert_one, doc)

    async def insert_many(self, docs: list[dict]):
        return await asyncio.to_thread(self._c.insert_many, docs)

    async def update_one(self, filt: dict, update: dict, upsert: bool = False):
        return await asyncio.to_thread(self._c.update_one, filt, update, upsert)

    async def update_many(self, filt: dict, update: dict):
        return await asyncio.to_thread(self._c.update_many, filt, update)

    async def delete_one(self, filt: dict):
        return await asyncio.to_thread(self._c.delete_one, filt)

    async def delete_many(self, filt: dict):
        return await asyncio.to_thread(self._c.delete_many, filt)

    async def replace_one(self, filt: dict, replacement: dict, upsert: bool = False):
        return await asyncio.to_thread(self._c.replace_one, filt, replacement, upsert)

    # ── reads ──
    async def find_one(self, filt: dict | None = None, projection=None):
        if projection is not None:
            raise NotImplementedError(
                "mongita.find_one(projection=...) is not supported.",
            )
        return await asyncio.to_thread(self._c.find_one, filt or {})

    def find(self, filt: dict | None = None, projection: Any = None):
        # Cursor is lazy — no async involved until awaited.
        return _MongitaAsyncCursor(self._c, filt, projection)

    async def count_documents(self, filt: dict | None = None):
        return await asyncio.to_thread(self._c.count_documents, filt or {})

    # ── aggregate — the big one ──
    def aggregate(self, pipeline: list[dict]):
        # Mongita's aggregate is entirely unimplemented (1.2.0).
        # Raising eagerly (not on to_list()) so callers see the failure at
        # dispatch time.
        raise NotImplementedError(
            "mongita.aggregate() is not implemented in mongita 1.2.0. "
            "Pipeline (first 2 stages): "
            + str(pipeline[:2]),
        )

    # ── indexes ──
    async def create_index(self, spec, **kwargs):
        # Strip Motor-only kwargs mongita rejects.
        clean = {k: v for k, v in kwargs.items() if k in ("unique", "name", "sparse")}
        try:
            return await asyncio.to_thread(self._c.create_index, spec, **clean)
        except Exception as e:  # noqa: BLE001
            # Compound & text indexes fail here — swallow so seed / startup
            # can proceed, but surface the diagnostic.
            raise NotImplementedError(
                f"mongita rejected create_index({spec!r}, {clean}): {e}",
            ) from e


class _MotorCollection:
    """Thin Motor collection passthrough (kept for symmetry & typing)."""

    def __init__(self, coll):
        self._c = coll
        self.name = coll.name

    async def insert_one(self, doc): return await self._c.insert_one(doc)
    async def insert_many(self, docs): return await self._c.insert_many(docs)
    async def update_one(self, f, u, upsert=False): return await self._c.update_one(f, u, upsert=upsert)
    async def update_many(self, f, u): return await self._c.update_many(f, u)
    async def delete_one(self, f): return await self._c.delete_one(f)
    async def delete_many(self, f): return await self._c.delete_many(f)
    async def replace_one(self, f, r, upsert=False): return await self._c.replace_one(f, r, upsert=upsert)
    async def find_one(self, f=None, projection=None): return await self._c.find_one(f, projection)
    def find(self, f=None, projection=None):
        return _MotorPassthroughCursor(self._c.find(f, projection))
    async def count_documents(self, f=None): return await self._c.count_documents(f or {})
    def aggregate(self, pipeline): return _MotorPassthroughCursor(self._c.aggregate(pipeline))
    async def create_index(self, spec, **kw): return await self._c.create_index(spec, **kw)


# ══════════════════════════════════════════════════════════════════════
# Database adapters (top-level facade)
# ══════════════════════════════════════════════════════════════════════
class DatabaseAdapter:
    """Motor-DB-shaped facade. `adapter.<collection_name>` returns a
    collection wrapper that quacks like a Motor collection."""

    mode: str = "abstract"

    def __getattr__(self, name: str):  # pragma: no cover
        raise NotImplementedError

    async def list_collection_names(self) -> list[str]:  # pragma: no cover
        raise NotImplementedError

    def __getitem__(self, name):
        # `db["records"]` should work same as `db.records`.
        return self.__getattr__(name)


class MotorAdapter(DatabaseAdapter):
    """Strict passthrough — MUST be behaviorally identical to today's code."""
    mode = "online"

    def __init__(self, motor_db):
        self._db = motor_db
        self._cache: dict[str, _MotorCollection] = {}

    def __getattr__(self, name):
        # Guard against Python double-underscore lookups.
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._cache:
            self._cache[name] = _MotorCollection(self._db[name])
        return self._cache[name]

    async def list_collection_names(self):
        return await self._db.list_collection_names()


class MongitaAdapter(DatabaseAdapter):
    """Wraps `mongita.MongitaClientDisk`. Every call goes through
    `asyncio.to_thread` so the event loop stays free."""
    mode = "offline"

    def __init__(self, data_dir: str | Path, db_name: str = "ubos"):
        from mongita import MongitaClientDisk  # lazy import
        self._data_dir = str(Path(data_dir).expanduser())
        Path(self._data_dir).mkdir(parents=True, exist_ok=True)
        self._client = MongitaClientDisk(host=self._data_dir)
        self._db = self._client[db_name]
        self._cache: dict[str, _MongitaCollection] = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._cache:
            self._cache[name] = _MongitaCollection(self._db[name], name)
        return self._cache[name]

    async def list_collection_names(self):
        return await asyncio.to_thread(self._db.list_collection_names)


# ══════════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════════
_ADAPTER_INSTANCE: DatabaseAdapter | None = None


def get_database_adapter() -> DatabaseAdapter:
    """Singleton factory. `UBOS_DB_MODE` env var picks the impl.

    online (default): Motor client on `MONGO_URL` + `DB_NAME` (current prod).
    offline         : Mongita on-disk at `UBOS_OFFLINE_DATA_DIR`.
    """
    global _ADAPTER_INSTANCE
    if _ADAPTER_INSTANCE is not None:
        return _ADAPTER_INSTANCE

    mode = os.environ.get("UBOS_DB_MODE", "online").lower()
    if mode == "offline":
        data_dir = os.environ.get("UBOS_OFFLINE_DATA_DIR", "~/.ubos/data")
        db_name  = os.environ.get("DB_NAME", "ubos")
        _ADAPTER_INSTANCE = MongitaAdapter(data_dir, db_name=db_name)
    else:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        motor_db = client[os.environ["DB_NAME"]]
        _ADAPTER_INSTANCE = MotorAdapter(motor_db)
    return _ADAPTER_INSTANCE


def reset_adapter_for_tests():
    """Used by pytest to blow away the singleton between adapter runs."""
    global _ADAPTER_INSTANCE
    _ADAPTER_INSTANCE = None
