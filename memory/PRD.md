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

## Phase 3 Sub-pass A — Records Core (2026-02) — LOCKED ✅

**Status:** e1_tester independent verification 23/23 PASS. No open issues.

**Explicit design decision (locked):** `GET /records/{id}/activity` + `/versions` return 404 for soft-deleted records. Users restore first, then inspect history. `tenant_filter` is NOT relaxed on these endpoints in Sub-pass B.

**Backend:**
- **Query Builder** (`services/query_builder.py`) — 10 operators (eq/ne/contains/gt/lt/gte/lte/between/in/not_in/is_empty/is_not_empty) with strict per-field-type validation (422 on invalid op × type). `in`/`not_in` reserved for `dropdown`/`multi_select` only; unknown fields fall back to `text` and reject `in`/`not_in`. Supports system fields (title/record_number/created_at/updated_at) and dynamic `fields.*`. Mirrored client-side in `frontend/src/lib/filterOps.js`.
- **Saved Views** (`routes/views.py` + `views` collection) — CRUD + `/duplicate` + `/set-default`. Private per-user with optional org-wide sharing (owner/admin only). Stores layout, q, filters, sort, category_ids, tag_ids, visible_fields, column_widths.
- **`POST /entity-types/{et_id}/records/search`** — accepts `{q, category_id, tag_ids, filters, sort, limit(≤200), skip, view_id}`. Auto-applies caller's default view when `view_id` omitted (user-scoped default takes priority over org-shared default). Body override semantics: `q`/`sort`/`category_id`/`tag_ids` — body wins when truthy; `filters` — merged per `field` key (body's condition on a field replaces the view's condition on that same field, other view filters survive). Response includes `applied_view_id`. Documented in OpenAPI description.
- **Activity Timeline** (`record_activity` collection) — created/updated/deleted/comment/restored events with actor_name denormalized. `GET/POST /records/{id}/activity`. Update payload includes per-field before/after diff. Comment endpoint validates non-empty text; requires `records.update`.
- **Version History** (`record_versions` collection) — every mutating operation snapshots the pre-update state. `GET /records/{id}/versions` + `GET /records/{id}/versions/{v}` + `POST /records/{id}/versions/{v}/restore` (writes pre-restore snapshot, applies fields/cats/tags, increments version, emits restored activity). Unique index on `(org_id, record_id, version_number)` guarantees exactly one row per version_number; `services/history.snapshot_version` swallows `DuplicateKeyError` so the earliest snapshot wins. Startup migration `_dedupe_record_versions` collapses any pre-existing duplicates before the unique index builds.
- **Bulk Actions** — `POST /entity-types/{et_id}/records/bulk` with typed discriminated union: `BulkDeleteAction` / `BulkAssignCategoriesAction` / `BulkAssignTagsAction` / `BulkUpdateFieldAction`. Each carries a per-action payload model with `extra="forbid"` — OpenAPI publishes `oneOf` + `discriminator.mapping` keyed on `action`. `assign_*` supports `mode` add/remove/replace. `update_field` allowed for `text/longtext/number/currency/boolean/dropdown/date/datetime/email/phone/url`; blocked with 422 for richtext/multi_select/image/file/relation; blocks bulk-set of unique fields to a non-empty value across multiple records. Every action emits activity + audit.
- **qr_payload** — set on record create as `{PUBLIC_APP_URL || APP_BASE_URL}/r/{record_id}`. Startup migration `_backfill_qr_payload` (re)writes any record whose qr_payload doesn't match the current base. `PUBLIC_APP_URL` added to `backend/.env` pointing at the public preview URL.
- **Indexes** — `(org_id, entity_type_id, category_ids)`, `(org_id, entity_type_id, tag_ids)`, `(org_id, entity_type_id, updated_at desc)`, `(org_id, entity_type_id, deleted_at)` on records. Compound indexes on views, record_activity (ts desc), record_versions (version desc + unique constraint).
- **Snapshot ordering** — `update_record` snapshots *after* validation succeeds so failed PATCH payloads don't create orphan versions.

