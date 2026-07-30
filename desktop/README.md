# UBOS desktop shell (Electron)

Packages UBOS as an offline Windows app: an Electron window that launches a
bundled MongoDB and the PyInstaller backend (which serves the React UI), gated
by an offline 2-machine license. See `../docs/windows-installer-plan.md`.

## Layout

```
desktop/
  main.js              orchestration (spawn mongod + backend, license gate, window)
  license.html         native activation screen (shows Machine ID, loads ubos.lic)
  license-preload.js   IPC bridge for the activation screen
  package.json         electron + electron-builder (nsis) config
  licensing/           vendor tools: keygen.py, issue_license.py
  resources/           POPULATED BY CI before packaging (git-ignored):
    backend/ubos-backend.exe
    mongodb/mongod.exe
    frontend/           the React build (built with REACT_APP_BACKEND_URL="")
```

## One-time vendor setup

```bash
python licensing/keygen.py --out ./secret     # keep secret/ubos_private_key.pem safe forever
```
Put the printed public key into the app: set `UBOS_LICENSE_PUBLIC_KEY` in the CI
build, or replace `LICENSE_PUBLIC_KEY` in `main.js` and `LICENSE_PUBLIC_KEY_B64`
in `backend/licensing.py`.

## Issue a license for a friend

They open the app → the activation screen shows two Machine IDs (one per PC).
Then:
```bash
python licensing/issue_license.py \
  --private-key ./secret/ubos_private_key.pem \
  --licensee "Friend Name" \
  --machine UBOS-AAAA-... --machine UBOS-BBBB-... \
  --out ./ubos.lic
```
Send `ubos.lic`; they load it from the activation screen.

## Dev run (macOS/Linux, against the repo backend + a local mongod)

Requires a `mongod` on PATH and the backend venv set up.
```bash
cd desktop && npm install
UBOS_LICENSE_PUBLIC_KEY="<test pub key>" npm start
```
In dev the shell runs the backend via `../backend/venv/bin/python -m uvicorn`
and `mongod` from PATH (override with `$UBOS_MONGOD` / `$UBOS_PY`).

## Production build (GitHub Actions `windows-latest`)

CI (`.github/workflows/build-windows.yml`, added in P4) will:
1. `frontend`: `REACT_APP_BACKEND_URL="" yarn build` → copy to `resources/frontend`.
2. `backend`: `pyinstaller ubos-backend.spec` → copy exe to `resources/backend`.
3. Download MongoDB Community (win x64) → copy `mongod.exe` (+ dlls) to `resources/mongodb`.
4. `cd desktop && npm ci && npm run dist` → `dist/UBOS-Setup-<version>.exe`.
5. Attach the installer to a GitHub Release.

> The frontend MUST be built with `REACT_APP_BACKEND_URL=""` so the SPA calls the
> backend same-origin (the backend serves the static build via `FRONTEND_DIR`).
