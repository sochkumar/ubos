# UBOS Desktop — Phase D0.5 GO/NO-GO Report · MontyDB Spike

**Date:** 2026-02-14
**Author:** E1 (Emergent)
**Status:** **NO-GO on montydb.** Same blocker as mongita — `Collection.aggregate` is not implemented.
**Recommendation:** Proceed with **Path A: bundle `mongod`**. Both pure-Python engines are eliminated.

---

## TL;DR

MontyDB (v2.5.6) is a strictly better pure-Python MongoDB clone than
mongita — it handles projections, compound indexes, text indexes, `$regex`,
and multi-key sort correctly. But it shares the exact same terminal gap:

> `NotImplementedError: 'MontyCollection.aggregate' is NOT implemented !`

Every aggregate pipeline stage (`$match`, `$group`, `$unwind`, `$facet`,
`$lookup`, `$sort`, `$limit`, even empty `[]`) raises immediately. Because
UBOS's `/records/browse` endpoint depends on 3 aggregate pipelines to
compute facets, offline mode on montydb would ship broken exactly as it
would on mongita.

**Conclusion: neither pure-Python engine can replace MongoDB. Pivot to bundled `mongod`.**

---

## Housekeeping — Directive 1 status

| Item | Status |
|------|--------|
| `db_adapter.py` + `test_d0_adapter_capability.py` landed to main | ✅ Kept |
| Header note added to `db_adapter.py` (mentions D0 provenance) | ✅ |
| `mongita==1.2.0` + `sortedcontainers==2.4.0` retained in `requirements.txt` | ✅ (D0.5 comparison) |
| `montydb==2.5.6` added to `requirements.txt` | ✅ |
| Full pytest with `UBOS_DB_MODE=online` (default) | 🟡 See breakdown |
| Motor path behaviorally unchanged | ✅ |

**Pytest count (default online mode, clean seed):**

```
tests/test_ubos_phase8_browse.py          16 passed
tests/test_labels_no_code_mode.py         13 passed
tests/test_d0_adapter_capability.py       27 passed, 6 failed (all mongita/montydb — EXPECTED)
────────────────────────────────────────────────────
                                          56 passed, 6 expected-fail
```

The 6 failures are the documented mongita+montydb aggregate/index gaps — they
prove the capability matrix is correct, not regressions.

**Wider suite:** 277 pass / 25 fail / 7 error out of 302+ total. The 25/7
failures live in `test_ubos_phase0.py`, `test_ubos_phase3a.py`,
`test_ubos_phase5a.py`, `test_ubos_phase5a_hotfix.py` — all use the legacy
pre-auth `X-Org-Id` header pattern (broken since Phase 5, unrelated to D0/D0.5).
Test-hygiene sprint tracked separately.

---

## D0.5 deliverables

| File | Change |
|------|--------|
| `/app/backend/requirements.txt` | +1 line: `montydb==2.5.6` |
| `/app/backend/core/db_adapter.py` | New `_MontyDBCollection`, `_MontyDBAsyncCursor`, `MontyDBAdapter` classes. Factory now routes `UBOS_OFFLINE_ENGINE={mongita\|montydb}`; montydb is the offline default. Header updated with D0-provenance note per Directive 1. |
| `/app/backend/tests/test_d0_adapter_capability.py` | Adapter fixture params extended `["motor","mongita","montydb"]` — same 11 tests now run **33 times**. |
| `/app/test_reports/desktop_phase_d0_5_report.md` | This file. |
| MongitaAdapter retained in the tree | ✅ Per Directive 2 non-goals — kept for comparison. |

---

## Full capability matrix (Motor / Mongita / MontyDB)

| Test | Motor | Mongita | MontyDB |
|------|:---:|:---:|:---:|
| **Pattern 1 · Records CRUD** |||
| insert_one + find_one | ✅ | ✅ | ✅ |
| find + sort + skip + limit | ✅ | ✅ | ✅ |
| update_one with `$set` | ✅ | ✅ | ✅ |
| soft-delete pattern | ✅ | ✅ | ✅ |
| count_documents | ✅ | ✅ | ✅ |
| **Pattern 2 · Browse aggregate** |||
| `$match + $group + $sort + $limit` | ✅ | ❌ | ❌ |
| `$match + $unwind + $group + $sort` | ✅ | ❌ | ❌ |
| **Pattern 3 · Category descendants** |||
| array-membership filter (`{"path": "A"}`) | ✅ | ✅ | ✅ |
| **Indexes** |||
| simple single-key index | ✅ | ✅ | ✅ |
| compound `(a,b,c)` index | ✅ | ❌ | ✅ |
| text index (`("field","text")`) | ✅ | ❌ | ✅ |
| **Totals** | **11/11** | **7/11** | **9/11** |

---

## The six named gaps — per-engine verdict

| Gap | Mongita 1.2.0 | MontyDB 2.5.6 |
|-----|:---:|:---:|
| `Collection.aggregate()` supported | ❌ Not implemented at all | ❌ **Not implemented at all** (identical error class) |
| Compound indexes accepted | ❌ Rejected as "multi-key not supported" | ✅ Works |
| `$text` operator + text index | ❌ Text index rejected; `$search` operator missing | ✅ Text index accepted; ❌ `$text` operator still raises "not supported" |
| `$regex` filter operator | ❌ Missing | ✅ Works |
| `find(filter, projection)` — projection arg | ❌ Rejects the argument | ✅ Native support |
| Multi-key sort `.sort([(k1,1),(k2,-1)])` | ❌ Single-key only | ✅ Works |