**Frontend:**
- **RecordsPage rewritten** — top row has Views picker + 5-layout switch (Table/Gallery/Grid/Card/List) + search. Second row has Category filter dropdown + toggleable tag pills + Filter chips + Sort popover + Clear button.
- **5 layouts** (`components/RecordLayouts.jsx`) — Table (multi-select checkboxes + row actions), Gallery (large tiles with monogram), Grid (dense cards), Card (2-column detail cards), List (compact rows). Every record row / card has `open-record-{record_number}` link to detail.
- **FilterBar** (`components/FilterBar.jsx`) — Add-filter popover with field → op dropdown filtered to valid ops for the picked field's type, dynamic value input (single/range/list/boolean/dropdown). Chips show `{Label} {op} {value}` with X. Sort popover supports multi-key ordering.
- **ViewsBar** (`components/ViewsBar.jsx`) — dropdown listing "All records" + saved views (star = default, "shared" badge). Save-as / Update-active / Duplicate / Set-default / Delete inline actions. Shared toggle only visible for owner/admin.
- **BulkToolbar** (`components/BulkToolbar.jsx`) — sticky top banner on selection with Categories (add/remove/replace + CategoryPicker), Tags (add/remove/replace + TagCombobox), Edit field (dynamically renders `DynamicField` for the picked field; unsupported types filtered out), Delete, and Clear. Toasts show `{updated} updated, {skipped} skipped`.
- **RecordDetailPage** (`pages/RecordDetailPage.jsx`) — route `/records/:id`. Tabs Overview / Activity / Versions / Attachments (stub) / Relationships (stub). Overview grid of all fields. Activity has comment box + timeline with actor avatars and diff rendering. Versions shows all versions with actor + timestamp; clicking opens a side-by-side diff dialog with Restore action. Right rail: metadata (created/updated/version/QR payload), categories, tags.
- **Route added** in `App.js`, "Views" chip in the sidebar removed since it's now real.

**Verification history:**
- First testing pass: `/app/test_reports/iteration_6.json` — 16/16 backend + all critical frontend flows PASS. Surfaced 4 items (qr_payload localhost env, orphan-version race, redundant right-rail stub, in/not_in gap).
- Patch pass (4 fixes): all confirmed via curl locally.
- e1_tester independent re-verification: 23/23 PASS. Sub-pass A LOCKED.

## Phase 3 Sub-pass B — Media + Relationship Instances (2026-02) — LOCKED ✅

**Status:** VERIFIED. iteration_7 → 18/18 backend + 100% critical frontend flows PASS. Independent verification then surfaced 2 API-consistency items (thumb response shape, audit filter visibility) + 1 bonus (fresh-org default quota). All folded in via iteration_8 → **42/42 pytest tests pass in isolation** (41/42 under pytest-xdist due to a pre-existing test race — flagged as test-only refactor, not an app bug).

### Sub-pass B patch (2026-02)
- **`GET /api/media/{id}/thumb` now returns a uniform `{url, mime}` JSON envelope for every media doc.** Image mimes → `url` points at a signed `/api/media/serve/<token>` link to a Pillow-generated 256×256 JPEG (mime `image/jpeg`). Non-image / SVG mimes → `url` points at the new public static endpoint `/api/media/mime-icon/{family}` (mime `image/svg+xml`). Corrupt-image and non-LocalDisk-adapter paths gracefully degrade to the family icon URL. Endpoint description updated in OpenAPI. **Contract is now consistent regardless of underlying mime.**
- **`/api/media/mime-icon/{family}`** — publicly accessible, no auth. Origin sets `Cache-Control: public, max-age=86400, immutable` + `CDN-Cache-Control: public, max-age=86400, immutable` + strong md5 `ETag` + `Last-Modified` + `Vary: Accept-Encoding`. **Weak-ETag comparison per RFC 7232 §2.3.2 in the `If-None-Match` handler** — CDNs (Cloudflare, Fastly) that re-gzip the body downgrade our strong `"..."` tag to a weak `W/"..."`; the endpoint normalises both sides so 304 revalidation works end-to-end even where the ingress rewrites `Cache-Control`. `*` wildcard also honoured. Family shortcuts: `pdf`, `doc`, `xls`, `ppt`, `txt`, `video`, `audio`, `image`, `generic`; unknown family falls back to the generic icon. `include_in_schema=False` (documented in the `/thumb` endpoint description as the target of returned URLs).
- **`GET /api/audit-logs` gains `target_type` and `target_id` filters** so testers (and admin UI) can grep cascade events, media events, etc. `?action=` was already supported; now `?action=record.cascade_deleted&target_id=<src>` narrows precisely. New indexes `(org_id, action, ts desc)` and `(org_id, target_id)` on `audit_logs`.
- **Fresh organizations get exactly `DEFAULT_ORG_STORAGE_QUOTA_BYTES` at creation.** `_org_helpers.create_organization` now sets `settings.storage_quota_bytes = env(DEFAULT_ORG_STORAGE_QUOTA_BYTES, 5 GB)` on insert so tests + fresh installs are deterministic. Verified: `POST /api/orgs` returns `settings.storage_quota_bytes = 5368709120`.
- **Cascade-delete audit event confirmed emitting properly** — `?action=record.cascade_deleted` returns entries carrying `target_type='record'`, `target_id=<deleted_source_id>`, `diff.cascaded_ids=[…]`, `diff.count`.

