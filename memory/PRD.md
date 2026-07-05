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

## What's Implemented (Phase 0 — Feb 2026) ✅ COMPLETE
- Metadata engine + generic records collection
- Full CRUD for entity_types, field_definitions, records
- FieldValidator across 13 types (image/file/relation stubbed)
- Tenant scoping via `X-Org-Id` header + `tenant_filter()`
- POC UI with sidebar, 3 routes, dynamic form/table, demo seed CTA

## What's Implemented (Phase 2 — Feb 2026) ✅ COMPLETE
**Backend:**
- **Categories** — hierarchical, materialized path (`path[]` + `path_names[]` + `depth`, max 10). Endpoints for CRUD + `/move` + `/reorder`. Circular guard + descendant recompute on move/rename. Soft-delete supports `?cascade=true` (delete descendants + strip from records) or default orphan (reparent children).
- **Tags** — org-wide or entity-scoped. `GET /tags?entity_type_id=&q=`, POST/PATCH/DELETE. Inline creation is `records.create`-gated; rename/delete is `entity_types.manage`. Auto color hash on create.
- **Relationship definitions** — schema-only (`from → to`, cardinality, required, cascade_delete). Instance CRUD deferred to Phase 3.
- **Records × Categories/Tags** — `records.category_ids[]` + `records.tag_ids[]`. Validated at save. Denormalized `category.record_count` + `tag.usage_count` maintained via `apply_record_diff` on create/update/delete. `GET /entity-types/{id}/records?category_id=&tag_ids=` — `category_id` matches descendants via materialized-path lookup.
- **Templates** — `TemplateApplier` service with rollback + skip/rename/error policies + dry_run. `GET /templates`, `GET /templates/{key}`, `POST /templates/{key}/apply`. 4 built-in libraries: catalog, inventory_lite, assets, crm_lite + `demo_basic`. `/api/dev/seed-demo` is now a thin wrapper around `apply_template("demo_basic")`.
- Audit events: category.*, tag.*, relationship.*, template.applied.

