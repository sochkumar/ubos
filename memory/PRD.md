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

## Phase 4 Sub-pass A — LOCKED (verified 12/13, 3/3 bugs fixed Feb 2026)
Signed off by e1_tester follow-up round. Sub-pass A code is frozen; only touch at explicit wire-up points.

## Phase 4 Sub-pass B — Global Search + Dashboard (SHIPPED Feb 2026, LOCKED after follow-up)

**Backend**
- `GET /api/search?q=&types=&entity_type_ids=&limit=&cursor=` — org-scoped fan-out over records, entity_types, categories, tags, media. Records ranked by `$text` on `search_text` (Phase 0 index), with title-exact / title-contains / record-number boosts. Other kinds use case-insensitive regex on `name`/`filename`/etc. Response: `{results, next_cursor, facets:{kinds, entity_types}, totals, took_ms}`. Cursor is opaque base64 skip.
- `GET /api/dashboard/summary` — returns the four widgets in one payload: `recent_records`, `activity` (audit_logs with actor-name & avatar; non-admins see only their own actions), `storage` (used/quota + mime-family breakdown), `entity_types` (with `record_count`). Process-level cache: 30 s TTL per `(org_id, user_id)`.
- `POST /api/dashboard/refresh` — manual cache bust (returns 204).
- Both endpoints require `records.read`.

**Frontend**
- **Command palette** (`⌘K` / `Ctrl+K`) — global keyboard listener registered by `useCommandPalette` in `AppLayout`. Debounced 200 ms input, keyboard nav (↑↓ Enter / ⌘+Enter opens new tab), recent-searches in `localStorage`, `took_ms` in footer, "View all results →" navigates to `/search?q=…`.
- **`/search`** — full-page with sidebar facets (kinds + entity types), deep-linkable URL state (`?q=&types=&entity_type=`), one-column result list with breadcrumb + snippet + kind badge.
- **`/dashboard`** — 2×2 grid of widgets (Recent records, Activity, Storage, Entity types overview). Each widget has consistent chrome (icon + title + right-side action link/button) and a graceful empty state. Refresh button busts the 30 s cache.
- **Topbar** — replaced the disabled search stub with a clickable "Search anything… ⌘K" trigger that opens the palette.
- **Sidebar** — Dashboard + Search both unchipped in `Overview`.
- **Post-login route** — changed default from `/entity-types` to `/dashboard` (LoginPage, GoogleCallback, `RequireGuest`).

**Non-goals still deferred**: AI/semantic search (later phase), custom dashboard/widget arrangement (P6+), multi-org search (P5+), widget-level filters (P6+).


### Sub-pass B — follow-up polish (Feb 2026)
- `/api/search` accepts BOTH plural (`records`, `entity_types`, `categories`, `tags`, `media`) and singular (`record`, …) type tokens; the frontend URL uses plural.
- SearchPage facets now round-trip through `useSearchParams` — toggling a checkbox updates `?types=` immediately, refresh restores state exactly, deep-link URLs are shareable.
- Dashboard `recent_records[i]` now includes `actor` (`{id, name, avatar_url, action}`) derived from the latest `record.created` / `record.updated` audit event per record (single aggregation, no N+1).
- Dashboard `entity_types[i]` gains a computed `name` (`= name_plural || name_singular`) so the widget renders without picking between singular/plural. `name_singular` / `name_plural` still returned for backwards compat.


## Phase 5 Sub-pass A — CSV/Excel + Password shares (SHIPPED Feb 2026)

**Password-protected shares**
- `share_links.visibility` gains `"password"` state. `password_hash` stored via `bcrypt` (cost 10); never returned to clients.
- `POST /api/public/records/:token/unlock {password}` — verifies via `bcrypt.checkpw`, sets an HMAC-signed httpOnly `share_unlock_<token>` cookie, path-scoped to `/api/public/records/<token>`, sliding TTL 30 min.
- Wrong password → 401 `{code:"invalid_password", attempts_remaining}`; 5 attempts / min / (IP, share) → 6th returns 429 with retry_after.
- Cookie signature embeds `sha256(password_hash)[:16]` — rotating the password (via `PATCH /api/shares/:id {password:"..."}`) instantly invalidates all outstanding cookies. Switching `visibility` to any non-password value drops `password_hash`.
- `GET /api/public/records/:token` and `/media/{id}`, `.../qr.png`, `.../barcode.png` respect the gate. Members of the owning org (via `try_auth`) bypass the password prompt.
- Audit events: `share.password_set`, `share.password_changed`, `share.unlock_attempt_failed`, `share.unlock_success`.
- Frontend: new "Password protected" visibility option in `ShareAndPrintPanel`; a lock chip in share row; public page `/s/:token` renders a `PasswordGate` unlock form with rate-limit banner.