### Sub-pass B main deliverables (retained from initial pass)

**Backend:**
- **Storage abstraction** (`core/storage/`) — `StorageAdapter` ABC + `LocalDiskAdapter` (atomic writes, sha256, HMAC-signed `/api/media/serve/{token}` URLs with 1h TTL) + `S3Adapter` stub (imports safely without boto3) + `factory.get_storage_adapter()`.
- **Media collection** — `{_id, org_id, uploader_id, filename, mime, size, checksum, storage_backend, storage_key, thumb_key?, width?, height?, attached_to[], created_at, updated_at, deleted_at}`. Indexes: `(org_id, deleted_at)`, `(org_id, checksum)` (dedup), `(org_id, attached_to.record_id)`, `(org_id, created_at desc)`.
- **Endpoints** — `POST /media/upload` (streaming multipart with early-bail if > `MAX_UPLOAD_SIZE_BYTES`; per-org same-checksum dedup; optional `record_id`/`field_key`/`role` for attach-on-upload). `GET /media`, `GET /media/:id` (with attached_to record hydration), `GET /media/:id/file` (returns `{url, filename, mime, size}` with signed URL), `GET /media/:id/thumb` (uniform `{url, mime}` envelope). `POST /media/:id/attach`, `POST /media/:id/detach`, `DELETE /media/:id` (409 with attached_to detail unless `?cascade=true` which detaches from `records.fields.<key>`, refunds quota, removes source + thumb from disk). `GET /media/serve/{token}` (HMAC-verified, streams with `nosniff` + `CORP same-origin`).
- **Quota service** — `check_can_upload` raises 413 with `code=file_too_large` OR `code=quota_exceeded`; `add_bytes` per-org counter; `set_quota` (100 MB ≤ q ≤ 100 GB) returns AFTER doc. `PATCH /orgs/:id/storage-quota` gated by `org.update`.
- **Field types activated** — `image` and `file` no longer stubbed. Async post-pass validates media exists in the same org + mime family + `max_size_mb` + `allowed_mimes`.
- **Record hooks** — create attaches, update diffs old-vs-new media_ids per image/file field and attach/detach symmetrically, delete detaches + cascades relationship targets when `rel_def.cascade_delete=true`.
- **Relationship instances** — bidirectional writes on `records.relationships[]`, cardinality enforced (`one_to_one` / `one_to_many` / `many_to_many`), 422 on entity-type mismatch, `record.cascade_deleted` audit event.
- **Audit events**: `media.uploaded / attached / detached / deleted`, `record.linked / unlinked / cascade_deleted`, `org.quota_updated`.
- **Migration**: `_backfill_org_storage_fields` sets `storage_used_bytes:0` on any org that lacks it.

**Frontend:**
- `MediaThumb`, `MediaUploadZone`, `ImageFieldRenderer`, `FileFieldRenderer`, `RecordPicker`, `RelationshipsPanel`, `AttachmentsPanel`, `StorageQuotaBar` — all new.
- `MediaPage` (`/media`) with grid + mime filter chips + filename search + storage bar + drawer + bulk delete.
- `RecordDetailPage` Attachments and Relationships tabs render real panels (previous "Coming in the next update" strings removed).
- `OrgSettingsPage` gets a Storage panel with editable quota (owner/admin only).
- Sidebar unchips Media.
- `DynamicField` routes image/file to the two new renderers.

**Env additions** (`backend/.env`): `STORAGE_BACKEND=local`, `LOCAL_STORAGE_ROOT=/app/backend/uploads`, `MEDIA_SIGNING_SECRET`, `MAX_UPLOAD_SIZE_BYTES=26214400`, `DEFAULT_ORG_STORAGE_QUOTA_BYTES=5368709120`. New deps: `pillow`, `aiofiles`.

**Verification history:**
- iteration_7 (initial): 18/18 backend + Playwright frontend PASS
- iteration_8 (patch): 42/42 pytest tests in isolation (thumb envelope, audit filters, fresh-org quota, full Sub-pass B regression). 1 pre-existing test-only race under pytest-xdist (flagged, not a bug).
- iteration_9 (micro-patch): 30/30 tests PASS. Testing agent surfaced + fixed a CDN weak-ETag bug (Cloudflare downgrades strong ETags to `W/"..."` when re-gzipping; exact-string If-None-Match match broke 304 through the ingress). Fixed with RFC 7232 §2.3.2 weak comparison. **Sub-pass B fully LOCKED.**

