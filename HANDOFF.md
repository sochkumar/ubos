# UBOS — Developer Handoff

This document is the single source of truth for a new engineer taking over the UBOS codebase. It covers what the product is, how the code is laid out, what secrets it needs, and everything that is currently unfinished, wired up "for later", or known to be broken. Read this before you touch anything.

Last updated: 2026-02-29 (Desktop workstream cancelled and reverted; unused `emergentintegrations` + `litellm` pin removed to fix `pip install`).

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Tech Stack & Architecture](#2-tech-stack--architecture)
3. [Environment & Secrets](#3-environment--secrets)
4. [External Services](#4-external-services)
5. [Deployment](#5-deployment)
6. [Known Issues](#6-known-issues)
7. [Conventions](#7-conventions)
8. [Access Details](#8-access-details)

---

## 1. Project Overview

UBOS ("Universal Business Operating System") is a **multi-tenant SaaS platform** for small businesses that lets non-technical owners model their operations without code changes. Where a normal SaaS ships with fixed tables ("orders", "invoices"), UBOS ships with a **metadata engine**: users define their own Collections at runtime, add whatever Fields they want, and every downstream feature (search, filters, imports, exports, sharing, labels, dashboards) drives itself off that metadata.

### Target customers

Small businesses that do not fit any single vertical tool cleanly. The product ships an **Industry Starter Packs** system (`/app/frontend/src/lib/industryPresets.js`) with pre-built templates for:

- Furniture stores
- Bakeries
- Jewellery retailers
- Generic retail / inventory
- CRM-lite
- Asset tracking

Each starter pack seeds a demo Collection set and rebrands the UI vocabulary (a bakery sees "Products & Recipes", a jeweller sees "Pieces & Certificates"; the same underlying `entity_types` collection powers both). See `/app/frontend/src/lib/terminology.js` for the runtime translator.

### Main user flow

1. **Signup** — email/password (`POST /api/auth/register`) or Google OAuth.
2. **Org creation** — first login provisions a personal org; user can add more via `POST /api/orgs`.
3. **Onboarding wizard** — `/app/frontend/src/pages/OnboardingPage.jsx` walks the user through picking an industry preset. Under the hood this calls `POST /api/templates/<key>/apply` with `conflict_policy=skip` (see `/app/backend/routes/templates.py` + `/app/backend/services/template_applier.py`).
4. **Author Collections and Items** — pages `EntityTypesPage.jsx`, `FieldsPage.jsx`, `RecordsPage.jsx`.
5. **Business operations** — labels/QR (`PrintLabelsDialog.jsx` → `/api/records/labels`), share links (`ShareAndPrintPanel.jsx` → `/api/records/{id}/shares`), CSV import (`ImportWizard.jsx` → `/api/import`), exports (`ExportMenu.jsx` → `/api/export`).
6. **Multi-tab workspace** — `TabBar.jsx` + `lib/tabs.jsx` provide a persistent tab strip like a browser. All in-app navigation goes through the tab manager, not through `window.location`.

### Completion status

- **Phases 0–8 shipped and deployed** to the preview environment. That covers metadata engine, records CRUD + validation, templates, media/images, share links + public views, RBAC + orgs + invitations, label rendering + label presets, security hardening, terminology + onboarding + coach marks, and universal browse.
- **Desktop workstream (Phases D0–D5) was cancelled** on 2026-02-29. All Desktop-era artifacts (`db_adapter.py`, `mongod_launcher.py`, mongita/montydb POC tests, three test-report markdown files, and three `requirements.txt` entries) have been reverted from the source tree. **This document supersedes any Desktop-phase documentation that may still be floating around.**
- **MVP is functionally complete.** Remaining work is production polish (see [Known Issues](#6-known-issues)) and P3 backlog items (bulk CSV invites, ZIP bundle upload, whole-dashboard sharing, approval-based join requests — none scoped or promised).

---

## 2. Tech Stack & Architecture

### Backend

- **Framework:** FastAPI (Python 3.11), ASGI via uvicorn.
- **Database driver:** Motor (async MongoDB driver) with Pydantic v2 models.
- **All routes are prefixed with `/api/*`.**
- **Location:** `/app/backend/`.

Directory layout:

| Path | Contents |
| --- | --- |
| `/app/backend/server.py` | FastAPI app factory, lifespan, middleware (CORS, security headers, IP resolution), router registration, exception handlers. Also runs the initial seed on empty DB. |
| `/app/backend/db.py` | Motor client + `get_db()` accessor. Reads `MONGO_URL` / `DB_NAME`. |
| `/app/backend/security.py` | JWT issuance/verification (`create_access_token`, `create_refresh_token`, `verify_token`) and bcrypt password hashing. |
| `/app/backend/auth_deps.py` | `get_current_user`, `AuthContext`, `require_permission("<perm>")` FastAPI dependencies. |
| `/app/backend/models.py` | Pydantic v2 shared models (`ORef`, `BaseDocument`, `PyObjectId`, etc.). |
| `/app/backend/validator.py` | `FieldValidator` — validates and coerces record payloads against `field_definitions`. Handles all 13 field types (`text`, `longtext`, `richtext`, `number`, `currency`, `date`, `datetime`, `boolean`, `dropdown`, `multi_select`, `email`, `phone`, `url`, plus stubs for `image`/`file`/`relation`). |
| `/app/backend/audit.py` | Audit-log writer (`audit(bg, action=..., actor_id=..., org_id=..., ...)`). Called from routes. |
| `/app/backend/core/request_ip.py` | Client-IP resolution (CF-Connecting-IP → leftmost XFF → `request.client.host`, gated by `TRUST_PROXY_HOPS` + `TRUST_LEFTMOST_XFF`). |
| `/app/backend/core/storage/` | Pluggable storage adapter (`base.py`, `local.py`, `s3.py`, `factory.py`). Selected by `STORAGE_BACKEND` env var. |
| `/app/backend/core/email/` | Pluggable email adapter (`dev.py`, `resend.py`, `sendgrid.py`, `ses.py`, `factory.py`, `templates.py`). Selected by presence of provider API keys. |
| `/app/backend/routes/` | One file per resource. Auth `auth.py`, orgs `orgs.py`, entity types + fields + records `data.py`, categories `categories.py`, tags `tags.py`, media `media.py`, share links `shares.py`, view shares `view_shares.py`, templates `templates.py`, label presets `label_presets.py`, labels `labels.py`, browse `browse.py`, search `search.py`, dashboards `dashboard.py` + `dashboard_layout.py`, import/export `export_import.py`, invitations `invitations.py`, audit `audit.py`, dev tooling `dev.py`, relationships `relationships.py` + `relationship_instances.py`, record history `record_history.py`, Google OAuth `oauth_google.py`, views `views.py`. |
| `/app/backend/services/` | Business logic that doesn't fit in a route: `template_applier.py`, `media.py` (dedup + thumbs), `labels.py` (ReportLab PDF layout), `qr_barcode.py`, `categories.py` (tree ops), `query_builder.py`, `quota.py` (storage accounting), `history.py`, `record_signals.py`, `relationships.py`. |
| `/app/backend/modules/templates/library/` | JSON template packs (starter presets). Loaded by `services/template_applier.py`. |
| `/app/backend/scripts/seed.py` | Idempotent seed for Acme Furniture demo org + owner/editor/viewer users. Also invoked from `server.py` lifespan when `users` collection is empty. |
| `/app/backend/tests/` | Pytest suite. See `pytest.ini` — runs `-n 2 --dist loadfile`. Legacy tests (`test_ubos_phase0.py` etc.) are being rewritten to JWT; see [Known Issues](#6-known-issues). |
| `/app/backend/Dockerfile` | Production image (uvicorn behind a slim Python base). |

### Frontend

- **Framework:** React 18, JavaScript (JSX). Bundler: Create-React-App (`react-scripts`).
- **Styling:** Tailwind CSS + shadcn/ui components (`/app/frontend/src/components/ui/`).
- **Notable libraries:** `@dnd-kit/*` (drag reorder in `FieldsPage`, `CategoryTreeNode`, `DashboardPage`), `shepherd.js` (guided tours in `lib/tourManager.js`), `sonner` (toasts), `react-router-dom`.
- **Location:** `/app/frontend/`.

Directory layout:

| Path | Contents |
| --- | --- |
| `/app/frontend/src/index.js` | Entry. Renders `<App/>` under React StrictMode, registers the PWA service worker via `lib/sw-register.js`. |
| `/app/frontend/src/App.js` | Router + provider tree (auth context, terminology, tabs, toaster). |
| `/app/frontend/src/lib/api.js` | Axios client wired to `REACT_APP_BACKEND_URL`; injects the JWT and handles 401 refresh. |
| `/app/frontend/src/lib/auth.jsx` | `AuthProvider`, `useAuth()`. Owns the access/refresh tokens (localStorage + memory), plus login/logout/refresh helpers. |
| `/app/frontend/src/lib/terminology.js` | The `t()` translator. Reads `org.settings.terminology` and rewrites UI strings — **never hardcode "Entity Type" / "Record" / etc.**, always use `t()`. |
| `/app/frontend/src/lib/industryPresets.js` | Static definitions of starter-pack vocabularies (bakery, furniture, jewellery, etc.). |
| `/app/frontend/src/lib/tabs.jsx` | Multi-tab workspace: `TabsProvider`, `useTabs()`. Persists tab state to `sessionStorage`. |
| `/app/frontend/src/lib/tourManager.js` | Shepherd.js wrapper. Tour definitions live near the pages they anchor. |
| `/app/frontend/src/lib/errors.js` | Central `formatError()` — normalizes Pydantic error bodies into user-facing strings. |
| `/app/frontend/src/lib/filterOps.js` | Client-side filter builder used by BrowsePage / RecordsPage. |
| `/app/frontend/src/lib/sw-register.js` | PWA service-worker registration (gated by `REACT_APP_ENABLE_SW`). |
| `/app/frontend/src/layouts/AppLayout.jsx` | Authenticated shell (sidebar + tab bar + content). |
| `/app/frontend/src/layouts/AuthLayout.jsx` | Signed-out shell. |
| `/app/frontend/src/pages/` | One file per screen. Notable: `EntityTypesPage.jsx`, `FieldsPage.jsx`, `RecordsPage.jsx`, `RecordDetailPage.jsx`, `BrowsePage.jsx`, `SearchPage.jsx`, `TemplatesPage.jsx`, `OnboardingPage.jsx`, `MediaPage.jsx`, `CategoriesPage.jsx`, `TagsPage.jsx`, `RelationshipsPage.jsx`, `PublicRecordPage.jsx`, `PublicViewPage.jsx`, `HelpPage.jsx`, plus `pages/settings/*` and `pages/auth/*`. |
| `/app/frontend/src/components/` | Reusable primitives. Notable: `DynamicField.jsx` (dispatches to the right renderer per field type), `ImageFieldRenderer.jsx`, `FileFieldRenderer.jsx`, `PrintLabelsDialog.jsx`, `ImportWizard.jsx`, `ExportMenu.jsx`, `TabBar.jsx`, `RequireAuth.jsx`, `ErrorBoundary.jsx`, `CommandPalette.jsx`, `GlobalHotkeys.jsx`, `FilterBar.jsx`, `CategoryPicker.jsx`. |
| `/app/frontend/src/components/ui/` | shadcn/ui primitives (button, dialog, dropdown, calendar, sonner, etc.). Prefer these over hand-rolled components. |
| `/app/frontend/public/sw.js` | Service worker. Caches shell assets. **Bump the version constant when you deploy changes to cached files** or users will see stale UI. |
| `/app/frontend/public/manifest.webmanifest` | PWA install manifest. |
| `/app/frontend/Dockerfile` | Production image (Node build → static-served). |

### Database

Single MongoDB instance. All customer-scoped data is filtered by `org_id`. **Every collection has soft-delete via `deleted_at`.** Timestamps stored as ISO-8601 strings.

Key collections:

| Collection | Purpose |
| --- | --- |
| `organizations` | Tenant record. Holds `slug`, `name`, `settings.terminology`, `settings.storage_quota_bytes`, `storage_used_bytes`. |
| `users` | User accounts with `password_hash`, `default_org_id`, `active_org_id`, `oauth.google`. |
| `memberships` | Join table: `(user_id, org_id) → role_id`. `role_id` is a string key resolved against a role table. |
| `entity_types` | Custom Collections. `{org_id, key, name_singular, name_plural, icon, color, description, record_counter}`. |
| `field_definitions` | Custom Fields. `{org_id, entity_type_id, key, label, type, config, required, unique, order, group, help_text}`. |
| `records` | The single generic table backing all custom Collections. `{org_id, entity_type_id, title, fields, record_number, search_text, version, category_ids, tag_ids, primary_image_id, ...}`. |
| `media` | Uploaded files. Dedup by SHA-256 hash. Thumbnails materialized async. |
| `share_links` | Per-record share tokens (`record_shares` in code) and per-view share tokens (`view_shares`). Passwordable with unlock rate-limiting. |
| `label_presets` | Custom label sheet layouts (per-org). Built-in presets live in code (`services/labels.py`). |
| `dashboard_layouts` | Saved dashboard configs. |
| `import_jobs`, `export_jobs` | Long-running CSV/XLSX import/export state. |
| `audit_logs` | Append-only event log. |
| `relationships`, `relationship_instances` | Typed links between records (many-to-many with optional metadata). |
| `record_history` | Per-record change log for the RecordDetail history tab. |
| `invitations` | Pending org invites (email + role). |
| `login_attempts` | Persistent brute-force lockout state (5 fails/15 min per email). |
| `views` | Saved filter+sort+column configs used by BrowsePage / RecordsPage. |
| `categories`, `tags` | Per-org taxonomy. Categories are a tree (path array); tags are flat. |

### How the pieces connect

```
Browser (React SPA)
  ├── static assets served from /app/frontend/build (or React dev server on :3000)
  └── XHR to REACT_APP_BACKEND_URL/api/*
         │
         ▼
    k8s ingress
         │
         ▼
    uvicorn on 0.0.0.0:8001 (server.py)
         │
         ├── middleware: CORS, security headers, IP resolution
         ├── auth: JWT bearer via auth_deps.get_current_user
         ├── routes: /api/auth, /api/orgs, /api/entity-types, /api/records, ...
         │
         ▼
    Motor client → MongoDB
```

The **PWA service worker** (`sw.js`) caches the shell (HTML/JS/CSS/icons) for offline reload only — it does NOT cache API responses. There is no offline-first data layer in production; the Desktop workstream that would have added one was cancelled.

---

## 3. Environment & Secrets

**Do not commit real values.** Local defaults live in `/app/backend/env.example`. Production values are set through the deploy platform.

### Backend (`/app/backend/.env`)

| Name | Purpose | Required? | Notes |
| --- | --- | --- | --- |
| `MONGO_URL` | MongoDB connection string | **yes** | Preview uses in-pod `mongodb://localhost:27017`; prod intent is MongoDB Atlas SRV URI. |
| `DB_NAME` | Mongo database name | **yes** | Preview uses `test_database`; do NOT hardcode elsewhere. |
| `JWT_SECRET` | HMAC key for access AND refresh tokens (differentiated by `type` claim, not by a separate secret) | **yes** | 32-byte random string. Rotate on suspected compromise. |
| `JWT_ACCESS_TTL_MINUTES` | Access-token lifetime | no (default 15) | |
| `JWT_REFRESH_TTL_DAYS` | Refresh-token lifetime | no (default 30) | |
| `SECRET_KEY` | Legacy fallback used by a subset of endpoints. Set to the same value as `JWT_SECRET` to be safe. | recommended | Grep `SECRET_KEY` in `server.py` to see where. |
| `CORS_ORIGINS` | Comma-separated allowlist for CORS | recommended | Prod must be explicit (no `*`). |
| `PUBLIC_APP_URL`, `APP_BASE_URL` | Base URL used when composing invitation/share URLs in outbound emails | recommended in prod | If unset, emails contain relative paths. |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | needed for Google Sign-In | Client ID is also read by the frontend (see below). |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | needed for Google Sign-In | Backend-only. |
| `STORAGE_BACKEND` | `local` (default) or `s3` | no | `local` writes to `LOCAL_STORAGE_ROOT`. |
| `LOCAL_STORAGE_ROOT` | Filesystem root for local storage backend | no (default `/app/backend/uploads`) | |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`, `AWS_REGION` | S3 storage backend credentials | only if `STORAGE_BACKEND=s3` | S3 adapter code exists in `core/storage/s3.py` but is **not production-tested** — see [Known Issues](#6-known-issues). |
| `AWS_SES_REGION` | Region override for AWS SES email adapter | only if `ses` provider | |
| `EMAIL_FROM`, `EMAIL_FROM_NAME` | Default From address | recommended in prod | Falls back to a placeholder in dev. |
| `RESEND_API_KEY` | Resend provider key | one email provider required in prod | If present, Resend adapter is chosen. |
| `SENDGRID_API_KEY` | SendGrid provider key | one email provider required in prod | If present (and no Resend), SendGrid adapter is chosen. |
| `DEV_EMAIL_LOG` | File path for the dev-only console email logger | no (default `/app/backend/dev_emails.log`) | Used when no provider key is set — messages are appended to this file. |
| `MAX_UPLOAD_SIZE_BYTES` | Per-file upload cap | no (default 25 MB) | |
| `DEFAULT_ORG_STORAGE_QUOTA_BYTES` | Storage quota for newly-created orgs | no (default 5 GB) | Editable per-org via `PATCH /api/orgs/{id}/storage-quota`. |
| `IMPORT_MAX_FILE_MB`, `IMPORT_MAX_ROWS`, `EXPORT_MAX_ROWS` | Import/export size guards | no | |
| `IMPORT_TMP_ROOT` | Where import jobs stash uploaded CSVs during processing | no (default `/tmp/ubos_imports`) | |
| `PUBLIC_READ_RATE_LIMIT` | Per-IP rate limit for public `/api/public/records/...` reads | no (default `60/min`) | Tests bump this to `200/min` — see `env` in this repo. |
| `PUBLIC_CODE_RATE_LIMIT` | Per-IP rate limit for public QR/barcode endpoints | no (default `60/min`) | |
| `INVITE_RATE_LIMIT_PER_HOUR` | Per-user invitation-send cap | no (default `50`) | |
| `TRUST_PROXY_HOPS` | Number of proxy hops to trust when parsing X-Forwarded-For | no (default 1) | Set to match your ingress. |
| `TRUST_LEFTMOST_XFF` | If `true`, take the leftmost XFF entry | no | See `core/request_ip.py` for the exact algorithm. |
| `SEED_USERS` | `true`/`false` — whether the FastAPI lifespan should seed on empty DB | no | Set to `false` in prod after first run to avoid accidental re-seeds. |

### Frontend (`/app/frontend/.env`)

| Name | Purpose | Required? |
| --- | --- | --- |
| `REACT_APP_BACKEND_URL` | Base URL the SPA calls (everything is appended with `/api/...`) | **yes**, build-time |
| `REACT_APP_ENABLE_SW` | `true` to register the PWA service worker | no (defaults to disabled in dev) |
| `NODE_ENV` | Standard React env; set by `react-scripts` | auto |

**Additional frontend-visible Google config:** the Google Sign-In client ID must be exposed to the SPA. If you enable Google auth in prod, add `REACT_APP_GOOGLE_CLIENT_ID` and wire it into the Google button. It is currently not set in the preview env.

---

## 4. External Services

| Service | Purpose | Status | Notes |
| --- | --- | --- | --- |
| **MongoDB** | Primary datastore | preview = in-pod, prod = **not yet migrated** to Atlas | The code has no Atlas-specific hooks — swapping the URI is enough. Set up a replica set (Atlas M10+) for prod so change streams work when we add them. |
| **Google OAuth** | Optional sign-in method | wired but disabled in preview | Credentials required from customer. Route: `/api/auth/google/callback` in `routes/oauth_google.py`. |
| **Email provider** | Password reset, invitations, share-link notifications | **dev-console fallback active in preview** | Set `RESEND_API_KEY` or `SENDGRID_API_KEY` (or AWS SES creds + `AWS_SES_REGION`) to enable a real provider. Adapter chosen at boot in `core/email/factory.py`. |
| **Object storage** | Media upload + thumbnails | **local disk** in preview | S3 adapter code exists at `core/storage/s3.py`. **Treat S3 as MOCKED for prod purposes** — it compiles and unit-passes but has never been exercised against a real bucket end-to-end. Media dedup relies on SHA-256; the local and S3 adapters must agree on key layout — verify before switching. |
| **Deployment platform** | Hosting | Emergent (Kubernetes-based) | Recent deploy attempt failed on a platform-side `wakeup_environment` timeout — not a code defect, retry-side. |

---

## 5. Deployment

### Current preview

- **URL:** `https://org-platform-13.preview.emergentagent.com` (from `/app/frontend/.env`).
- **Platform:** Emergent auto-deploys from the workspace on save.
- **Backend serves on:** container internal `0.0.0.0:8001`, exposed via ingress at `/api/*`.
- **Frontend serves on:** container internal `:3000` (dev) or as static build (prod).
- **MongoDB:** in-pod, `mongodb://localhost:27017`.

### Production

- **Target URL:** `https://ubos.aariko.in` (customer's custom domain — DNS TBD).
- **Current status:** deploy is blocked on a platform-side `wakeup_environment` timeout. Not a code issue; the user needs to retry from the platform UI.
- **Migration checklist before flipping DNS:**
  1. Point `MONGO_URL` at a real Atlas cluster.
  2. Populate `JWT_SECRET` (32-byte random) and `SECRET_KEY` (mirror or independent).
  3. Set `CORS_ORIGINS` to `https://ubos.aariko.in`.
  4. Set `PUBLIC_APP_URL` and `APP_BASE_URL` to the same origin.
  5. Provide an email provider key (`RESEND_API_KEY` recommended).
  6. Set `SEED_USERS=false` (so a bug can't wipe/re-seed the prod tenant).
  7. Bump the service-worker cache version in `/app/frontend/public/sw.js` so returning users don't get a stale shell.
  8. Smoke-test: `/api/health` and `/api/openapi.json` should both return 200 unauthenticated.

### Build artifacts

- Backend Dockerfile: `/app/backend/Dockerfile`.
- Frontend Dockerfile: `/app/frontend/Dockerfile`.
- Frontend build command: `yarn build` (never `npm` — the repo is committed to yarn).

### Running locally

```bash
# Backend (in one terminal)
cd /app/backend
export MONGO_URL=mongodb://localhost:27017
export DB_NAME=ubos_local
export JWT_SECRET=$(python -c 'import secrets;print(secrets.token_urlsafe(32))')
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# Frontend (in another terminal)
cd /app/frontend
yarn install
yarn start
```

MongoDB must be running locally (Docker: `docker run -d -p 27017:27017 mongo:7`).

### Seeding

`python -m scripts.seed` from `/app/backend/`. Flags:

- `--reset` — purge non-canonical data, then seed.
- `--minimal` — only create the four canonical users + the Acme Furniture org (no demo Collections).

`server.py`'s lifespan hook auto-runs the seed when the `users` collection is empty on startup. Disable this in prod by setting `SEED_USERS=false`.

### Running tests

```bash
cd /app/backend
python -m pytest tests/ -q -n 0     # SERIAL — recommended, see Known Issues #6
```

Serial run takes ~4-5 minutes. Parallel `-n 2 --dist loadfile` (the `pytest.ini` default) is faster but occasionally hangs in this pod's environment — see [Known Issues](#6-known-issues) item 7.

Frontend has no automated test suite. Manual smoke pass through the onboarding wizard + the 5 canonical flows in `/app/memory/test_credentials.md` before any prod deploy.

---

## 6. Known Issues

Ordered by impact. Prod-blockers first.

1. **Production deploy blocked on platform `wakeup_environment` timeout.** Not a code issue; retry from the Emergent deploy UI. If it persists, escalate to Emergent support.
2. **S3 storage adapter is unverified.** `core/storage/s3.py` compiles and passes unit tests against a mock, but has never been exercised against a real S3 bucket end-to-end. Before switching `STORAGE_BACKEND=s3` in prod, run a full media round-trip: upload → thumbnail materialization → serve → delete → verify quota accounting.
3. **Public share endpoint may leak field metadata.** `exposed_defs.config` on the public share payload currently returns the full field-definition `config` dict — which can include `help_text`, admin-only option lists, and validation constants. Whitelist the projection to `label`, `type`, and only the public-safe subset of `config` (dropdown options are fine; anything else is suspect). Trace: `routes/shares.py` → public read path → `_build_public_payload`.
4. **Facet counts on `/api/records/browse` do not exclude their own dimension.** When you filter by `entity_type_ids=X`, the entity-type facet still shows counts as if no filter were applied. UX polish; not a data-correctness bug. Fix in `routes/browse.py::_facet_group`.
5. **Category descendant lookup is N+1.** `services/categories.py::descendants_of()` does one query per parent when it should use a single `$in` on the `path` array. Fine at current data sizes; will hurt when an org has >1000 categories.
6. **`/icons/favicon.png` returns 404.** During de-branding the frontend switched to `favicon.svg`; the `.png` fallback was not re-emitted. Cheap fix in `/app/frontend/public/`.
7. **Pytest sometimes hangs under `pytest-xdist` in this pod.** Root cause is a monkey-patched retry adapter in `tests/conftest.py` colliding with `Retry-After` headers on 429 responses (the auth brute-force limiter emits `Retry-After: 899`). The current mitigation is `respect_retry_after_header=False` in the adapter. If you touch `conftest.py`, re-verify. **Recommended validation mode: `pytest -n 0` (serial).**
8. **Legacy pytest files carry pre-Phase-5 auth patterns.** `test_ubos_phase0.py`, `test_ubos_phase3a.py`, `test_ubos_phase5a_hotfix.py` were partially rewritten to JWT during the aborted "hygiene sprint" and still have a handful of failing / flaky cases (approx. 6 tests). Harmless — none block prod, none exercise a broken code path. Suggested fix: either finish the JWT rewrite or delete the obsolete cases outright. See git log around 2026-02-29 for context.
9. **Rate-limit tests are flaky under parallel worker load.** They share the server's in-memory `_RL` bucket. `POST /api/dev/reset-rate-limits` exists as a targeted reset (owner-scoped RBAC). Tests that need a clean bucket must opt in via the `reset_rate_limits` fixture in `tests/conftest.py`; do not add it as autouse or you break cross-worker isolation.
10. **`login_attempts` collection is never trimmed.** The brute-force lockout writes rows and only expires them lazily on read. Not a correctness bug (5-fail lockout still fires correctly) but the collection grows monotonically. Add a TTL index on `expires_at`.

**Resolved during handoff (2026-02-29):**
- ~~`pip install -r requirements.txt` fails on `emergentintegrations==0.2.0` vs `litellm==1.80.0`.~~ **Fixed.** `emergentintegrations` was zero-referenced in the codebase (verified by grep) and was pulled in as boilerplate. Removed from `requirements.txt`. `litellm` remains as a top-level pin but is also zero-referenced — kept because removal is out of scope for the handoff; safe to delete when convenient.

---

## 7. Conventions

Follow these. The customer has flagged several of them as non-negotiable.

### UI terminology policy (hard rule)

**Never expose technical jargon to the user.** The words "Entity Type", "Record", "Dynamic Field", "Metadata", "Schema" must not appear anywhere the user can see them. Always route through the runtime translator:

```jsx
import { useTerminology } from "@/lib/terminology";

const { t } = useTerminology();
<h1>{t("entity_type.plural")}</h1>   // renders "Products" or "Recipes" or "Pieces" per org
```

The mapping lives in `org.settings.terminology` (per-org), seeded by the industry starter pack picked at onboarding. If you add a new UI string, add its translation key to `/app/frontend/src/lib/terminology.js` and to every starter pack in `/app/frontend/src/lib/industryPresets.js`.

### Multi-tab workspace

The app has a browser-like tab strip (`TabBar.jsx`). **All in-app navigation must go through the tab manager** — do not call `window.location = ...` or use `<a href>` for internal routes. Use:

```jsx
import { useTabs } from "@/lib/tabs";
const { openTab } = useTabs();
openTab({ id: "records:products", title: "Products", route: "/records/products" });
```

Tab state persists to `sessionStorage`.

### Client-IP resolution

Strict 3-tier hierarchy (documented and enforced in `/app/backend/core/request_ip.py::get_client_ip`):

1. `CF-Connecting-IP` (if present).
2. Leftmost entry of `X-Forwarded-For`, gated by `TRUST_LEFTMOST_XFF` + `TRUST_PROXY_HOPS`.
3. `request.client.host` fallback.

Match the k8s ingress config to this hierarchy or IP-based rate limits become useless.

### Auth

- **Access tokens** — short-lived JWTs (default 15 min), sent as `Authorization: Bearer <token>`.
- **Refresh tokens** — long-lived (default 30 days), rotated on every refresh, tracked in memory for revocation.
- **All `/api/*` routes require auth** except `/api/auth/*`, `/api/health`, `/api/openapi.json`, and the `public/records/*` / `public/views/*` share endpoints.
- **RBAC** is enforced through the `require_permission("<perm>")` FastAPI dependency (`/app/backend/auth_deps.py`). Never gate off `role_id` directly — always check permission names.

### Naming

- **Python:** `snake_case` files, functions, and variables. Classes are `PascalCase`.
- **JavaScript/JSX:** `PascalCase` components, `camelCase` hooks and utilities, `kebab-case` file names for non-component assets.
- **JSON API bodies (both directions):** `snake_case`. This deviates from the JS convention on purpose — the backend is the source of truth and doesn't rewrite on serialization. If you touch a route response shape, keep it `snake_case`.
- **MongoDB collections:** `snake_case`, plural (`entity_types`, `field_definitions`, `records`, `share_links`).
- **`_id` on documents is a string UUID**, not `ObjectId`. Every collection uses UUIDs so shard-friendly ids don't leak Mongo-ish behavior into API responses.

### State management

React Context + hooks. **No Redux, no Zustand, no MobX.** Providers wired in `App.js`:

- `AuthProvider` (`lib/auth.jsx`) — tokens + current user.
- `TerminologyProvider` (implicit via `useTerminology` reading auth context).
- `TabsProvider` (`lib/tabs.jsx`) — tab strip state.
- `<Toaster/>` from `sonner` for notifications.

### Error handling

- **Backend:** always raise `HTTPException(status_code, detail={...})` with structured `detail`. Validation errors surface as `422 {"detail": {"errors": {"fields.<key>": "message"}}}`. Never leak a raw stack trace to the client.
- **Frontend:** wrap the router in `<ErrorBoundary/>` (`/app/frontend/src/components/ErrorBoundary.jsx`) — it renders a graceful "Something broke on this page" screen. Individual pages catch API errors through the axios interceptor in `lib/api.js` and surface with `toast.error(formatError(e))`.

### PWA

Service worker registered by `lib/sw-register.js`. **When you deploy any change to a cached asset (HTML, CSS, JS chunks, icons), bump the `SW_VERSION` constant in `/app/frontend/public/sw.js`** — otherwise repeat visitors get the previous build until they hard-reload. There is no automatic asset-hash invalidation.

### Test credentials

Live in `/app/memory/test_credentials.md`. Contains owner / editor / viewer / demo accounts for the seeded Acme org, plus their passwords. **Do not commit real production credentials to this file.** Testing agents and forked branches read from this file.

---

## 8. Access Details

| Item | Value / Notes |
| --- | --- |
| **GitHub repository** | Customer will grant access separately (invitation email). |
| **Preview URL** | `https://org-platform-13.preview.emergentagent.com` (from `/app/frontend/.env`). |
| **Production URL** | `https://ubos.aariko.in` — customer's custom domain. Currently pending deploy retry (see [Known Issues](#6-known-issues) #1). |
| **MongoDB Atlas cluster** | Not yet provisioned. Customer will share the SRV URI directly out-of-band once created. |
| **Google OAuth credentials** | Customer will provide `GOOGLE_CLIENT_ID` + `GOOGLE_CLIENT_SECRET` out-of-band. |
| **Email provider account** | Customer to decide between Resend / SendGrid / AWS SES and provide the corresponding key out-of-band. |
| **S3 bucket + AWS credentials** | Only needed if `STORAGE_BACKEND=s3`. Customer to provide out-of-band. |
| **Test credentials file** | `/app/memory/test_credentials.md` (in-repo). |
| **Deploy platform account** | Emergent — customer owns the workspace. Contact the customer for platform access if you need to redeploy or view logs beyond `/app/backend/dev_emails.log` and pod logs. |

---

**End of handoff.** If anything in this document does not match what you find in the code, the code wins — file paths and line numbers were verified against the tree at commit time, but drift is inevitable. When in doubt, `grep`.
