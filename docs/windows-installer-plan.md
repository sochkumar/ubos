# UBOS — Windows desktop installer + 2-machine license

Status: **plan (approved decisions)** · Target: give a friend an offline Windows app locked to 2 machines.

## Decisions (locked)
- **Shell:** Electron.
- **Database:** bundle real MongoDB (`mongod.exe`) as a child process.
- **License:** offline, signed license file locked to 2 specific machine IDs (no server).
- **Data sharing between the 2 machines:** file-based **workspace export/import** (no live sync).
- **Build:** GitHub Actions `windows-latest` runner produces the installer (no Windows PC needed).

## Critical constraint
The final artifacts are Windows-specific: the PyInstaller backend `.exe`, `mongod.exe`, and the Electron/NSIS installer must be **built on Windows** (a Windows PC or a GitHub Actions `windows-latest` runner). All the *source* (Electron main process, license tooling, desktop config, build scripts) is cross-platform and can be written/tested on macOS; only the packaging step needs Windows.

## Architecture

```
UBOS-Setup-x.y.z.exe   (NSIS installer via electron-builder)
  └─ installs to  %LOCALAPPDATA%\Programs\UBOS\
       ├─ UBOS.exe            Electron shell (main + renderer)
       ├─ resources\
       │    ├─ backend\ubos-backend.exe     PyInstaller: uvicorn + serves the React build
       │    ├─ mongodb\mongod.exe           bundled MongoDB Community
       │    └─ frontend\                     static React build (served by backend)
       └─ license\ubos.lic    (dropped in by the user; signed, 2 machine IDs)

Runtime data (per-user, writable):
  %APPDATA%\UBOS\
       ├─ db\        mongod --dbpath   (the customer's data)
       ├─ uploads\   media storage
       └─ config     generated JWT secret, chosen port
```

**Startup sequence (Electron main process):**
1. Read/verify `license\ubos.lic` against the current machine ID → if invalid, show an activation screen and stop.
2. Ensure `%APPDATA%\UBOS\{db,uploads}` exist; on first run generate a JWT secret.
3. Spawn `mongod.exe --dbpath %APPDATA%\UBOS\db --port <loopback>` (bound to 127.0.0.1).
4. Spawn `ubos-backend.exe` (uvicorn) with env: `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `LOCAL_STORAGE_ROOT`, `SEED_USERS=true` (first run only), `CORS_ORIGINS=http://127.0.0.1:<port>`.
5. Wait for `/api/health` → load `http://127.0.0.1:<port>` in the Electron `BrowserWindow`.
6. On quit / crash: terminate both child processes (tree-kill).

## Licensing design (offline, signed, 2 machines)

**Keypair (you keep the private key secret, forever):**
- Ed25519 keypair. **Public key is embedded in the app**; the private key never ships.

**Machine ID (Windows):** `SHA256(MachineGuid + system volume serial)`, where `MachineGuid` = `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`. Stable across reboots. A small "Show my Machine ID" screen in the app (and a standalone `machine-id.exe`) prints it.

**Issuing flow (one-time, per friend):**
1. Friend installs the app on both PCs, opens "Machine ID", sends you the 2 IDs.
2. You run `tools/issue_license.py` (private key on your machine only):
   ```
   payload = { "licensee": "Friend Name", "machines": ["<id1>","<id2>"], "issued": "2026-..." , "product":"ubos" }
   ubos.lic = base64(payload) + "." + base64(ed25519_sign(payload))
   ```
3. Send `ubos.lic`; friend drops it in the app's `license\` folder (or an in-app "Load license" button copies it there).

**Verification (app, offline):** decode → verify Ed25519 signature with the embedded public key → check `current_machine_id ∈ payload.machines`. Enforced in the Electron main process **and** re-checked by the backend on boot (defence in depth). No network, exactly 2 named machines.

*Honest caveat:* this stops casual copying, not a determined reverse-engineer. That's the right level for a friend.

## Code changes needed (this repo)

1. **Desktop config profile** — backend reads env exactly as today; the Electron main process supplies desktop values. Add `SEED_USERS` first-run guard (already supported). No schema changes.
2. **Backend serves the frontend** — mount the React `build/` as static files and add an SPA fallback route, so there is a single local URL. (Small addition to `server.py`.)
3. **License check on boot** — a `backend/license.py` verifier + a startup gate; plus the Electron-side check.
4. **New `desktop/` folder** — Electron app (`main.js`, preload, `package.json`, electron-builder config), the PyInstaller spec, and `tools/issue_license.py` + `machine-id` utility.
5. **Bundle prep** — download MongoDB Community zip for Windows x64; vendor `mongod.exe` into `desktop/resources/mongodb/`.