**Environmental note (not a bug):** Through the `preview.emergentagent.com` Cloudflare layer, `Cache-Control` on the mime-icon endpoint is rewritten to `no-store, no-cache, must-revalidate` — this is an infrastructure behaviour outside app code. The origin (`localhost:8001`) serves the correct `public, max-age=86400, immutable`. Browsers still benefit end-to-end because `ETag` + `Last-Modified` pass through the ingress and `If-None-Match` → 304 revalidation works (verified with 0-byte 304 responses). Self-hosted or non-Cloudflare deployments will get full browser caching directly.

**Deferred (backlog):**
- S3Adapter real implementation
- SVG upload sanitisation (nh3/bleach) → lift `image/svg+xml` from the rejected-mimes list
- PDF page-1 thumbnails
- Refactor `TestMediaDeleteCascade` to compare quota delta vs media size instead of absolute `used_bytes` (avoids xdist worker cross-talk)

## Prioritized Backlog
- **P1 (next)**: QR PNG / barcode generation / printable labels; Public share links (read-only tokenised record URLs); Dashboard widgets; Global search UI
- **P2**: CSV/Excel import-export; User invitations flow
- **P3**: Electron wrapper; Expo mobile mirror; Migrate FastAPI on_event → lifespan
- **Deferred quality items**: S3Adapter real implementation; SVG upload sanitisation (nh3/bleach) so we can lift the SVG mime rejection; PDF page-1 thumbnails; sweep any orphan `.thumb.jpg` files that got left behind by pre-hardening deletes (new deletes now clean them up).


## Phase 4 Sub-pass A — Sharing + QR/Barcode + Printable Labels (SHIPPED Feb 2026)

**Backend**
- `share_links` collection (token unique, per-record listing, revoke lifecycle).
- `POST /records/{id}/shares`, `GET /records/{id}/shares`, `PATCH /shares/{id}`, `POST /shares/{id}/revoke`, `DELETE /shares/{id}`.
- Public read: `GET /api/public/records/{token}` + `.../qr.png` + `.../barcode.png` + `.../media/{id}`.
- Authed codes: `GET /api/records/{id}/qr.png`, `GET /api/records/{id}/barcode.png` — LRU-cached in memory (no persistence).
- Label rendering: `GET /api/labels/presets` (Avery 5160/5163/L7160/L7163), `POST /api/records/labels`, `POST /api/entity-types/{et_id}/records/labels` (view-scoped, X-Records-Included header).
- `field_definitions.sensitive: bool = False` — always stripped from public share payloads (also honours legacy `config.sensitive`).
- Optional-auth dependency `try_auth` (never raises 401) enables `org_only` visibility resolution on public endpoints.
- In-memory rate limiter (env-configurable via `PUBLIC_READ_RATE_LIMIT` / `PUBLIC_CODE_RATE_LIMIT`) with per-IP+route buckets; honours `X-Forwarded-For`.
- Visibility semantics: `public` (open), `org_only` (requires matching-org auth), `private` (creator + admins only). Expired/revoked share → 410; underlying record soft-deleted → 404; org soft-deleted → 410 with `code: org_gone`.
- `visible_fields` distinguishes `null` (all non-sensitive), `[]` (title/record # only), and `list` (intersection with non-sensitive).

**Frontend**
- Public page `/s/:token` — read-only view with QR + Code128 sidebar, expiry banner in footer, optional "Report a problem" mailto when org has `settings.support_email`.
- Right-rail **Share & Print** card on RecordDetailPage — inline QR (~104px) + Code128 (~90px) previews, create/list/revoke/delete public shares, launch Print Labels dialog.
- **PrintLabelsDialog** — preset picker, code mode (QR + Code128 / QR only / Code128 only), copies, start slot, extra field chips, live label-count stats, downloads PDF.
- **BulkToolbar** gains a "Print labels" action for selected records.
- **FieldsPage** exposes a `Sensitive` toggle in the field builder + a red `sensitive` badge in the row.

**Tests**: 28/28 backend pass (`/app/backend/tests/test_ubos_phase4a.py`); frontend flows verified via testing agent.

**Deferred to Sub-pass B**: Global data-search UI, Dashboard widgets. Password-protected shares, whole-view sharing, and CSV import/export are Phase 5.
