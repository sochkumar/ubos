# UBOS — Universal Business Operating System

> Multi-tenant SaaS platform where any organization can define its own entity
> types and records without code changes. Desktop-first React SPA + PWA.

UBOS is built on a single generic `records` collection driven by dynamic
`field_definitions` per `entity_type`. Add a new entity type in the UI → its
records, forms, tables, and searches all become available immediately, without
touching the codebase.

---

## Features

- **Metadata engine** — Define custom entity types with 13 field kinds
  (`text`, `longtext`, `richtext`, `number`, `currency`, `date`, `datetime`,
  `boolean`, `dropdown`, `multi_select`, `email`, `phone`, `url`) plus native
  `image`, `file`, and `relation` fields.
- **Auth & RBAC** — Email/password + Google OAuth (env-gated), JWT access +
  refresh rotation, four seeded roles (owner/admin/editor/viewer), per-org
  memberships, brute-force lockout, invitations by email.
- **Records** — Categories (hierarchical), tags (org-wide or entity-scoped),
  relationship instances (one-to-one/one-to-many/many-to-many), five layout
  modes (Table/Gallery/Grid/Card/List), saved views, filters, sort, bulk
  actions, activity timeline, version history, soft-delete + restore.
- **Import / Export** — CSV + XLSX round-trip with a 4-step import wizard
  (upload → preview → mapping → run) and background async runner.
- **Media** — Pluggable storage adapter (local disk shipped, S3 stub),
  streaming multipart uploads, per-org quotas, per-record attachments,
  image thumbnails, PDF page-1 thumbnails, mime-family icons.
- **Sharing & Labels** — Password-protected public share links for both
  individual records and saved views. Printable QR + Code128 labels
  (Avery 5160/5163/L7160/L7163 + custom sizes).
- **Search** — Global `⌘K` command palette (records / entity types /
  categories / tags / media), full search page with facets, deep-linkable
  filter state.
- **Dashboards** — Recent records, activity feed, storage breakdown, entity
  types overview. Customizable via drag-and-drop with hide/show, saved
  per-user + per-org.
- **PWA** — Manifest + service worker (network-first shell, cache-first
  assets, `/api/*` bypass), install prompt, cross-browser date picker,
  keyboard shortcuts, error boundaries, standardized toasts.

---

## Stack

| Layer     | Technology                                             |
|-----------|--------------------------------------------------------|
| Backend   | FastAPI + Motor (async MongoDB) + Pydantic v2 + uvicorn|
| Frontend  | React (CRA) + Tailwind + shadcn/ui + React Router      |
| DB        | MongoDB (single generic `records` collection)          |
| Storage   | Pluggable — Local disk (default) or S3 (stubbed)       |
| Email     | Dev logger (default) / Resend / SendGrid / AWS SES     |
| Auth      | JWT (`python-jose`) + bcrypt, optional Google OAuth    |

All backend routes are prefixed with `/api/*`; OpenAPI at `/api/openapi.json`.

---

## Repo layout

```
/app
├── backend/                     FastAPI app
│   ├── server.py                app factory + lifespan
│   ├── routes/                  HTTP handlers (one router per feature)
│   ├── services/                cross-cutting logic (validator, history, ...)
│   ├── core/                    storage adapters, email providers, request-ip
│   ├── modules/templates/       built-in workspace templates (JSON)
│   ├── scripts/seed.py          idempotent seed CLI
│   ├── tests/                   pytest suite (Phase 0 → 6a)
│   └── requirements.txt
├── frontend/                    React SPA (CRA + Craco)
│   ├── src/
│   ├── public/                  PWA manifest + service worker + icons
│   └── package.json
├── memory/                      PRD + credentials for local devs
├── docker-compose.yml           full local stack (mongo + backend + web)
├── backend/Dockerfile
├── frontend/Dockerfile          multi-stage: node build → nginx serve
├── frontend/nginx.conf          SPA fallback + /api/* proxy
└── README.md
```

---

## Environment variables

Copy the examples then edit values for your environment:

```bash
cp backend/env.example backend/.env
cp frontend/env.example frontend/.env
```

### Backend (`backend/.env`)

| Variable                            | Required | Default                                  | Notes                                                                  |
|-------------------------------------|:--------:|------------------------------------------|------------------------------------------------------------------------|
| `MONGO_URL`                         | ✅       | `mongodb://localhost:27017`              | Connection string.                                                     |
| `DB_NAME`                           | ✅       | `test_database`                          | Database name (MUST match your data).                                  |
| `CORS_ORIGINS`                      |          | `*`                                      | Comma-separated allowed origins.                                       |
| `JWT_SECRET`                        | ✅       | —                                        | HS256 signing secret; rotate for prod.                                 |
| `JWT_ACCESS_TTL_MINUTES`            |          | `15`                                     | Access-token TTL.                                                      |
| `JWT_REFRESH_TTL_DAYS`              |          | `30`                                     | Refresh-token TTL.                                                     |
| `GOOGLE_CLIENT_ID` / `_SECRET`      |          | `REPLACE_ME`                             | Enables Google OAuth when both are set to real values.                 |
| `APP_BASE_URL`                      |          | `http://localhost:3000`                  | Used in emails / OAuth redirects.                                      |
| `PUBLIC_APP_URL`                    |          | *(same as APP_BASE_URL)*                 | Base URL embedded in `qr_payload` for record QR codes.                 |
| `STORAGE_BACKEND`                   |          | `local`                                  | `local` or `s3`.                                                       |
| `LOCAL_STORAGE_ROOT`                |          | `/app/backend/uploads`                   | Where local uploads land.                                              |
| `MEDIA_SIGNING_SECRET`              | ✅       | —                                        | HMAC secret for `/api/media/serve/{token}` links.                      |
| `MAX_UPLOAD_SIZE_BYTES`             |          | `26214400` (25 MB)                       | Per-file upload cap.                                                   |
| `DEFAULT_ORG_STORAGE_QUOTA_BYTES`   |          | `5368709120` (5 GB)                      | Default per-org quota on org create.                                   |
| `SEED_USERS`                        |          | `true`                                   | Auto-seed `owner/editor/viewer@ubos.test` if `users` collection empty. |
| `EMAIL_FROM` / `EMAIL_FROM_NAME`    |          | `noreply@ubos.local` / `UBOS`            | Sender identity for outbound email.                                    |
| `RESEND_API_KEY`                    |          | —                                        | Enables Resend provider when set.                                      |
| `SENDGRID_API_KEY`                  |          | —                                        | Enables SendGrid provider when set.                                    |
| `AWS_SES_REGION`                    |          | —                                        | Enables SES provider when set.                                         |
| `INVITE_RATE_LIMIT_PER_HOUR`        |          | `20`                                     | Per-org invitation throttle.                                           |
| `PUBLIC_READ_RATE_LIMIT`            |          | `120/minute`                             | Per-IP+route bucket for public share reads.                            |
| `PUBLIC_CODE_RATE_LIMIT`            |          | `60/minute`                              | Per-IP+route bucket for public QR/barcode.                             |
| `TRUST_PROXY_HOPS`                  |          | `1`                                      | XFF hops to trust for client IP.                                       |
| `EXPORT_MAX_ROWS` / `IMPORT_MAX_*`  |          | —                                        | Export/import guardrails.                                              |

### Frontend (`frontend/.env`)

| Variable                    | Required | Notes                                                                       |
|-----------------------------|:--------:|-----------------------------------------------------------------------------|
| `REACT_APP_BACKEND_URL`     | ✅       | Absolute URL of the backend (e.g. `https://your-domain.com`). Used by axios.|
| `REACT_APP_ENABLE_SW`       |          | `1` to enable the service worker in production builds.                      |
| `WDS_SOCKET_PORT`           |          | `443` when behind an HTTPS proxy for dev-server HMR.                        |

---

## Running locally (bare metal)

Prereqs: Python 3.11+, Node 18+, `yarn`, MongoDB running on `localhost:27017`,
`poppler-utils` on your PATH (needed by `pdf2image`).