## Data sharing between the 2 machines (workspace export/import)

The two installs are independent copies. To move an updated dataset from one to
the other, ship a **full workspace bundle** — distinct from the existing
per-collection CSV/XLSX import/export (which stays for spreadsheet workflows).

- **Bundle format:** a single `.ubos` file = a ZIP containing one JSON per
  collection (`entity_types`, `field_definitions`, `field_library`,
  `custom_field_types`, `categories`, `tags`, `records`, `relationships`,
  `views`, `label_presets`) + a `media/` folder with the actual files +
  `manifest.json` (org, app version, exported_at, counts, checksum).
- **Export:** `GET /api/workspace/export` streams the ZIP. An in-app
  "Export workspace" button saves it (e.g. to a USB drive or cloud folder).
- **Import:** `POST /api/workspace/import` with a mode:
  - **Replace** — wipe this org's data, load the bundle (simplest; treat one
    machine as source of truth at a time).
  - **Merge (newer wins)** — upsert by `_id`, keeping the row with the later
    `updated_at`. Gives real file-based "sync" without a server. IDs are UUIDs
    so they're stable across machines.
- **Media:** copied into the local storage root on import; dedup by SHA-256
  (already how media works), so re-imports don't duplicate files.
- Scope for the friend MVP: **Export + Replace-import** first; add Merge next.

## Build pipeline — GitHub Actions (`windows-latest`)

A single workflow (`.github/workflows/build-windows.yml`), triggered on a version
tag (e.g. `v0.1.0`), runs on `windows-latest`:

1. Checkout; set up Node + Python (3.11).
2. `cd frontend && yarn install && yarn build`.
3. `pip install -r backend/requirements.txt pyinstaller` → `pyinstaller backend/ubos-backend.spec` (onefile; hidden imports: motor, pymongo, reportlab, pillow, passlib/bcrypt, email-validator).
4. Download MongoDB Community (Windows x64) and unzip `mongod.exe` (+ required DLLs) into `desktop/resources/mongodb/`.
5. Copy `frontend/build` and `ubos-backend.exe` into `desktop/resources/…`.
6. `cd desktop && npm ci && npm run dist` (electron-builder, target `nsis`) → `UBOS-Setup-x.y.z.exe`.
7. Upload the installer as a workflow artifact **and** attach it to a GitHub Release for the tag.

Result: push a tag → download a ready installer from the Release page. No local
Windows machine required. (Code-signing can be added to this workflow later with
an Authenticode cert stored as a repo secret.)

## Phased implementation

- **P0 — License tooling (cross-platform, testable on macOS now):** Ed25519 keypair, `issue_license.py`, machine-ID function (Windows path + macOS dev fallback), verifier + unit tests.
- **P1 — Workspace export/import (backend, testable now):** `GET /api/workspace/export` (ZIP bundle) + `POST /api/workspace/import` (Replace mode first, then Merge). Round-trip test on the local DB. Also useful for the current cloud app as a full backup/restore.
- **P2 — Backend desktop-mode:** serve the frontend statically, boot-time license gate, first-run seed. Test the whole stack locally (uvicorn serving UI + API from one port).
- **P3 — Electron shell:** main process that spawns mongod + backend, health-wait, loads the window, tree-kills on exit; Machine-ID, "Load license", and Export/Import screens. (Dev-run on macOS against local mongod.)
- **P4 — CI packaging (`.github/workflows/build-windows.yml`):** PyInstaller spec, vendor mongod.exe, electron-builder NSIS config; tag → GitHub Release with the installer. Smoke-test the artifact on a clean Windows VM.
- **P5 — Polish:** app icon/branding, first-run splash, unsigned-installer note (code-signing later), a 1-page setup guide for your friend.

## Deliverables to the friend
- `UBOS-Setup-x.y.z.exe` (the installer).
- A 1-page setup guide: install → open "Machine ID" on both PCs → send you the 2 IDs → drop in `ubos.lic` → done.
- Their data lives in `%APPDATA%\UBOS\db`; include a "Backup my data" note (zip that folder).

## Gotchas & product-track notes
- **MongoDB SSPL:** fine to bundle for a friend; **before selling UBOS, move off MongoDB** (Postgres, or FerretDB = Mongo-compatible over Postgres/SQLite, Apache-2). Decide before scaling.
- **SmartScreen:** unsigned installer warns on first run — fine for a friend; buy an Authenticode cert (~$100–200/yr) before public release.
- **Installer size:** ~150–250 MB (mongod dominates).
- **Backups:** desktop data is only on their PC — the "2 machines" run independent copies (no sync). If they need the same data on both, that's a separate sync feature (out of scope here).
- **Auto-update:** skip for the friend; electron-builder + a static release feed can add it later.
