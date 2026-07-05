# UBOS — Universal Business Operating System

## Vision
Multi-tenant SaaS platform where any organization can define its own entity types and records without code changes. Desktop-first React SPA + PWA (later wrapped in Electron / mirrored to Expo — NOT built in Phase 0).

## Stack (locked)
- **Backend:** FastAPI + Motor (async MongoDB) + Pydantic v2
- **Frontend:** React (JS + CRA for Phase 0, TypeScript+Vite migration deferred) + Tailwind + shadcn/ui + React Router
- **DB:** MongoDB (single generic `records` collection)
- **Routing:** All backend routes prefixed with `/api/*`; OpenAPI at `/api/openapi.json`
- **Location:** `/app/backend/`, `/app/frontend/`

## Architecture — Core Bet
**One generic `records` collection driven by dynamic `field_definitions` per `entity_type`.** If this proves out, the platform becomes truly no-code for any business domain. Phase 0 is the POC of exactly this.

## Multi-Tenancy Foundation (Phase 0)
- No auth yet. Hardcoded default `org_id = "demo-org"`.
- Every request accepts `X-Org-Id` header (defaults to `demo-org`).
- Every DB query MUST filter by `org_id`. Helper: `tenant_filter(org_id)`.
- This foundation stays through all phases; auth layer will just provide the `org_id`.

## Data Model

### `entity_types`
```
{ _id, org_id, key, name_singular, name_plural, icon, color, description,
  is_system, record_counter, created_at, updated_at, deleted_at }
```
Indexes: unique `(org_id, key)`, `(org_id, deleted_at)`

### `field_definitions`
```
{ _id, org_id, entity_type_id, key, label, type, config, required, unique,
  order, group, help_text, created_at, updated_at, deleted_at }
```
Types (Phase 0):
- Implemented + validated: `text`, `longtext`, `richtext`, `number`, `currency`, `date`, `datetime`, `boolean`, `dropdown`, `multi_select`, `email`, `phone`, `url`
- Stub-accepted (Phase 3): `image`, `file`, `relation`

Indexes: unique `(org_id, entity_type_id, key)`

### `records`
```
{ _id, org_id, entity_type_id, title, description, fields: {<dynamic>},
  record_number, search_text, version, created_at, updated_at, deleted_at }
```
Indexes: `(org_id, entity_type_id, deleted_at)`, text index on `search_text`

## Metadata Engine — `FieldValidator`
Given a list of `field_definitions` for an entity_type, validates a `fields` dict:
- Type coercion (numbers, dates, booleans, emails, urls, phones)
- `required` enforcement
- `unique` enforcement (DB query scoped by org + entity_type + optional exclude id)
- `config` rules: dropdown options, multi_select options, number min/max, string patterns/max length
- Returns structured errors keyed by field path (`fields.<key>: message`)
- Denormalizes readable text values into `search_text` on save

## Phase 0 API Surface
```
GET    /api/health
GET    /api/openapi.json

GET    /api/entity-types
POST   /api/entity-types
GET    /api/entity-types/{id}
PATCH  /api/entity-types/{id}
DELETE /api/entity-types/{id}          (soft delete)

GET    /api/entity-types/{id}/fields
POST   /api/entity-types/{id}/fields
PATCH  /api/fields/{id}
DELETE /api/fields/{id}
POST   /api/entity-types/{id}/fields/reorder

GET    /api/entity-types/{id}/records?q=&limit=&skip=
POST   /api/entity-types/{id}/records
GET    /api/records/{id}
PATCH  /api/records/{id}
DELETE /api/records/{id}

POST   /api/dev/seed-demo
```
- Pydantic v2 models
- 422 for validation, 404 for missing, 409 for conflicts

## Frontend (Phase 0)
Desktop-first (min-width 1024px). Sidebar + content. Routes:
- `/` → redirect to `/entity-types`
- `/entity-types` — list + create + delete
- `/entity-types/:id/fields` — field builder (all 13 types + config, reorder, delete)
- `/entity-types/:id/records` — dynamic table + dynamic form based on field_definitions

Sidebar footer holds "Load demo data" CTA (calls `/api/dev/seed-demo`), also surfaced in empty state.

## Design Guidelines
- Font: **IBM Plex Sans** (body/headings) + **IBM Plex Mono** (record numbers, field keys) — distinctive workspace typography
- Palette: stone/zinc neutrals, off-white background, **teal-700** primary
- Components: shadcn/ui (Card, Table, Dialog, Select, DropdownMenu, Input, Textarea, Switch, Sonner toasts)
- No emoji icons — use `lucide-react`
- Empty states, breadcrumbs, inline field errors

## Phase 0 Success Criteria
1. Create entity type "Products" with key `products`
2. Add fields: `sku` (text, required, unique), `price` (currency, required, min 0), `in_stock` (boolean), `category` (dropdown), `launch_date` (date), `notes` (longtext)
3. Create 3 records — validation errors show for missing required / duplicate SKU / negative price
4. List, edit, delete records
5. Repeat with entity type "Machines" (`serial_no`, `manufacturer`, `installed_at`) — proves genericity

## Phase 0 Non-Goals
No auth, no orgs UI, no media/QR, no search UI, no categories/tags, no views, no sharing, no dashboard.

## Roadmap (post Phase 0)
- **Phase 1:** Auth + orgs (Emergent auth), roles, `org_id` from session
- **Phase 2:** Search UI, saved views, filters, sorts, categories/tags
- **Phase 3:** Media fields (image/file), relations, QR
- **Phase 4:** Dashboards, sharing, public views
- **Phase 5:** Electron wrapper + Expo mirror

## What's Implemented (Phase 0 — Feb 2026)
- Metadata engine + generic records collection
- Full CRUD for entity_types, field_definitions, records
- FieldValidator across 13 types (image/file/relation stubbed)
- Tenant scoping via `X-Org-Id` header + `tenant_filter()`
- POC UI with sidebar, 3 routes, dynamic form/table, demo seed CTA

## Prioritized Backlog
- P0: Auth (Phase 1)
- P1: Search UI & saved views (Phase 2)
- P1: Media + relations (Phase 3)
- P2: Dashboards / sharing (Phase 4)
- P2: Electron / Expo (Phase 5)