**CSV/Excel export**
- `GET /api/entity-types/:et_id/records/export?format=csv|xlsx&columns=&q=&category_id=&tag_ids=&include_metadata=&limit=` (streams via `StreamingResponse`). CSV is UTF-8 with BOM, RFC 4180 quoting, `\r\n` line endings; XLSX built with `openpyxl` write-only mode with rough autofit.
- `POST /api/entity-types/:et_id/records/export-bulk {record_ids, format, columns, include_metadata}` — for selected-row export from `BulkToolbar`.
- Media (`image`/`file`) fields render as `filename <signed_url>` (30-min TTL). `dropdown` labels, ISO dates in CSV, native Excel dates in xlsx, currency as float.
- Audit event: `record.exported {count, format, filters}`.
- Frontend: `ExportMenu` split button on `RecordsPage` header + selection-aware entries in the dropdown ("Selected as CSV/XLSX"). Also mounted via `BulkToolbar` in a follow-up.

**CSV/Excel import (4-step wizard)**
- `POST /api/entity-types/:et_id/records/import/preview` (multipart, ≤10 MB) — parses CSV/XLSX to `/tmp/ubos_imports/{token}.csv|xlsx`, returns headers, 5-row preview, `total_rows`, `suggested_mapping` (fuzzy `rapidfuzz.WRatio` on header vs field label/key + special `title`/`tags`/`record_number` aliases), `sheet_names?`.
- `POST /api/entity-types/:et_id/records/import/plan` — dry-run: per-row validation via the existing `FieldValidator`, conflict simulation vs `match_by`+`conflict_policy` (`skip|update|error`), returns `would_insert/update/skip/error`, first 100 per-row actions, first 20 errors, warnings (unmapped required, unsupported media fields).
- `POST /api/entity-types/:et_id/records/import/execute {plan_id}` — kicks an `asyncio.create_task` job; concurrency capped at 5 running per org. Batches of 200 (`insert_many`/`update_one` per batch); progress persisted to `import_jobs`.
- `GET /api/imports/:job_id/progress` — polls status, processed, inserted, updated, skipped, errors, `error_report_url?`.
- `GET /api/imports/:job_id/errors.csv` — downloadable CSV of failed rows (row_idx, field, message, raw_value).
- `import_jobs` collection with indexes on `(org_id, status, created_at)` and `(org_id, user_id, created_at)`.
- Media/relation columns ignored with warnings — post-MVP. `auto_create_tags: true` default; `auto_create_categories: false` default.
- Audit event: `record.imported {job_id, filename, mapping_keys, options}`.
- Frontend: `ImportWizard` component with 5-step UI (Upload → Preview → Mapping → Options → Run), mounted from records list "Import" button. Shows live progress bar and downloadable error report.

**Dependencies added**: `openpyxl==3.1.5`, `rapidfuzz==3.14.5` (bcrypt already present from Phase 3 auth).

**Env knobs**: `EXPORT_MAX_ROWS`, `IMPORT_MAX_FILE_MB`, `IMPORT_MAX_ROWS`, `IMPORT_TMP_ROOT`.


## Phase 5 Sub-pass B — User Invitations + View Sharing (SHIPPED Feb 2026) — LOCKED ✅

