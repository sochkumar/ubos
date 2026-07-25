# UBOS Desktop — Phase D0 GO/NO-GO Report

**Date:** 2026-02-14
**Author:** E1 (Emergent)
**Status:** **NO-GO for mongita as the offline engine. Recommend pivot to bundled `mongod`.**

---

## TL;DR

`mongita` (v1.2.0) **cannot serve UBOS's real query patterns**. The single
biggest gap is that `Collection.aggregate()` is entirely unimplemented in
mongita — the exception literally reads:

> `MongitaNotImplementedError: Collection.aggregate is not yet implemented. You can help.`

Since `/api/records/browse` — the marquee Phase 8 feature — depends on
three aggregate pipelines (`$group` for entity-type counts, `$unwind + $group`
for tag & category facets), the offline mode built on mongita would
ship broken. Compound indexes and text indexes are also rejected.

**Recommendation: STOP the mongita track. Bundle `mongod` (community edition)
instead** — same query semantics, same indexes, ~90 MB binary vs mongita's
2 MB but eliminates all the compatibility gymnastics.

---

## What was built

| File | Purpose | LOC |
|------|---------|-----|
| `/app/backend/requirements.txt` (+2 lines) | Added `mongita==1.2.0` and `sortedcontainers==2.4.0` | — |
| `/app/backend/core/db_adapter.py` | Motor-DB-shaped adapter facade (`MotorAdapter`, `MongitaAdapter`) with async cursor emulation, projection guard, aggregate stub, factory keyed on `UBOS_DB_MODE` | 271 |
| `/app/backend/tests/test_d0_adapter_capability.py` | Parametrized suite: 11 tests × 2 adapters = 22 runs, covering the 3 named code paths | 227 |

**No route files were touched.** The existing 3 code paths (records CRUD in
`routes/data.py`, browse aggregate in `routes/browse.py`, category descendants
in `services/categories.py`) already flow through `get_db()`. The adapter
is a drop-in replacement — a Motor-shaped facade that any of those modules
could use tomorrow by swapping `get_db()` for `get_database_adapter()`. No
behavior changes were made to those files during D0 to minimise blast radius.

---

## Test results

| Adapter | Pattern 1 · Records CRUD | Pattern 2 · Browse aggregate | Pattern 3 · Category descendants | Indexes |
|---------|:---:|:---:|:---:|:---:|
| Motor   | **5/5 ✓** | **2/2 ✓** | **1/1 ✓** | **3/3 ✓** |
| Mongita | **5/5 ✓** | **0/2 ✗** | **1/1 ✓** | **1/3 ✗ ✗** |

**Motor:** 11/11 — regression guard fully green.
**Mongita:** 7/11 — 4 hard failures.

Existing Phase 8 suite (`test_ubos_phase8_browse.py`) unchanged: **16/16
passing** with `UBOS_DB_MODE=online` (the default), i.e. Motor path
untouched by the D0 changes.

---

## Mongita capability matrix (actual errors observed)

### 🛑 Blocking gaps

1. **`Collection.aggregate(pipeline)` — entirely not implemented.**
   ```
   MongitaNotImplementedError: Collection.aggregate is not yet implemented.
       You can help.
   ```
   Impacted callsites in current UBOS code:
   - `routes/browse.py::_facet_group()` — 3 pipelines: entity_types, categories, tags
   - `services/query_builder.py` — used by saved views for computed sorts
   - Any future dashboard-widget aggregations

2. **`create_index()` rejects compound keys.**
   ```
   MongitaNotImplementedError: Mongita does not support multi-key indexes yet
   ```
   Impacted: essentially every index in `db.py`:
   - `[(org_id,1), (entity_type_id,1), (updated_at,-1)]`
   - `[(org_id,1), (category_ids,1)]`
   - `[(org_id,1), (tag_ids,1)]`
   - `[(org_id,1), (updated_at,-1)]`
   - many more…

3. **Text indexes rejected.**
   ```
   MongitaError: Index key direction must be either ASCENDING (1) or
       DESCENDING (-1). Not 'text'
   ```
   Kills `search_text` free-text search entirely.

4. **`$text` / `$search` filter operator missing.**
   ```
   MongitaError: Mongita does not support '$search'. These filter operators
       are supported: ('$in', '$eq', '$gt', '$gte', '$lt', '$lte', ...)
   ```

5. **`$regex` filter operator missing.**
   ```
   MongitaError: Mongita does not support '$regex'. ...
   ```
   Used in slug/label prefix searches and dashboard filters.