```bash
# ─── backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp env.example .env                 # then edit as needed
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# ─── frontend (in another shell)
cd frontend
yarn install
cp env.example .env                 # then edit REACT_APP_BACKEND_URL
yarn start                          # http://localhost:3000
```

### Seed test users

The backend auto-seeds `owner@ubos.test / editor@ubos.test / viewer@ubos.test`
(password `Passw0rd!` for each) plus an org "Acme Furniture" when the `users`
collection is empty and `SEED_USERS=true`.

For a clean reset or a repeatable seed:

```bash
cd backend
python -m scripts.seed          # idempotent — safe to re-run
python -m scripts.seed --reset  # wipe & re-create
python -m scripts.seed --minimal # skip demo records
```

### Load demo data

Once signed in you can either:
- Click **Load demo workspace** in the onboarding wizard, or
- POST `/api/dev/seed-demo` (creates the "Products" + "Machines" template pair
  documented in the PRD).

---

## Running with Docker Compose

The `docker-compose.yml` at the repo root brings up **MongoDB + backend + web**
end-to-end, with the frontend served by nginx and `/api/*` proxied to the
backend container (same-origin, no CORS gymnastics).

```bash
# 1) point to a fresh env
cp backend/env.example backend/.env
cp frontend/env.example frontend/.env

# 2) build + start
docker compose up --build

# → open http://localhost:8080
# → backend visible internally at http://backend:8001, browser hits /api/* via nginx
# → mongo persisted on the ubos_mongo_data named volume
```

Uploads land on the `ubos_uploads` named volume and survive container rebuilds.

To stop and clean up:

```bash
docker compose down                 # keep volumes
docker compose down -v              # nuke mongo + uploads
```

### Notes on the frontend Docker build

- The frontend is built with `REACT_APP_BACKEND_URL=/` (empty prefix) so all
  API calls are relative and go through the same nginx that serves the SPA.
  Nginx then proxies `/api/*` → the `backend` service on port 8001.
- SPA routing is preserved with `try_files $uri $uri/ /index.html;`.
- Static assets are served with long-lived immutable cache headers; `index.html`
  is served no-cache so app updates roll out on next load.

---

## API reference

- **OpenAPI (JSON)**: `GET /api/openapi.json`
- **Swagger UI**: `GET /docs` (mounted by FastAPI)
- **Health probe**: `GET /api/health` → `{"status":"ok","db":"up"}`

Key groups: `/api/auth/*`, `/api/orgs/*`, `/api/entity-types/*`,
`/api/fields/*`, `/api/records/*`, `/api/views/*`, `/api/shares/*`,
`/api/view-shares/*`, `/api/media/*`, `/api/labels/*`, `/api/search`,
`/api/dashboard/*`, `/api/invitations/*`, `/api/audit-logs`.

---

## Testing

```bash
cd backend
pytest -q                     # full suite
pytest -q tests/test_ubos_phase6a.py  # a single phase
```

The tests spin up their own event loop and expect MongoDB at `MONGO_URL`.

---

## Deployment

For a self-managed VM:

1. Set `JWT_SECRET`, `MEDIA_SIGNING_SECRET` to strong random values (32+ bytes).
2. Point `MONGO_URL` at your managed MongoDB.
3. Configure a real email provider (`RESEND_API_KEY` or `SENDGRID_API_KEY`).
4. Set `APP_BASE_URL` + `PUBLIC_APP_URL` to your public domain.
5. Serve nginx on 443 with a TLS cert; the compose file's ports mapping is a
   starting point — swap `8080:80` for `443:443` with a cert-terminating
   reverse proxy (Caddy / nginx-proxy / Traefik) in front, or bake certs into
   the frontend image.
6. Point `STORAGE_BACKEND=s3` and wire up S3 credentials once you outgrow
   local disk (the S3 adapter is currently a stub — implement upload/download
   before flipping the switch in production).

---

## License

Proprietary — © 2026 UBOS. All rights reserved.