**Score:**
- Mongita clears 0/6.
- MontyDB clears 4/6 fully + 1/2 on the text gate (index works, operator doesn't).
- **Neither clears the `aggregate` gate — the biggest one.**

### Actual errors (verbatim)

```
NotImplementedError: 'MontyCollection.aggregate' is NOT implemented !
```

```
MongitaError: Mongita does not support '$text'. These filter operators are
    supported: ('$in', '$eq', '$gt', '$gte', '$lt', '$lte', ...)
```

```
NotImplementedError: 'query op $text is NOT implemented'
```

---

## Perf ballpark (1000-doc benchmark, same box)

| Op | Motor + MongoDB | Mongita | MontyDB (SQLite storage) |
|----|---|---|---|
| `insert_one` × 1000 (serial) | 191 ms | 384 ms | **3,460 ms** (~18× Motor) |
| `find + sort + limit(1000)` | 4 ms | 6 ms | 32 ms |
| `aggregate` group-by | 1 ms | **UNSUPPORTED** | **UNSUPPORTED** |

Even ignoring the aggregate gap, montydb's SQLite backend imposes an
18× write penalty. That's unusable for anything realtime — every record
edit, every CSV import, every bulk update would feel like a database
crash. Mongita's file-per-doc storage is much faster but still fails on
the same capabilities.

---

## New gaps discovered in montydb (not present in mongita's list)

None material. MontyDB is strictly a better clone of mongita — projections,
regex, compound/text indexes, multi-key sort all work. But the two hard
blockers (`aggregate`, `$text` operator) are shared, and montydb's write
throughput is ~9× worse than mongita's.

---

## GO/NO-GO recommendation

Per Directive 2's rule ("**If it fails any of the 6 named gaps: stop and
report. Do NOT attempt workarounds.**"):

**MontyDB FAILS gate #1 (`Collection.aggregate` not implemented) and gate #3
(`$text` operator still raises "not supported"). Per rule → STOP.**

### The pure-Python route is exhausted

- mongita: 4/6 gaps hit → NO-GO
- montydb: 2/6 gaps hit + 18× write slowdown → NO-GO

There's no third serious pure-Python MongoDB implementation on PyPI worth
spiking. `pymongoexplain`, `motor` itself, etc. all require a real server.

### Path A — bundle `mongod` — is now the recommendation, uncontested

**Why it's the right call:**

1. **Same query engine as Atlas** — zero query gaps, zero adapter maintenance.
2. **Existing code doesn't change at all** — offline mode swaps `MONGO_URL`
   to `mongodb://localhost:27017` pointing at a bundled `mongod` process
   that Electron manages.
3. **Standard Electron pattern** — plenty of prior art (e.g. Meteor's local
   development server, various desktop CMS apps).
4. **The `DatabaseAdapter` layer we just built is still valuable** — it
   isolates online-vs-offline concerns (mongod lifecycle wrapper,
   temp-dir setup, log routing, first-run seed) at a clean seam even
   though the driver stays Motor for both modes.

**Trade-off:** installer size. Bundle sizes for mongod community edition:
- Linux x64: ~95 MB unpacked, ~35 MB compressed
- macOS Intel/ARM: ~100 MB
- Windows x64: ~110 MB
Total desktop installer per platform lands around ~180–220 MB after
including Node/Electron/UI. That's within the norm for Electron desktop
apps (Slack, Notion, Discord all ship 200–300 MB installers).

### Path C — kill offline mode entirely — still on the table

If the ~200 MB installer is genuinely a dealbreaker, the honest answer
becomes "UBOS is online-only." Given the customer explicitly asked for
airgapped/offline mode, I don't recommend this — but it's a legitimate call
if binary size is a hard product constraint.

---

## Awaiting decision

**Recommend:** GO on **Path A — bundle `mongod`**. Approve and I'll:

1. Add `D0.6` — download + verify `mongod` binaries for Linux x64, macOS Intel/ARM, Windows x64. Produce a bundle-size table and a per-OS launcher stub. Roughly 4 hours.
2. Then proceed to D1 — Electron integration + first-run picker + mongod lifecycle wrapper inside `DatabaseAdapter` (or a companion `OfflineEngineManager`).

If you want to reconsider Path C (kill offline), tell me and I'll clean up
the mongita/montydb adapter code but keep the `MotorAdapter` layer in main
(still useful for future test-mocking).

---

## Files touched (D0.5 total)

- `/app/backend/requirements.txt` (+1 line: montydb)
- `/app/backend/core/db_adapter.py` (+140 LOC: `_MontyDBCollection`,
  `_MontyDBAsyncCursor`, `MontyDBAdapter`, factory extension, header note)
- `/app/backend/tests/test_d0_adapter_capability.py` (+7 LOC: params
  extended with `montydb`)
- `/app/test_reports/desktop_phase_d0_5_report.md` (this file)

**Guardrail check:**
- ✅ Online mode untouched.
- ✅ MongitaAdapter code retained per non-goal #4.
- ✅ No Electron / installer / mongod-bundling work.
- ✅ No modules outside adapter layer refactored.
- ✅ Time budget honoured: killer signal (montydb also missing aggregate)
      surfaced during probing in ~15 minutes; wrote the writeup within the
      1-day cap.
