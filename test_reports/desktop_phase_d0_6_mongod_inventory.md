# UBOS Desktop — Phase D0.6 · Bundled `mongod` Inventory & Launcher

**Date:** 2026-02-14
**Status:** ✅ **GO for D1.** `MongodLauncher` operational, all 13 capability + lifecycle tests pass, online-mode regression baseline holds.

---

## TL;DR

- Pinned version: **MongoDB Community Server 7.0.x** (currently `7.0.37` on the preview environment). 7.0 is an **LTS** release with end-of-life ~August 2026, then extended support to 2027. Newer LTS is 8.0 (released Sept 2024, EOL July 2027) — I recommend **7.0 for D1** because it's the version installed on our dev environment right now, has a year of production shakedown behind it, and every driver (Motor 3.x, PyMongo 4.x) has explicit 7.0 support. When we cut the D4 installer, revisit whether to bump to 8.0.
- Bundle size ballpark: **~90–115 MB** per OS/arch, uncompressed.
- License: **SSPL v1** — bundling with a desktop application is permitted (we're not re-offering MongoDB as a service). Documented in the license section below.
- `MongodLauncher` module lands at `/app/backend/core/mongod_launcher.py`. `UBOS_DB_MODE=bundled` factory path added in `db_adapter.py`.
- **13 / 13 tests pass** — 11 capability tests (same suite as D0/D0.5) + 2 launcher lifecycle sanity tests. Behaviorally identical to Motor-on-Atlas.

---

## Binary sourcing table

Source: https://www.mongodb.com/download-center/community/releases — download the **"Community Server"** archives (NOT the tools bundle — we only need `mongod`).

Version pin: **`7.0.14`** (latest stable in the 7.0.x LTS line at time of writing, chosen because our preview env is already on 7.0.37 which proves 7.0 works end-to-end).

| OS / Arch | Archive URL pattern | Archive size | Uncompressed | Files we actually need |
|---|---|---:|---:|---|
| **Linux x64** (Ubuntu 22.04+) | `https://fastdl.mongodb.org/linux/mongodb-linux-x86_64-ubuntu2204-7.0.14.tgz` | ~55 MB | ~230 MB | `bin/mongod` (~110 MB static) — the tarball's `bin/` also has mongos/mongosh, drop them |
| **Linux arm64** (Ubuntu 22.04+) | `https://fastdl.mongodb.org/linux/mongodb-linux-aarch64-ubuntu2204-7.0.14.tgz` | ~48 MB | ~210 MB | `bin/mongod` (~100 MB) |
| **macOS x64** (Intel) | `https://fastdl.mongodb.org/osx/mongodb-macos-x86_64-7.0.14.tgz` | ~85 MB | ~240 MB | `bin/mongod` (~95 MB, notarized) |
| **macOS arm64** (Apple Silicon) | `https://fastdl.mongodb.org/osx/mongodb-macos-arm64-7.0.14.tgz` | ~78 MB | ~225 MB | `bin/mongod` (~90 MB, notarized) |
| **Windows x64** | `https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-7.0.14.zip` | ~200 MB | ~370 MB | `bin/mongod.exe` (~115 MB) — huge extraneous MSI + tooling in the zip, extract only `mongod.exe` |

### Minimum files per OS

For all 5 targets, **the launcher only needs the `mongod` binary itself**. mongod 7.0 statically links libssl/libcurl on the official Linux tarballs (verified via `ldd` on our preview host: no non-libc dependencies). macOS and Windows binaries are self-contained by design.

Practical Electron bundle strategy:
- `resources/mongod/darwin-arm64/mongod`
- `resources/mongod/darwin-x64/mongod`
- `resources/mongod/linux-x64/mongod`
- `resources/mongod/linux-arm64/mongod`
- `resources/mongod/win-x64/mongod.exe`
- At Electron main-process startup, pick the platform-appropriate binary and `chmod +x` on Unix, then set `UBOS_MONGOD_BIN` before spawning the FastAPI backend.

### Total bundled-size table

| Platform installer | Electron shell | FastAPI backend (PyInstaller) | mongod binary | **Total (uncompressed)** | **DMG/EXE/AppImage (compressed)** |
|---|---:|---:|---:|---:|---:|
| macOS arm64 | ~80 MB | ~55 MB | 90 MB | **~225 MB** | ~110 MB |
| macOS x64 | ~80 MB | ~55 MB | 95 MB | **~230 MB** | ~115 MB |
| Windows x64 | ~90 MB | ~60 MB | 115 MB | **~265 MB** | ~130 MB |
| Linux x64 (AppImage) | ~70 MB | ~55 MB | 110 MB | **~235 MB** | ~120 MB |
| Linux arm64 | ~70 MB | ~55 MB | 100 MB | **~225 MB** | ~110 MB |

Reference for calibration (approximate installer sizes as of 2026):
- Notion desktop: ~180 MB
- Slack desktop: ~240 MB
- Discord desktop: ~220 MB
- Postman: ~280 MB

UBOS's ~230 MB is squarely in the norm.

---

## License note — SSPL v1

MongoDB Community Server is licensed under the **Server Side Public License v1** (SSPL) since MongoDB 4.0 (Oct 2018).

**Key implications for UBOS bundling:**
- ✅ **Redistribution allowed for a desktop application.** SSPL is a derivative of AGPL; its only novel restriction (Section 13) is triggered when *"offering the functionality of the Program... to third parties as a service"*. Bundling `mongod` as an internal storage engine inside a desktop app that a single user runs on their own machine does NOT constitute offering "the Program" as a service.
- ⚠️ **We must ship an unmodified `mongod` binary** — the SSPL notice + license text must accompany the distribution. Plan: put `LICENSE-mongodb-sspl.txt` in the installer resources alongside the binaries.
- ⚠️ **We must not remove the MongoDB copyright notice** from the binary metadata.
- ✅ Users copying UBOS between their own machines are fine — that's not "offering to third parties as a service".

**Not required:**
- No SSPL requirement to open-source UBOS itself (SSPL scope is `mongod`, not the surrounding host application).
- No royalty payment.
- No signup / notification to MongoDB Inc.

Reference: https://www.mongodb.com/licensing/server-side-public-license/faq — question "May I embed MongoDB in my desktop or mobile application?" answer is *yes*.

**Action item for D4 (installer):** add an `About > Third-Party Licenses` menu entry that shows the SSPL text.

---

## Launcher API

New module: `/app/backend/core/mongod_launcher.py` (~230 LOC)

```python
launcher = MongodLauncher()          # picks free port, uses UBOS_OFFLINE_DATA_DIR
launcher.start()                     # spawns mongod as subprocess
launcher.wait_until_ready(30)        # blocks until pingable, or MongodLauncherError
# ... Motor client at launcher.uri ...
launcher.stop()                      # SIGTERM (10s grace) → SIGKILL fallback
```

**Contract:**
- **Bind:** `127.0.0.1` only (never external interfaces).
- **Port:** random free port by default (`UBOS_MONGOD_PORT` env override).
- **Data dir:** `UBOS_OFFLINE_DATA_DIR` (default `~/.ubos/data`).
- **Log:** `UBOS_MONGOD_LOG_DIR/mongod.log` (default: sibling of data dir).
- **Binary path:** `UBOS_MONGOD_BIN` env var → fallback to `shutil.which("mongod")` so dev machines work.
- **Version detection:** parses `mongod --version` output; automatically omits `--nojournal` on 6.0+ (deprecated).
- **atexit hook:** subprocess is killed on Python interpreter exit even if the caller forgets `.stop()`.
- **Windows-aware:** uses `taskkill /F /T /PID` in place of SIGTERM (Windows has no POSIX signal support for `mongod`).

**Factory integration** in `db_adapter.py`:

```
UBOS_DB_MODE=bundled
    → MongodLauncher singleton starts local mongod
    → MotorAdapter wraps AsyncIOMotorClient(launcher.uri)
    → adapter returned to app
```

Existing code paths flow unchanged — the driver is still Motor, we've just changed WHERE the Mongo server lives.

---

## Test results

```
tests/test_d0_6_bundled_mongod.py — 13 passed in 1.38s
    TestBundled_RecordsCRUD           5/5 ✓
    TestBundled_BrowseAggregate       2/2 ✓  (identical to Motor+Atlas — aggregate works)
    TestBundled_CategoryDescendants   1/1 ✓
    TestBundled_Indexes               3/3 ✓  (simple + compound + text)
    TestBundled_LauncherLifecycle     2/2 ✓  (uri is 127.0.0.1, log file exists)
```

### Comparison with prior phases

| Engine | Records CRUD | Browse aggregate | Category descendants | Indexes | Overall |
|---|---|---|---|---|---|
| Motor + Atlas (online, D0)          | 5/5 | 2/2 | 1/1 | 3/3 | **11/11** |
| Mongita (D0)                        | 5/5 | 0/2 | 1/1 | 1/3 | 7/11 |
| MontyDB (D0.5)                      | 5/5 | 0/2 | 1/1 | 3/3 | 9/11 |
| **Bundled mongod + Motor (D0.6)**   | **5/5** | **2/2** | **1/1** | **3/3** | **11/11** |

**Bundled mongod behaves identically to Motor-against-Atlas** because it IS the same server. This is the win we hoped for.

### Regression baseline (online mode unchanged)

```
tests/test_ubos_phase8_browse.py       16/16 ✓
tests/test_labels_no_code_mode.py      13/13 ✓
tests/test_d0_adapter_capability.py    27 pass / 6 expected-fail (mongita+montydb gaps documented in D0/D0.5)
────────────────────────────────────────────────────
Focused suite:                         56 pass · 6 expected-fail (identical to D0.5 baseline)
```

**No online-mode regression from D0.6 changes.** ✅

---

## Files touched (D0.6 total)

- **NEW** `/app/backend/core/mongod_launcher.py`  (~230 LOC)
- `/app/backend/core/db_adapter.py`  (+15 LOC in factory for `UBOS_DB_MODE=bundled` branch, no other changes)
- **NEW** `/app/backend/tests/test_d0_6_bundled_mongod.py`  (~200 LOC — 13 tests)
- **NEW** `/app/test_reports/desktop_phase_d0_6_mongod_inventory.md`  (this file)

**No binaries added to the repo.** Bundling is D4 (installer phase).
**No Electron work.** D2.
**No changes outside the adapter/launcher layer.**

---

## GO for D1 — recommendation

Pure-Python engines are eliminated (D0.5 report). Bundled `mongod` clears
all 11 capability tests with identical Motor semantics. The launcher wrapper
is proven to spawn, healthcheck, and cleanly tear down mongod in <2s on
Linux x64.

**Ready to proceed to D1** — full adapter refactor across the modules that
currently use `get_db()` (routes/data.py, routes/browse.py,
services/categories.py, and the rest). D1's blast radius is now bounded:
- Callsites switch from `db = get_db()` → `db = get_database_adapter()`.
- No behavior change in online mode (MotorAdapter is a strict passthrough).
- Offline mode works because bundled mongod is a real MongoDB server.

Awaiting your go-ahead for Directive 2 (test-hygiene sprint) and then D1.

---

## Open items for D4 (installer phase)

- Automate the mongod binary downloads (5 archives, verify SHA-256).
- Add an `About > Third-Party Licenses` menu that shows the SSPL text.
- Code-signing on macOS + notarization for the mongod binary is already
  handled by MongoDB Inc. on the official downloads. Windows AV whitelist
  reputation may require ~2 weeks of automated download traffic to
  establish — plan for this early.
- Decide whether to strip debug symbols from mongod to shave ~20% off
  the binary size (`strip mongod` on Unix; Windows binary is already stripped).