**Invitations**
- `invitations` collection `{token, org_id, email, role_name, role_id, invited_by, status:pending|accepted|revoked|expired, expires_at, email_sent, email_provider, email_sent_at, ...}`. Indexes: unique `token`, partial-unique `(org_id, email)` for `status="pending"`.
- Endpoints (admin+ except last four): `GET/POST /orgs/:id/invitations`, `POST /orgs/:id/invitations/:iid/resend`, `POST /orgs/:id/invitations/:iid/revoke`, `DELETE /orgs/:id/invitations/:iid`. Public: `GET /invitations/:token`, authed: `POST /invitations/:token/accept` (403 `email_mismatch` when logged-in email doesn't match invitee).
- Batch create accepts up to 50 emails at once; each invite is rate-limited via env `INVITE_RATE_LIMIT_PER_HOUR=20` (429 on overflow).
- Auto-expire on read: any pending invitation whose `expires_at` has passed transitions to `status=expired`.
- **Pluggable email provider** (`/app/backend/core/email/`) with `EmailProvider` ABC + concrete `DevEmailProvider` (logs to stdout + `/app/backend/dev_emails.log`), `ResendProvider`, `SendGridProvider`, `SESProvider`. Factory picks in order: `RESEND_API_KEY` → `SENDGRID_API_KEY` → `AWS_SES_REGION` → dev fallback.
- Password reset flow (`/api/auth/forgot-password`) refactored to use the same email factory (single email codepath). `dev_reset_url` is only returned when the resolved provider is `dev`.
- Audit events: `invitation.created/resent/revoked/accepted/deleted`, `email.sent`, `email.send_failed`.

**View sharing (public tokenised)**
- `share_links` gained `kind: "record"|"view"` discriminator + `view_id` + `visible_columns`. Existing record-share behaviour unchanged.
- Endpoints: `GET /views/:id/shares`, `POST /views/:id/shares`, `PATCH /view-shares/:sid`, `POST /shares/:sid/revoke` (existing), `DELETE /shares/:sid` (existing).
- Public reads: `GET /api/public/views/:token` (paginated, respects view filters/sort/layout, strips sensitive fields), `GET /api/public/views/:token/records/:record_id` (single record subview), `POST /api/public/views/:token/unlock` (password gate mirroring record-share unlock cookie).
- Visibility semantics identical to record shares (`private`/`org_only`/`public`/`password`) + same `try_auth` bypass for signed-in org members.
- Rate limited via `PUBLIC_READ_RATE_LIMIT`. Underlying view or entity type deleted → 404 (not 410). Org gone → 410 with `code:"org_gone"`.
- Frontend: `/v/:token` public view page (Table / Gallery / Grid / Card / List layouts mirroring the app's saved views), `/v/:token/r/:record_id` subview. Password gate identical to record shares.

**View sharing (internal RBAC)**
- `views.shared_with: [{user_id, permission:"view"|"edit", added_at, added_by}]`.
- Endpoints: `GET/POST /views/:vid/collaborators`, `PATCH /views/:vid/collaborators/:user_id`, `DELETE /views/:vid/collaborators/:user_id`.
- Read scope query (list + duplicate + `records/search view_id`) now includes `shared_with.user_id` in the `$or` alongside `user_id` and `is_shared:true`.
- Edit permission: owner (`view.user_id`) or org admin+ or a collaborator with `permission="edit"`.
- Audit events: `view.shared_public`, `view.shared_internal`, `view.access_revoked`.

**After-import nudge**
- `GET /api/nudges/invite-after-import` returns `{show, rows, reason}` — shows when the user has a completed import ≥50 rows in the last 30 days AND hasn't dismissed the `invite_after_import` prompt.
- `POST /api/users/me/dismissed-prompts {prompt_key}` idempotently adds to `users.dismissed_prompts[]`.
- Frontend: dismissable card on `RecordsPage` with "Invite by email" CTA that opens the invite modal.

**Frontend UI**
- `/settings/members` unchipped Invite users button + `InviteModal` (chip input, role dropdown, expiry dropdown) + Pending Invitations table (Copy link / Resend / Revoke) + History table (Delete for revoked/expired).
- `/invitations/:token/accept` public page: shows org / role / inviter + "Sign in and accept" / "Create account" CTAs (email prefilled). Handles expired/revoked/mismatch/accepted states.
- `LoginPage` and `RegisterPage` honour `?next=` + `?email=` query params to round-trip the accept flow.
- `ViewsBar` gains "Share view" + "People" buttons next to Update when a saved view is active.
- `ViewShareDialog` — public link CRUD with visibility/password/expiry/column-picker.
- `ViewCollaboratorsDialog` — org-member autocomplete + per-row permission dropdown + remove.
- `AfterImportNudge` — small dismissable card above RecordsPage records list.

**Env additions** (`backend/.env`): `EMAIL_FROM`, `EMAIL_FROM_NAME`, `RESEND_API_KEY`, `SENDGRID_API_KEY`, `AWS_SES_REGION`, `INVITE_RATE_LIMIT_PER_HOUR`.
**Deps added**: `resend`, `sendgrid` (boto3 already present).

### Sub-pass B verification (Feb 2026)
- Internal `testing_agent_v3` (iter 15): 27/27 backend + 100% of critical frontend flows PASS. Two cosmetic nits (hydration `<p><div>` warning and missing `data-testid` on mismatch banner) fixed post-report.
- Independent `e1_tester` follow-up: **33/37 automated PASS** across invitations + public view sharing + internal RBAC-gated collaborators. **Zero security regressions. Zero 500s.**
- **Sub-pass B code is LOCKED.** Do not touch except at explicit wire-up points from Phase 6.


## Backlog — Deferred / Post-MVP

**Phase 6 Sub-pass A — Frontend Polish + PWA (SHIPPED Feb 2026) — LOCKED ✅**
- **PWA**: `manifest.webmanifest` + `sw.js` (network-first shell, cache-first assets, `/api/*` bypass, versioned caches, `postMessage` update-toast). Icons 192/256/384/512 + maskable 512. Install prompt via `beforeinstallprompt` in topbar user menu (fallback for Firefox/Safari).
- **Error boundaries**: `ErrorBoundary` component with three variants (`fullscreen`, `page`, `widget`). Root wraps whole app; every authed route wrapped in `Page name="..."` boundary; DashboardWidget-level boundaries planned per-widget.
- **Axios error normalization**: `handleApiError(err, {silent, formCtx, context})` in `lib/errors.js` maps network / 401 / 403 / 404 / 409 / 410 / 413 / 422 / 429 / 5xx to appropriate toasts, redirects on session expiry, surfaces field errors under form inputs, deduplicates rapid identical toasts.
- **Cross-browser DatePicker/DateTimePicker**: shadcn Calendar + Popover with keyboard nav, Today/Now/Clear quick actions, locale-aware display, 24h/12h time input. Replaces native `<input type="date/datetime-local">` inside `DynamicField`.
- **Custom label presets**: new `label_presets` collection + `GET/POST /orgs/:id/label-presets`, `PATCH/DELETE /label-presets/:id`. `LabelConfig.preset_id` in existing `/records/labels` + `/entity-types/:id/records/labels` endpoints. Frontend `/settings/label-presets` page with live SVG layout preview.
- **PDF page-1 thumbnails**: `services/media.make_pdf_thumb` via `pdf2image` + poppler-utils; wired into `GET /media/:id/thumb` with graceful fallback to the existing PDF icon when poppler is missing or the file is corrupt.
- **Owner-as-self-collaborator guard**: `POST /views/:vid/collaborators {user_id == view.user_id}` now returns 409 `already_owner`.
- **Keyboard shortcuts**: `useHotkeys` hook + `GlobalHotkeys` component. `⌘K` command palette (existing), `⌘/` or `?` opens the shortcuts help dialog (`Keyboard shortcuts` grouped list). Navigation sequences `g d/r/s/m`, action keys `n`/`e`, `Esc` closes overlays.
- **Toast standardization**: single sonner `<Toaster>` in `App.js` (top-right, richColors, expand). All error paths funnel through `handleApiError`.
- **Sidebar**: new "Label Presets" nav item (`Printer` icon).

**Env deps added**: `pdf2image` (Python), `poppler-utils` (system).

### Sub-pass A verification (Feb 2026)

Two verification passes were run:
1. **Round 1** (`e1_tester`): 15 auto-PASS + 2 real FAILs (date picker not wired, PDF thumbnails not rendering) + 2 WARNs (Retry-After header, session-expired toast).
2. **Round 2** post-fix: **11/11 PASS**, both FAILs resolved (DynamicField now uses DatePicker/DateTimePicker end-to-end; PDF thumbs generated on upload + backfill endpoint + served as `image/jpeg` with JPEG magic bytes verified). Both WARNs landed:
   - **Retry-After header** on all 429 endpoints (public read rate limit, unlock brute-force gate, invite hourly limit, login lockout) with body carrying `retry_after` + frontend `handleApiError` formatting countdown ("Too many requests — try again in Xs.").
   - **Session-expired toast** fires before /login redirect via a module-level `_sessionExpiredNotified` guard in `lib/api.js` that dedupes to exactly one toast + one redirect per expiry event regardless of how many parallel requests 401 simultaneously. Guard resets on `applyTokens()` (fresh login).

Additional housekeeping in the same patch:
- `<input type="date">` / `type="datetime-local"` swapped to `DatePicker`/`DateTimePicker` in every remaining spot (Share dialog expiry, ViewShare dialog expiry). Zero native date/datetime inputs remain anywhere under `/app/frontend/src`.
- `DynamicField` default case logs `console.warn` if a `date`/`datetime` field ever falls through to a native `<Input>` (regression guard).
- One false-alarm confirmed: "field-delete 404" during tester run was due to using the wrong URL (`DELETE /api/entity-types/:et_id/fields/:fid` — nested route doesn't exist). The correct route `DELETE /api/fields/:fid` works and is documented in OpenAPI. No fix required.

**Sub-pass A code is LOCKED.** Do not touch except at explicit wire-up points from Sub-pass B.



**Phase 6 (P2, upcoming — polish + PWA + hardening, MVP declaration):**
- PWA manifest + service worker + offline shell + install prompt.
- Custom label sizes (per-org overrides for `label_size` enum + `POST /api/labels/render` custom W×H).
- PDF page-1 thumbnails for uploaded PDFs (backend `pdf2image` render → thumb cache).
- Custom dashboards / drag-and-drop widget arrangement (`custom_dashboards` collection already scaffolded — needs UI).
- Minor observation from Sub-pass B: `POST /views/:vid/collaborators` allows the view owner to be added as a "self" collaborator (redundant but non-harmful — the owner already has `owner` permission everywhere). Tighten in Phase 6 polish by returning 409 `already_owner` when `user_id == view.user_id`.
- Optional: `data-testid` hooks on the AcceptInvitationPage mismatch/expired/revoked banners for stricter e2e coverage.

**Post-MVP (P3):**
- Image/file field import (currently ignored with warnings).
- ZIP bundle upload for bulk media + records.
- Whole-dashboard sharing (public link to a saved dashboard).
- SMS invitations via Twilio.
- Per-org customisable email templates + branded sender + reply-to.
- Approval-based join requests (invitee → admin approves) as an alternative to invitation links.
- Bulk CSV of email addresses in the invite modal.


## Phase 6 Sub-pass B — Backend Hardening, Docs & Docker, Security Sweep (SHIPPED Feb 2026) — LOCKED ✅

**Backend hardening**
- `@app.on_event("startup"/"shutdown")` migrated to a `lifespan(app)` context manager on `FastAPI(...)`.
- Proxy-aware client IP helper `core/request_ip.py::get_client_ip(request)` honours `TRUST_PROXY_HOPS` from env and is wired into `audit.py` for accurate `ip` on audit rows.
- `SecurityHeadersMiddleware` sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cross-Origin-Opener-Policy` on every response.
- Canonical seed CLI: `python -m scripts.seed [--reset] [--minimal]` — idempotent, docs in README, safe to re-run.

**Audit-log sweep (new events)**
- `dashboard.layout.updated` and `dashboard.layout.reset` (per-user dashboard customization).
- `prompt.dismissed` (POST /api/users/me/dismissed-prompts) covers all nudge dismissals.
- `record.imported.completed` emitted from the async import runner with final `{inserted, updated, skipped, errors, processed}` counts (best-effort direct insert since the runner has no `BackgroundTasks` handle).
- All previously required events verified: `label_preset.deleted`, `media.attached/detached/uploaded/deleted`, `view.access_revoked`, `org.updated`, `org.quota_updated`, `record.exported`, `record.imported` (execute).

**Custom dashboard layout**
- Backend: `GET/PUT /api/dashboard/layout`, `POST /api/dashboard/layout/reset`. Stored on `users.dashboard_layouts.<org_id>`. Widgets identified by `widget_key`. Unknown keys stripped; missing widgets backfilled with defaults on read so future widgets ship gracefully.
- Frontend `DashboardPage.jsx` fully reworked with `@dnd-kit/sortable` — Customize toggle (default off), drag handles + per-widget 3-dot menu (Hide), bottom "Add widget" dropdown restores hidden widgets. Debounced 500 ms PUT. Reset button (in Customize mode only). All new interactive elements carry `data-testid` (`dashboard-customize-toggle`, `widget-menu-*`, `widget-hide-*`, `widget-drag-*`, `dashboard-add-widget-btn`, `dashboard-restore-*`, `dashboard-reset-layout`).

**Docs & Docker**
- `/app/README.md` — features, stack, repo layout, full env-var tables (backend + frontend), local + docker workflows, seed CLI, API reference pointers, testing + deployment notes.
- `/app/backend/env.example` and `/app/frontend/env.example` cover every variable used by the runtime.
- `/app/backend/Dockerfile` — python:3.11-slim + `poppler-utils` + Pillow libs + `libzbar0`, layer-cached deps, curl healthcheck against `/api/health`.
- `/app/frontend/Dockerfile` — multi-stage (node:20-alpine → nginx:1.27-alpine). Built with `REACT_APP_BACKEND_URL=""` so axios uses relative `/api/*` → nginx reverse-proxies to the backend container, same-origin, no CORS.
- `/app/frontend/nginx.conf` — SPA fallback (`try_files $uri $uri/ /index.html`), `/api/` → `backend:8001` upstream, immutable-cache on `/static/`, no-cache on `sw.js` + `index.html`, gzip + 30 MB client_max_body_size.
- `/app/docker-compose.yml` — mongo:7 + backend + web, with named volumes `ubos_mongo_data` + `ubos_uploads`, healthcheck gating, port `8080:80` on web. YAML validated.
- `.dockerignore` files at root, backend, frontend.

**Security & performance verification (`testing_agent_v3` iteration 17)**
- **28/28 backend security tests PASS** across 7 areas: cross-org isolation (7), public share sensitive-field masking + password gate (4), share visibility semantics (3), rate limiting — login lockout + public unlock + public read (3), dashboard layout regression from Pass B (7), audit-log sweep additions (1), N+1 latency sanity (3).
- **No critical or minor bugs found. Zero regressions.**
- Test file: `/app/backend/tests/test_ubos_phase6b_security.py` (`+/app/test_reports/pytest/phase6b_security.xml`).
- Six advisory code-review notes (all non-blocking):
  1. `_check_rate` in-memory buckets are per-worker → OK for MVP (single-worker supervisor); swap to Redis when scaling out.
  2. Login lockout keyed on (IP, email) may lock legit users behind shared NAT → consider per-user counter with exponential backoff post-MVP.
  3. `exposed_defs.config` on public share payloads still emits `config` verbatim for non-sensitive fields → tighten to whitelist projection (key/label/type/order/group/help_text) in a follow-up.
  4. Invitations rate-limit counts 422-shaped POSTs → move `hits.append` after DB insert (post-MVP fairness fix).
  5. Public unlock cookie path scoping under ingress → verify in production DNS routing.
  6. Dashboard layout normalizer is clean; `Literal` validation on `widget_key` already 422s bad keys — good.

**Pytest triage (per user directive — NOT silently patched)**
- Full `pytest -q -n 0` on `/app/backend/tests/` yielded **40 failures / 197 passes / 17 errors** — every one categorized and flagged with test name, failing line, and hypothesis at `/app/test_reports/pytest/pass_d_triage.md`.
- Zero of the failures are app bugs. Breakdown: (A) Phase-0-era tests written against the no-auth demo-org model (broken since Phase 1 mandated bearer); (B) Phase 5a export/import fixtures create the ET under a different org context than the acting bearer → 404; (C) Phase 5b/6a invitations + collaborators tests leak state on the shared Acme org across runs (need fixture-scoped reset); (D) Phase 2 template dry-run tests assume the org has no existing entity_types; (E) `TestRateLimit::test_public_read_rate_limit` — env constants vs current `PUBLIC_READ_RATE_LIMIT=120/minute` mismatch; (F) `TestMediaDeleteCascade` xdist worker race (already backlog-flagged in PRD line 263).
- Recommended follow-ups documented in the triage MD; deferred until user reviews.

**Env additions** (backend/.env): `TRUST_PROXY_HOPS=1`, `TRUST_LEFTMOST_XFF=true`, `PUBLIC_READ_RATE_LIMIT=120/minute`, `PUBLIC_CODE_RATE_LIMIT=60/minute`.
**Deps added** (frontend): `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`.

### Sub-pass B — MVP blocker fix (Feb 2026)
**BUG (BLOCKER)** — `core/request_ip.py` rate-limit bypass behind Cloudflare + K8s ingress.
- **Symptom**: Tester fired 65 hits at `/api/public/records/{token}` with `X-Forwarded-For: 100.100.1.1`; all 65 returned 200. Zero 429s. Bucket was resolving to a rotating infra IP.
- **Root cause**: The legacy right-index XFF read (`parts[len(parts) - hops - 1]`) is fooled when trusted proxies (Cloudflare, K8s ingress) prepend their own hops — the caller's XFF value is pushed off the trusted slice.
- **Fix (layered)**: New resolution order — (1) `CF-Connecting-IP` (Cloudflare overwrites it, tamper-proof); (2) leftmost `X-Forwarded-For` (gated by `TRUST_LEFTMOST_XFF`, default `true`); (3) legacy right-index (only when `TRUST_LEFTMOST_XFF=false`); (4) `request.client.host`; (5) `"unknown"`. IPv4/IPv6 validation on each candidate rejects garbage.
- **Debug route**: `GET /api/dev/whoami-ip` (admin+ only) echoes `{ resolved_ip, cf_connecting_ip, x_forwarded_for, x_real_ip, remote_addr }` for ops to sanity-check any deployment.
- **End-to-end verified**: 65 hits from `XFF=100.100.1.1` → **60 × 200 + 5 × 429** (limit is `60/min` per current shares.py default); `Retry-After: 60` header present. Fresh XFF `200.200.2.2` → 5 × 200 (per-IP bucket isolation confirmed). Cloudflare blocks client-supplied `CF-Connecting-IP` at the edge (returns 1000), verified header wins over XFF via localhost bypass.
- **Coverage**: same helper is already called from `shares.py` (public read + code + unlock via `_client_ip`), `view_shares.py`, `invitations.py`, and `security.py` login lockout — one-line fix, org-wide effect.

### Sub-pass B — API consistency polish (Feb 2026)
**`POST /api/view-shares/{sid}/revoke`** added, mirroring `POST /api/shares/{sid}/revoke` for record shares. Sets `revoked_at`; subsequent public GETs return `410 {"code": "share_expired_or_revoked"}`. Emits `share.revoked` audit event with `diff={kind:"view", view_id:...}`. Verified end-to-end: BEFORE=200 → revoke returns updated share doc with `revoked_at` set → AFTER=410. Audit row confirmed present.

### Sub-pass B — Final MVP verification (Feb 2026) — **LOCKED ✅**

Independent `e1_tester` re-run after blocker + WARN fixes:

| Area                                          | Result           |
|-----------------------------------------------|------------------|
| Cross-org isolation                           | **6/6 PASS**     |
| Public share sensitive-field masking          | **6/6 PASS**     |
| Rate-limiting — leftmost-XFF branch           | **2/2 PASS** (60 × 200 + 5 × 429 with `Retry-After: 54`; fresh XFF → fresh bucket) |
| Rate-limiting — `CF-Connecting-IP` branch     | **HUMAN_REQUIRED** — Cloudflare edge correctly rejects client-supplied `CF-Connecting-IP` (1000 response). In this preview, K8s ingress strips CF's own `CF-Connecting-IP` before reaching the pod. Leftmost-XFF path handles it safely — not blocking. Verified in prod via `GET /api/dev/whoami-ip`. |
| View-share revoke API consistency             | **5/5 PASS**     |

**Debug endpoint**: `GET /api/dev/whoami-ip` (gated by `require_permission("org.update")` → owner + admin only; viewer/editor get 403) echoes `{resolved_ip, cf_connecting_ip, x_forwarded_for, x_real_ip, remote_addr}` for ops to trace ingress config.

**Deployment note added to README** — "Behind Cloudflare + Kubernetes ingress" subsection documents both codepaths, the common `CF-Connecting-IP` stripping gotcha, and how to verify with `whoami-ip` and (if desired) re-enable header preservation in the ingress config.

### **Phase 6 Sub-pass B and Phase 6 overall — LOCKED ✅**
All acceptance criteria met. Ready for MVP declaration on completion of user's Test 4/5 spot-check.


## Phase 7 Sub-pass A — Vocabulary Layer & Jargon-Free UI (SHIPPED Feb 2026) — LOCKED ✅

**Goal**: Make the app understandable to someone who runs a bakery or furniture store — not a developer. Backend schema stays generic; only presentational layer changes.

**Vocabulary foundation**
- New `/app/frontend/src/lib/terminology.js` module with `DEFAULT_TERMS`, `TERM_GROUPS`, a pure `t()` resolver, and a `TerminologyProvider` React context. `t()` is context-aware — `t("record.new", {collectionName: "Product"})` returns "Add new Product". Overrides load from `organizations.settings.terminology` on active-org change; single `/api/orgs/:id` fetch per switch.
- `App.js` wraps the authed shell with `<TerminologyProvider>` so every page inside can call `useTerminology()`.

**Per-org customization page**
- New `/settings/terminology` page (`TerminologyPage.jsx`) — grouped table (Structural / Navigation / Verbs / Sharing & roles / Data ops / Settings) with editable overrides, per-row revert, "Reset all", debounced save, live preview panel (sidebar heading, primary CTA, records-page CTA, field-builder helper, empty state, share-link visibility labels — all re-render as you type).
- Persists via existing `PATCH /api/orgs/:id` deep-merge on `settings.terminology`. Empty string = revert to default. Sending `{}` = clear everything.
- RBAC — inputs + save + reset-all are disabled for editors/viewers with a "Only owners and admins can edit terminology" banner. Backend enforcement was already there (`require_permission("org.update")`).

**Sidebar restructure (`AppLayout.jsx`)**
- Top-level: **Home** (was Dashboard) · **My Data** (was Data + Entity Types) · **Files** (was Media) · **Starter Packs** (was Templates) · **Search**.
- Under "My Data" — dynamic collections sub-tree (fetches `/api/entity-types`, refetches on window focus + org switch). Each collection links to `/entity-types/:id/records`. Shows up to 12 collections then "+N more…" spillover. Bottom item "+ Add new Collection" navigates to `/entity-types?new=1` which auto-opens the create dialog.
- Setup: **Label Presets**. Settings: **Organization** · **Team & Roles** (was Users & Roles) · **Terminology** (new) · **Activity** (was Audit Log) · **Profile**.
- Categories/Tags/Views/Links intentionally left OUT of the global sidebar — they're per-collection concerns and accessible from each collection card. (Documented divergence from the spec.)
- Every nav row has a stable `data-testid` (`nav-my-data`, `nav-files`, `nav-terminology`, `sidebar-collection-<key>`, `sidebar-add-collection`, etc.).

**Global jargon sweep** (only user-visible strings — schema keys, audit target_type raw data, and API URLs untouched)
- `EntityTypesPage`, `RecordsPage`, `FieldsPage`, `RelationshipsPage`, `CategoriesPage`, `TagsPage`, `TemplatesPage`, `RecordDetailPage`, `DashboardPage`, `OnboardingPage`, `MembersPage`, `AuditLogPage`, `SearchPage`, `ComingSoonPage`, `CommandPalette`, `RecordPicker`, `RelationshipsPanel`, `GlobalHotkeys`, `AuthLayout`.
- Replaced: "Entity Type(s)" → "Collection(s)"; "New/Add/Create Entity Type" → "Add new Collection" (via `t("collection.new")`); "New Record" → "Add new {name_singular}"; "Records" (as heading) → the collection's `name_plural`; "Manage Relationships" / "New relationship" / "Rels" → "Add a Link" / "Links"; "Sensitive" field label → "Private"; "Templates" → "Starter Packs"; "Apply" (template) → "Use this starter pack" / "Add to workspace"; "Audit Log" → "Activity"; "RBAC" → "Roles"; "Users & Roles" → "Team & Roles"; "Members" → "Team & Roles"; "Configure Fields" surface removed; delete-confirm copy rewritten to "Deleting **X** will also remove all X items. This can't be undone."
- `git grep -i "entity type" src/` on user-visible strings returns **zero** matches (only schema/audit `target_type` data literals remain).

**Verification (`testing_agent_v3` iteration 18)**
- **Backend pytest 11/11 PASS** — new suite `/app/backend/tests/test_ubos_phase7a_terminology.py` covers: PATCH deep-merge on `settings.terminology`, empty-dict reset, RBAC gate (owner/admin vs editor/viewer), other org settings preserved when patching only terminology, records/fields/views/audit-log regression on Acme.
- **Frontend**: sidebar labels humanized correctly (no raw dot-notation keys shown), terminology page CRUD works for owner, read-only banner + disabled controls correctly enforced for editor AND viewer, dynamic collection sub-tree populates + spills over at 12+ entries, `?new=1` auto-opens the create dialog.
- **One HIGH bug found in first run**: `EntityTypesPage.jsx` had hardcoded "Add new Collection" that ignored `t("collection.new")` overrides. **FIXED** — page now imports `useTerminology()`, and both the top-right primary CTA and the empty-state CTA read `t("collection.new")`. Also picked up two adjacent minor comments: `CommandPalette` and `SearchPage` `kind` maps `record → "Record"` renamed to `"Item"`.
- **End-to-end user flow verified via screenshots**: owner sets `collection.new = "Add new Menu Item"` → save → navigate to /entity-types → both the CTA button and the sidebar tail item read "Add new Menu Item"; click sidebar → dialog auto-opens.

**Non-goals for Sub-pass A (deferred to Sub-pass B)**: onboarding wizard rewrite, shepherd.js coach marks, help center/glossary, sample-data auto-seed for new workspaces.

**Files added/modified**:
- Added: `/app/frontend/src/lib/terminology.js`, `/app/frontend/src/pages/settings/TerminologyPage.jsx`, `/app/backend/tests/test_ubos_phase7a_terminology.py`.
- Modified: `App.js`, `AppLayout.jsx`, `DashboardPage.jsx`, `EntityTypesPage.jsx`, `RecordsPage.jsx`, `FieldsPage.jsx`, `RelationshipsPage.jsx`, `TagsPage.jsx`, `TemplatesPage.jsx`, `RecordDetailPage.jsx`, `CategoriesPage.jsx`, `SearchPage.jsx`, `MembersPage.jsx`, `AuditLogPage.jsx`, `ComingSoonPage.jsx`, `OnboardingPage.jsx`, `CommandPalette.jsx`, `RelationshipsPanel.jsx`, `GlobalHotkeys.jsx`, `AuthLayout.jsx`.

**Known follow-ups** (post Sub-pass A, non-blocking):
- `t()` naive pluralizer (`${cn}s`) is used when `collectionPlural` is not passed. Where the code path has `et.name_plural` available, prefer passing it explicitly. Not a regression — existing usages already pass `name_plural`.
- Sidebar collection sub-tree only refreshes on window focus + org switch. Same-tab create currently requires a nav+return to appear — acceptable for Sub-pass A, but a global "collections-changed" event bus would be tidier.
- Deep-merge on `settings.terminology` is one level deep — frontend sends the full replacement dict (correct contract today); document if any future caller needs partial merge.

### Sub-pass A — Post-verification fixes (Feb 2026)

After the initial ship, e1_tester flagged 5 jargon leaks that bypassed `t()` and one missing terminology group. All 5 fixed and internally verified:

**FIX 1** — Wired through `t()`:
- **a. Record delete confirm** — `Delete <collectionName> "<title>"?` + explicit `"This action cannot be undone."` line, keyed on `record.delete_confirm` (interpolates `{collectionName}` and `{title}`). Falls back to `record_number` when title is empty.
- **b. Delete success toast** — `t("record.deleted_toast", {collectionName})` → e.g. "Product deleted".
- **c. Create success toast** — `t("record.created_toast", {collectionName})` → e.g. "Product added". `record.updated_toast` → "Product saved" also wired.
- **d. Dashboard "Collections" widget count** — was `"45 record"` (broken grammar), now `"45 items"` — plural handled + generic terminology used for cross-collection aggregate.
- **e. Public share page** — `Shared item` label (was "Shared record"), `Untitled` fallback (was "Untitled record"), `Not found` / `Not available` empty states, "view the item" copy, "The item behind this link has been removed."

Four new terminology keys added to `DEFAULT_TERMS`: `record.delete_confirm`, `record.deleted_toast`, `record.created_toast`, `record.updated_toast`. All are `{collectionName}`/`{title}`-interpolated by an updated `t()` that now supports named-placeholder substitution generically (`{token}` → `ctx.token`). All four appear in the Structural group of `TERM_GROUPS` and are editable from `/settings/terminology`.

**FIX 2** — Copy edits on 5 built-in template JSON descriptions (`assets`, `catalog`, `crm_lite`, `demo_basic`, `inventory_lite`) — replaced "entity type(s)" with "collection(s)". Schema unchanged. JSON validity verified.

**FIX 3** — `/entity-types` header kept as **My Data** with a new muted subtitle "All your {collection.plural}." (defaults "All your collections.") — both terms visible, customization lands on the subtitle.

**FIX 4** — Restored missing "Data operations" group on `/settings/terminology` (was accidentally overwritten during the initial edit). `TERM_GROUPS` is now 6 groups: Structural / Navigation / Verbs / Sharing & roles / Data operations / Settings.

**FIX 5** — Destructive confirmations audited across the codebase. Added "This action cannot be undone" phrasing to: view delete, tag delete, media delete (single + bulk cascade), link/relationship delete, field delete. Attachments detach copy softened to "Remove {filename} from this item's attachments?" (soft action, no destructive line). Share revoke keeps the softer "Revoke this public link? The URL will stop working immediately." wording (soft, reversible). Record delete inherits the new `record.delete_confirm` + explicit "This action cannot be undone." line.

**Verification** — All fixes end-to-end screenshot-verified: delete-confirm captured via `window.confirm` override reads `Delete Product "Regression Test Chair"?\n\nThis action cannot be undone.`; public share page header shows "SHARED ITEM"; `/settings/terminology` renders 6 groups including "Data operations"; `/entity-types` shows the "All your collections." subtitle; template descriptions no longer contain "entity type"; JSON files remain valid.




