"""Printable label PDF endpoints."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from services.labels import PRESETS, preset_from_custom_doc, preset_summary, render_labels_pdf

router = APIRouter(tags=["labels"])


async def _resolve_preset_for_config(db, org_id: str, config_data: dict) -> dict:
    """Resolve `preset_id` → custom preset dict OR validate built-in `preset`.
    Mutates `config_data` in-place: injects `_custom_preset` if custom."""
    pid = config_data.get("preset_id")
    if pid:
        doc = await db.label_presets.find_one({
            "_id": pid, "org_id": org_id, "deleted_at": None,
        })
        if not doc:
            raise HTTPException(404, {
                "code": "preset_not_found",
                "detail": "Custom label preset was not found or has been deleted.",
            })
        config_data["_custom_preset"] = preset_from_custom_doc(doc)
        config_data["preset"] = doc.get("key", "custom")
        return config_data
    key = config_data.get("preset", "avery_5160")
    if key not in PRESETS:
        raise HTTPException(422, {
            "code": "unknown_preset",
            "detail": f"Preset '{key}' is not a built-in preset. Pass preset_id for custom.",
        })
    return config_data


def _public_base() -> str:
    return (os.environ.get("PUBLIC_APP_URL") or os.environ.get("APP_BASE_URL") or "").rstrip("/")


class LabelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    preset: str = "avery_5160"
    preset_id: str | None = None   # references a `label_presets` doc (Phase 6-A)
    code_mode: Literal["qr_and_barcode", "qr_only", "barcode_only", "none"] = "qr_and_barcode"
    show_title: bool = True
    show_record_number: bool = True
    show_fields: list[str] = Field(default_factory=list)
    # When true, render the per-value icons of any choice field that has
    # `config.option_icons` (e.g. End Use → curtain / blind / upholstery).
    show_value_icons: bool = False
    copies_per_record: int = Field(default=1, ge=1, le=100)
    start_position: int = Field(default=0, ge=0)


class RecordsLabelsBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    record_ids: list[str] = Field(min_length=1, max_length=500)
    config: LabelConfig = Field(default_factory=LabelConfig)


class ViewLabelsBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    view_id: str | None = None
    filters: list[dict] = Field(default_factory=list)
    q: str | None = None
    category_id: str | None = None
    tag_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=200, ge=1, le=200)
    config: LabelConfig = Field(default_factory=LabelConfig)


async def _hydrate_records_with_qr(db, org_id: str, record_ids: list[str]) -> list[dict]:
    records = await db.records.find(
        tenant_filter(org_id, {"_id": {"$in": record_ids}}),
    ).to_list(500)
    # For each, find an active public share; else use qr_payload.
    base = _public_base()
    shares = await db.share_links.find({
        "org_id": org_id, "record_id": {"$in": record_ids},
        "visibility": "public", "revoked_at": None,
    }).to_list(2000)
    share_by_rec = {}
    now = datetime.now(timezone.utc)
    for s in shares:
        exp = s.get("expires_at")
        if exp:
            try:
                if datetime.fromisoformat(str(exp).replace("Z", "+00:00")) < now:
                    continue
            except Exception:
                pass
        share_by_rec.setdefault(s["record_id"], s)
    out = []
    id_order = {rid: i for i, rid in enumerate(record_ids)}
    for r in records:
        s = share_by_rec.get(r["_id"])
        if s:
            r["_qr_text"] = f"{base}/s/{s['token']}" if base else f"/s/{s['token']}"
        else:
            r["_qr_text"] = r.get("qr_payload") or (f"{base}/r/{r['_id']}" if base else f"/r/{r['_id']}")
        r["id"] = r["_id"]
        out.append(r)
    out.sort(key=lambda x: id_order.get(x["_id"], 9999))
    return out


async def _prepare_value_icons(db, org_id: str, records: list[dict], cfg: dict) -> None:
    """When show_value_icons is on, resolve each record's choice-field values to
    their mapped icon images and stash them on cfg for the sync renderer.

    Populates:
      cfg["_value_icons"] = {field_key: {value: media_id}}
      cfg["_icon_pngs"]   = {media_id: png_bytes}
    """
    if not cfg.get("show_value_icons"):
        return
    et_ids = list({r.get("entity_type_id") for r in records if r.get("entity_type_id")})
    if not et_ids:
        return
    fds = await db.field_definitions.find(
        tenant_filter(org_id, {"entity_type_id": {"$in": et_ids}}),
    ).to_list(2000)
    # field_key -> {value: media_id} (only fields that declare option icons)
    value_icons: dict[str, dict] = {}
    for fd in fds:
        icons = (fd.get("config") or {}).get("option_icons") or {}
        if icons:
            value_icons.setdefault(fd["key"], {}).update(icons)
    if not value_icons:
        return
    # collect the media ids actually needed by these records
    needed: set[str] = set()
    for r in records:
        rf = r.get("fields") or {}
        for fk, mapping in value_icons.items():
            v = rf.get(fk)
            vals = v if isinstance(v, list) else [v]
            for val in vals:
                mid = mapping.get(val)
                if mid:
                    needed.add(mid)
    if not needed:
        return
    from core.storage.factory import get_storage_adapter
    adapter = get_storage_adapter()
    media_docs = await db.media.find(
        tenant_filter(org_id, {"_id": {"$in": list(needed)}}),
    ).to_list(len(needed))
    icon_pngs: dict[str, bytes] = {}
    for m in media_docs:
        try:
            icon_pngs[m["_id"]] = await adapter.read_all(m["storage_key"])
        except Exception:
            continue
    cfg["_value_icons"] = value_icons
    cfg["_icon_pngs"] = icon_pngs


@router.get("/labels/presets")
async def list_presets(ctx: AuthContext = Depends(require_permission("records.read"))):
    return preset_summary()


@router.post("/records/labels")
async def make_labels_for_records(
    body: RecordsLabelsBody, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    db = get_db()
    records = await _hydrate_records_with_qr(db, ctx.org_id, body.record_ids)
    if not records:
        raise HTTPException(404, "no records match")
    cfg = body.config.model_dump()
    await _resolve_preset_for_config(db, ctx.org_id, cfg)
    await _prepare_value_icons(db, ctx.org_id, records, cfg)
    pdf = render_labels_pdf(records, cfg)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    fn = f"labels-{cfg.get('preset','custom')}-{ts}.pdf"
    audit(bg, action="labels.printed", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="records", target_id=body.record_ids[0],
          diff={"count": len(records), "preset": body.config.preset,
                "copies": body.config.copies_per_record}, request=request)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.post("/entity-types/{et_id}/records/labels")
async def make_labels_for_view(
    et_id: str, body: ViewLabelsBody, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    # Resolve via the search endpoint's logic. Keep it simple — reuse it.
    from routes.data import search_records
    from models import RecordSearchBody
    search_body = RecordSearchBody(
        q=body.q, category_id=body.category_id, tag_ids=body.tag_ids,
        filters=body.filters, sort=[], limit=body.limit, skip=0,
        view_id=body.view_id,
    )
    r = await search_records(et_id, search_body, ctx=ctx)
    ids = [i["id"] for i in r["items"]]
    if not ids:
        raise HTTPException(404, "no records match")
    truncated = len(ids) >= body.limit
    db = get_db()
    records = await _hydrate_records_with_qr(db, ctx.org_id, ids)
    cfg = body.config.model_dump()
    await _resolve_preset_for_config(db, ctx.org_id, cfg)
    await _prepare_value_icons(db, ctx.org_id, records, cfg)
    pdf = render_labels_pdf(records, cfg)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    fn = f"labels-{cfg.get('preset','custom')}-{ts}.pdf"
    audit(bg, action="labels.printed_view", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="entity_type", target_id=et_id,
          diff={"count": len(records), "preset": body.config.preset,
                "truncated": truncated, "view_id": body.view_id}, request=request)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"',
                 "X-Records-Included": str(len(records)),
                 "X-Truncated": "1" if truncated else "0"},
    )
