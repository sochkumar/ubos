"""Full-workspace export / import — a portable `.ubos` bundle.

Distinct from the per-collection CSV/XLSX import/export: this moves an entire
org's dataset (all collections + media files) between two independent installs
(e.g. the desktop app on two machines). See docs/windows-installer-plan.md.

Bundle = ZIP with:
    manifest.json                 {product, app_version, source_org_id, exported_at, counts}
    collections/<name>.json       array of docs (org-scoped)
    media/<storage_key>           the actual media file bytes

Import remaps every doc's org_id to the importing user's org (installs have
different org ids). `_id`s are UUIDs and are preserved, so intra-bundle
references (entity_type_id, library_id, category_ids, tag_ids, …) stay valid.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import Response

from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from core.storage.factory import get_storage_adapter

router = APIRouter(prefix="/workspace", tags=["workspace"])

# Collections that make up a shareable workspace (auth/tenant collections are
# intentionally excluded — the importing install keeps its own users/org).
COLLECTIONS = [
    "entity_types", "field_definitions", "field_library", "custom_field_types",
    "categories", "tags", "records", "relationship_definitions",
    "relationship_instances", "views", "label_presets", "dashboard_layouts",
]

APP_VERSION = "0.2.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/export")
async def export_workspace(ctx: AuthContext = Depends(require_permission("records.read"))):
    db = get_db()
    adapter = get_storage_adapter()
    counts: dict[str, int] = {}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for coll in COLLECTIONS:
            docs = await db[coll].find({"org_id": ctx.org_id}).to_list(100000)
            counts[coll] = len(docs)
            zf.writestr(f"collections/{coll}.json", json.dumps(docs, default=str))

        # media: metadata is exported via the `media` collection JSON; here we
        # add the actual files. Store under media/<storage_key>.
        media_docs = await db.media.find({"org_id": ctx.org_id}).to_list(100000)
        counts["media"] = len(media_docs)
        zf.writestr("collections/media.json", json.dumps(media_docs, default=str))
        media_files = 0
        for m in media_docs:
            key = m.get("storage_key")
            if not key:
                continue
            try:
                data = await adapter.read_all(key)
                zf.writestr(f"media/{key}", data)
                media_files += 1
            except Exception:
                continue  # tolerate a missing file rather than fail the whole export
        counts["media_files"] = media_files

        manifest = {
            "product": "ubos",
            "app_version": APP_VERSION,
            "bundle_version": 1,
            "source_org_id": ctx.org_id,
            "exported_at": _now(),
            "counts": counts,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    data = buf.getvalue()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    fn = f"ubos-workspace-{ts}.ubos"
    return Response(
        content=data, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.post("/import")
async def import_workspace(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Query(default="replace", pattern="^(replace)$"),
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    """Import a `.ubos` bundle into the current org.

    mode=replace : wipe this org's data in the bundled collections, then load.
    (merge mode is planned next — see the plan doc.)
    """
    db = get_db()
    adapter = get_storage_adapter()
    raw = await file.read()
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(422, "not a valid .ubos bundle (bad zip)")

    names = set(zf.namelist())
    if "manifest.json" not in names:
        raise HTTPException(422, "bundle is missing manifest.json")
    manifest = json.loads(zf.read("manifest.json"))
    if manifest.get("product") != "ubos":
        raise HTTPException(422, "not a UBOS workspace bundle")

    target_org = ctx.org_id
    summary: dict[str, int] = {}

    # ── Replace: hard-delete this org's data in the bundled collections. ──
    all_colls = COLLECTIONS + ["media"]
    for coll in all_colls:
        await db[coll].delete_many({"org_id": target_org})

    # ── Load each collection, remapping org_id to the target org. ──
    for coll in all_colls:
        entry = f"collections/{coll}.json"
        if entry not in names:
            continue
        docs = json.loads(zf.read(entry))
        if not docs:
            summary[coll] = 0
            continue
        for d in docs:
            d["org_id"] = target_org
        await db[coll].insert_many(docs)
        summary[coll] = len(docs)

    # ── Media files: write bytes back into local storage at their key. ──
    media_written = 0
    for name in names:
        if not name.startswith("media/") or name.endswith("/"):
            continue
        key = name[len("media/"):]
        try:
            await adapter.put_bytes_at_key(key, zf.read(name))
            media_written += 1
        except Exception:
            continue
    summary["media_files"] = media_written

    return {
        "ok": True, "mode": mode,
        "source_org_id": manifest.get("source_org_id"),
        "imported": summary,
    }
