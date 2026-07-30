# Design plan — Reusable library (Fields, Categories, Tags) + custom field types

Status: **proposal, awaiting sign-off** · Covers backlog items 1, 2, 3, 7.

## 1. Goal (from requirements)

- **Item 3** — Categories, Fields, and Tags are **created once, separately**, and can be attached to **any** catalogue (today each catalogue rebuilds its own).
- **Item 2** — Catalogues stay **independent**: adding/removing an item, a field, a category, or a tag in one catalogue must not change another.
- **Item 1** — Users can **define their own field types** (e.g. `GSM`, `CMS`) — a named type with a base kind + unit — instead of only the built-in list.
- **Item 7** — On a choice field (e.g. **End Use**), users **upload an icon per value**; icons print on the tag, toggled on/off in the Print dialog.

## 2. Current state (verified in code + DB)

`field_definitions`, `categories`, and `tags` all carry a single `entity_type_id` — they belong to exactly one catalogue. Record values are stored keyed by field `key`. There is no org-level library of any of these.

## 3. Proposed model

Introduce **org-level library collections** and **attach** them to catalogues. Two candidate semantics — this is the main decision:

| | **A — Shared/linked (recommended)** | **B — Copy on attach** |
|---|---|---|
| Library holds the definition | Catalogue stores a reference (`field_id`) + per-catalogue overrides (order, required) | Attaching copies the field into the catalogue |
| Edit a library field | Updates everywhere it's used | No effect on already-attached catalogues |
| Remove from a catalogue | Detaches there only; library + other catalogues untouched (satisfies item 2) | Deletes the local copy only |
| Matches "create once, use anywhere" | ✅ strongest | partial (drifts over time) |

New collections:
- `field_library` — `{org_id, key, label, type, config, help_text, unit, field_type_id?}`
- `category_library` — org-level category tree (drop `entity_type_id`, keep parent/path)
- `tag_library` — org-level tags (drop `entity_type_id`)
- Attachments on the catalogue: `entity_types.field_ids[]`, `category_ids[]`, `tag_ids[]` (with optional per-attachment overrides for fields: `order`, `required`).

**Key rule (important):** a field's `key` is shared across catalogues, so `gsm` means the same thing everywhere — which is exactly what makes one import/label/search config work for all catalogues. Record data stays per-catalogue (unchanged).

## 4. Custom field types (item 1)

New `field_types` (org-level): `{org_id, name, base_type, unit, default_config}`.
- e.g. `GSM` = `{ base_type: "number", unit: "GSM" }`; `CMS` = `{ base_type: "number", unit: "CMS" }`.
- The field-creation "Type" picker lists built-ins **plus** the org's custom types.
- Picking a custom type prefills base kind + unit; the unit renders next to the value in forms, tables, detail, and labels (e.g. `250 GSM`).

## 5. End Use icons (item 7)

- For `dropdown`/`multi_select` fields, extend option config to `{ value, icon_media_id }`.
- Icons are uploaded via the existing media system (`POST /api/media/upload`) and referenced per option.
- Label renderer (`services/labels.py`, ReportLab) draws the icons for the record's selected values.
- Print dialog gains a **"Show icons"** toggle (default off, per item 8's spirit); a new label config flag `show_value_icons`.

## 6. Migration (existing demo + real data)

One idempotent script:
1. For each distinct field `key` per org, create a `field_library` entry (merge identical keys; log conflicts where the same key has different types).
2. Populate `entity_types.field_ids[]` from existing `field_definitions` (preserving order/required as overrides).
3. Collapse `categories`/`tags` to org-level `*_library`, de-duplicating by name; map old ids → new and rewrite `records.category_ids/tag_ids`.
4. Keep old collections read-only for one release as a rollback net.
Record `fields{}` data is untouched (still keyed by `key`).

## 7. API surface (new/changed)

- `GET/POST /api/field-library`, `PATCH/DELETE /api/field-library/{id}`
- `GET/POST /api/field-types`, `PATCH/DELETE …`
- `GET/POST /api/category-library`, `/api/tag-library`
- `POST /api/entity-types/{id}/attach-fields` `{field_ids}` / `detach` ; same for categories/tags
- Existing per-catalogue field/category/tag routes become thin wrappers over attach/detach for backward compatibility.

## 8. Frontend

- New **Library** area (sidebar → "Library"): manage Fields, Field Types, Categories, Tags once.
- Catalogue **Fields** page becomes an **attach/compose** screen: pick from library, set order (drag — already built), mark required; "＋ New field" still allowed and auto-adds to the library.
- Field-type picker shows custom types; unit rendering in `DynamicField`, table cells, detail.
- Dropdown option editor gains per-option **icon upload**.
- Print dialog gains **Show icons** toggle.

## 9. Phasing (each independently shippable)

1. **Field library + attach model** (items 2, 3 for fields) + migration.
2. **Custom field types + units** (item 1).
3. **Category & Tag libraries** (items 2, 3 for cats/tags).
4. **End Use icon upload + label rendering + print toggle** (item 7).

## 10. Decisions — LOCKED (2026-07-31)

1. **Field semantics → A (shared/linked).** Library holds the field; catalogues reference it; editing the library field updates every catalogue using it; removing from a catalogue only detaches it there.
2. **Categories & Tags → fully global.** Every category/tag is available in every catalogue automatically — no per-catalogue attach. `entity_type_id` is dropped from both.
3. **Units → suffix** (`250 GSM`). Prefix deferred.
4. **Migration → run on the local DB now** as part of the build (merge field keys, collapse cats/tags to global, rewrite record references; keep old collections read-only as rollback net).

### Resulting model
- **Fields**: `field_library` (org-level) + `entity_types.field_ids[]` ordered attachment. Shared/linked. `GET /entity-types/{id}/fields` keeps its existing response shape (resolves attachments → library fields) so records/labels/import/DynamicField keep working unchanged. `DELETE /fields/{id}` = detach from this catalogue; editing patches the library field.
- **Categories & Tags**: become org-level (`entity_type_id` removed); every catalogue sees all.
- **Record data** (`records.fields{}`, keyed by `key`) is untouched.