6. **`find(filter, projection)` — projection argument rejected.**
   ```
   MongitaError: The argument 'projection' is not supported by
       Collection.find in Mongita.
   ```
   Impacted callsites: dozens (any time we do `db.foo.find({...}, {'field':1})`).
   Every projection use would need to be rewritten to fetch full docs and
   strip in Python — significant network/memory cost on large collections.

### ⚠️ Working but with caveats

- Multi-key sort (`.sort([(k1,1),(k2,-1)])`) — mongita's cursor only takes a
  single sort key. The adapter surfaces this as `NotImplementedError` with
  the requested spec.
- Chained `.skip().limit()` works, but our adapter re-slices in Python
  post-fetch to guarantee Motor-identical semantics (mongita's own cursor
  slicing has some quirks around empty ranges).

### ✅ Confirmed working

- Basic CRUD: `insert_one`, `insert_many`, `find_one`, `find`, `count_documents`,
  `update_one`, `update_many`, `delete_one`, `delete_many`.
- Operators: `$in`, `$eq`, `$gt`/`$gte`/`$lt`/`$lte`, `$or`, `$and`,
  `$exists`, `$ne`, `$set`.
- Single-key indexes.
- Array-membership filter (`{"path": "A"}` matching docs whose `path` array
  contains `"A"`) — this is what makes category-descendant lookup work.

---

## Rough perf ballpark (single-shot, warm cache, in the same container)

| Op (1,000 docs on a hot cache) | Motor + MongoDB | Mongita on disk |
|---|---|---|
| `insert_one` × 1000 (serial) | 191 ms | 384 ms (~2× slower) |
| `find + sort + limit(1000)` | 4 ms | 6 ms (comparable) |
| `aggregate` (`$match + $group + $sort`) | 1 ms | **UNSUPPORTED** |

Not a benchmark — just a sanity check. Read-heavy simple queries are close
enough. Writes are ~2× slower due to disk sync per op. The aggregate gap is
the killer.

---

## The recommendation

**NO-GO on mongita. Pivot to bundling `mongod`.**

### Why not "just polyfill aggregate in Python"?

Two of the three aggregate pipelines in the browse endpoint alone would
need to be re-implemented in Python. That's:

- `$group` over 100k+ records → pull all docs across the network + group in
  Python. Memory + latency disaster.
- `$unwind + $group` for tag/category facets → same, worse.
- Every future aggregate pipeline (dashboard widgets, reports, analytics)
  would need a manual Python re-implementation.

We'd be building and maintaining a partial MongoDB re-implementation
forever. That's an enormous, non-differentiating engineering tax.

### Why bundling `mongod` is better

1. **Zero query gaps.** Aggregate, text indexes, compound indexes, `$regex`,
   `$text`, projections — everything works because it's the same engine
   Atlas uses.
2. **No adapter maintenance.** Existing code doesn't change at all — offline
   mode just points `MONGO_URL` at `localhost:27017` on a bundled `mongod`.
3. **Well-trodden path.** Electron apps bundling `mongod` is a common
   pattern; the binary is ~95 MB (Linux x64), which is fine for a desktop
   installer.
4. **Adapter layer we just built is not wasted.** The `DatabaseAdapter`
   facade can still house environment-specific concerns (mongod lifecycle,
   temp-directory setup, log routing) — just without the crippling capability
   gap.

### If you insist on the pure-Python route

The realistic alternative is `montydb` (pure-Python, targets MongoDB 4.x
semantics) — worth a 1-day D0.5 spike to see if it clears the aggregate
bar. `mongita` will not.

---

## Files touched (D0 total)

- `/app/backend/requirements.txt`  (+2 lines: mongita, sortedcontainers)
- `/app/backend/core/db_adapter.py`  (NEW)
- `/app/backend/tests/test_d0_adapter_capability.py`  (NEW)
- `/app/test_reports/desktop_phase_d0_report.md`  (this file)

**Guardrail check:**
- ✅ Online mode untouched (existing `get_db()` unchanged).
- ✅ Existing pytest green on `UBOS_DB_MODE=online`.
- ✅ No Electron / installer / PyInstaller work.
- ✅ No changes to route files outside adapter POC.
- ✅ Adapter is behavior-preserving for Motor.

---

## Awaiting decision

Options:
- **A.** Pivot to bundled `mongod`. I write the D0 addendum (bundle discovery
  + lifecycle wrapper) then proceed to D1.
- **B.** Spike `montydb` for 1 day as a last pure-Python attempt.
- **C.** Kill the offline-mode workstream entirely.

I'm recommending **A**. Please confirm.