**Frontend:**
- `/templates` gallery with preview drawer + apply dialog (conflict-policy radio).
- `/entity-types/:id/categories` tree editor: HTML5 native drag-to-reparent, iterative tree renderer, right-side detail panel with rename/color/description + Move-to picker, delete dialog with cascade checkbox.
- `/entity-types/:id/tags` — list, inline create with color + scope toggle, delete with usage warning.
- `/entity-types/:id/relationships` — table + create dialog (target picker, key auto-slugify, cardinality radio, required/cascade switches).
- Onboarding wizard Step 2 shows the 4 real templates as one-click starters.
- Record dialog gains Categories multi-picker (tree checkboxes) + Tags combobox (autocomplete + inline "Create '..."'). Records table has Category column + inline tag chips + filter bar (category filter + toggleable tag chips + Clear).
- Entity type cards now expose 5 per-entity buttons: Fields · Categories · Tags · Rels · Records. Sidebar Config has Templates as a real link; Views chipped Phase 3.



## What's Implemented (Phase 2 — Feb 2026) ✅ COMPLETE
**Backend:**
- **Categories** (`categories` collection) — hierarchical with materialized path (`path[]` + `path_names[]` + `depth`), max depth 10. Endpoints: `GET|POST /entity-types/{id}/categories`, `GET|PATCH|DELETE /categories/{id}`, `POST /categories/{id}/move`, `POST /categories/{id}/reorder`. Circular-parenting guard + descendant path/name recompute on move+rename. Soft-delete with `?cascade=true` (removes descendants) or default orphan (children reparent to node's parent).
- **Tags** (`tags` collection) — org-wide (`entity_type_id: null`) or entity-scoped. Endpoints: `GET /tags?entity_type_id=&q=`, `POST /tags`, `PATCH|DELETE /tags/{id}`. Inline creation from records is `records.create`-gated (editor+); rename/delete is `entity_types.manage`. Auto color hash on create if not provided.
- **Relationship definitions** (`relationship_definitions` collection) — schema-only. `GET|POST /entity-types/{id}/relationships`, `GET|PATCH|DELETE /relationships/definitions/{id}`. Cardinality: one_to_one/one_to_many/many_to_many. **No instance CRUD** (Phase 3).
- **Records × Categories/Tags** — `records` doc gains `category_ids[]` + `tag_ids[]`. Save/update validates ids belong to same org+entity_type. Denormalized `category.record_count` + `tag.usage_count` maintained via `apply_record_diff()` service on create/update/delete. `GET /entity-types/{id}/records?category_id=&tag_ids=` — `category_id` filter matches descendants via materialized-path lookup, `tag_ids` uses `$in`.
- **Templates** — `GET /templates`, `GET /templates/{key}` (preview), `POST /templates/{key}/apply` with `{conflict_policy, dry_run}`. `TemplateApplier` service: rollback on failure, skip/rename/error policies, dry_run returns the plan without writes. 4 built-in libraries: **catalog**, **inventory_lite**, **assets**, **crm_lite**, plus `demo_basic` (old seed). `POST /api/dev/seed-demo` is now a thin wrapper around `apply_template("demo_basic")`.
- **Audit** — added events: `category.created/updated/moved/deleted`, `tag.created/updated/deleted`, `relationship.created/updated/deleted`, `template.applied`.

**Frontend:**
- **Templates gallery** at `/templates` with 4 template cards, Preview drawer (entity types + fields breakdown), Apply dialog with conflict-policy radio (skip/rename/error).
- **Categories tree editor** at `/entity-types/{id}/categories`: left = tree with HTML5 native drag-to-reparent + expand/collapse + inline "+ subcategory" and delete; right = detail panel with rename/color/description + "Move to…" parent picker. Delete dialog offers cascade checkbox.
- **Tags page** at `/entity-types/{id}/tags`: table with usage counts, scope pill (entity/org-wide), inline create dialog with color + scope toggle, delete with usage warning.
- **Relationships page** at `/entity-types/{id}/relationships`: table + "New relationship" dialog with target picker, key auto-slugify from `from_label`, cardinality radio, required/cascade switches.
- **Onboarding wizard** — Step 2 now shows the 4 real templates as one-click starters alongside "Start blank" and "Load demo workspace".
- **Records list + form updated** — record dialog has Categories multi-picker (tree checkboxes) and Tags combobox (autocomplete + inline "Create '...'" for editors). Records table has Category column + inline colored tag chips + filter bar (single-select tree category filter + toggleable tag chips + "Clear" button).
- **Entity Type cards** — now show 5 buttons: Fields · Categories · Tags · Rels · Records. Sidebar Config group has "Templates" as a real link + "Views" chipped Phase 3.
**Backend (auth + orgs + RBAC):**
- Email/password auth with bcrypt hashing + brute-force lockout (5 attempts / 15 min per ip+email)
- JWT access (15 min, python-jose HS256) + refresh (30 days, hashed in `refresh_tokens`, ROTATED on every refresh)
- Google OAuth via `authlib` — env-gated (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` = `REPLACE_ME` by default → `/auth/google/status` reports `{enabled:false}`)
- Google flow uses one-time exchange code (60s TTL) to avoid leaking tokens in URLs
- `/api/auth/*`: register, login, refresh, logout, me, forgot-password (dev logs reset URL), reset-password, change-password, google/status, google/login, google/exchange
- Organizations + memberships + roles (owner/admin/editor/viewer, seeded per-org). Endpoints: `POST/GET/PATCH /orgs`, `POST /orgs/{id}/switch`, `GET/PATCH/DELETE /orgs/{id}/members(/{mid})`.
- All Phase 0 endpoints migrated to `require_permission(...)` FastAPI dependency; JWT-derived `org_id` context (`X-Org-Id` still honored for API scripting when membership check passes)
- Audit log (background-task, non-blocking) for user.*, org.*, member.*, entity_type.*, field.*, record.* events; `GET /api/audit-logs` (admin+ only)
- **Test users auto-seeded** on empty DB: owner/editor/viewer @ubos.test + shared org "Acme Furniture"
- **Phase 0 demo-org data wiped** on first Phase 1 boot (documented migration choice; users re-seed via `/api/dev/seed-demo`)

**Frontend (AppShell + auth flows):**
- Public routes: `/login`, `/register`, `/forgot-password`, `/reset-password` under a two-panel `AuthLayout`
- `/auth/google/callback` handles OAuth exchange
- `/onboarding` two-step wizard (Create org → Start blank OR Load demo). Starter templates chip shows "Coming soon".
- Authed shell: sidebar with Overview/Data/Config/Settings groups (Config/Dashboard items show "Coming in Phase N" chips), plus topbar with org switcher dropdown (list + create), global search stub, notifications stub, user menu (Profile / Organization / Sign out)
- Settings pages: `/settings/organization`, `/settings/members` (role dropdown + remove), `/settings/audit-log` (admin+ only), `/settings/profile` (change password)
- `RequireAuth` guard + axios refresh interceptor (auto-refresh once on 401, redirect to `/login` on failure); tokens in localStorage (`ubos.access_token`, `ubos.refresh_token`)
- Google button disabled with tooltip when `/auth/google/status` returns `{enabled:false}`

**Bug fixes carried into Phase 1:**
- Field-key slugifier no longer strips underscores — it only strips non-alpha prefixes (backend regex `^[a-z][a-z0-9_]*$`)

## Prioritized Backlog
- P0: Starter templates gallery (Phase 2 hook)
- P1: Search UI, filters, sorts, saved views (text index already in place)
- P1: Media fields (image/file) + relations (upload playbook via `integration_playbook_expert_v2`)
- P1: Invitations flow (deferred from Phase 1)
- P2: Categories/tags, dashboards, sharing / public views
- P2: Electron wrapper + Expo mirror
- P3: Migrate FastAPI on_event → lifespan
