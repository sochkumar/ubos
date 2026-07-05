"""Custom label preset CRUD (Phase 6-A).

Combined with the four built-in presets in `services/labels.PRESETS`, a
`records.labels` request may resolve `preset` to either a built-in key
(`avery_5160` etc.) OR a `preset_id` referencing a doc in `label_presets`.

All dimensions are stored in millimetres; the reportlab layer converts to
points on render.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db, tenant_filter
from models import strip_id
from services.labels import preset_summary

router = APIRouter(tags=["label-presets"])

_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


PageSize = Literal["Letter", "A4", "A3", "custom"]


class LabelPresetCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    key: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    page_size: PageSize = "A4"
    page_width_mm: float | None = None
    page_height_mm: float | None = None
    cols: int = Field(ge=1, le=20)
    rows: int = Field(ge=1, le=40)
    label_w_mm: float = Field(gt=0, le=500)
    label_h_mm: float = Field(gt=0, le=500)
    margin_top_mm: float = Field(default=10.0, ge=0, le=200)
    margin_left_mm: float = Field(default=10.0, ge=0, le=200)
    gutter_h_mm: float = Field(default=0.0, ge=0, le=200)
    gutter_v_mm: float = Field(default=0.0, ge=0, le=200)


class LabelPresetUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    page_size: PageSize | None = None
    page_width_mm: float | None = None
    page_height_mm: float | None = None
    cols: int | None = Field(default=None, ge=1, le=20)
    rows: int | None = Field(default=None, ge=1, le=40)
    label_w_mm: float | None = Field(default=None, gt=0, le=500)
    label_h_mm: float | None = Field(default=None, gt=0, le=500)
    margin_top_mm: float | None = Field(default=None, ge=0, le=200)
    margin_left_mm: float | None = Field(default=None, ge=0, le=200)
    gutter_h_mm: float | None = Field(default=None, ge=0, le=200)
    gutter_v_mm: float | None = Field(default=None, ge=0, le=200)


def _validate_key(key: str) -> str:
    key = (key or "").strip().lower()
    if not _KEY_RE.match(key):
        raise HTTPException(422, {
            "code": "invalid_key",
            "detail": "Key must be lowercase, start with a letter, and use letters/digits/_/-.",
        })
    return key


def _validate_custom_size(payload: dict) -> None:
    if payload.get("page_size") == "custom":
        if not payload.get("page_width_mm") or not payload.get("page_height_mm"):
            raise HTTPException(422, {
                "code": "custom_page_missing_dimensions",
                "detail": "page_width_mm and page_height_mm are required when page_size='custom'.",
            })


def _hydrate(doc: dict) -> dict:
    d = strip_id(doc)
    d["is_system"] = bool(d.get("is_system"))
    return d


@router.get("/orgs/{org_id}/label-presets")
async def list_label_presets(
    org_id: str, ctx: AuthContext = Depends(require_permission("records.read")),
):
    if ctx.org_id != org_id:
        raise HTTPException(403, "active org does not match")
    db = get_db()
    system = preset_summary()  # built-in 4
    # normalize system shape to include the fields the frontend expects
    system_out = [
        {
            "id": None, "org_id": None, "key": p["key"], "name": p["label"],
            "page_size": p["page"], "cols": p["cols"], "rows": p["rows"],
            "per_page": p["per_page"], "is_system": True,
            # dimensions filled from services.labels.PRESETS on demand
        }
        for p in system
    ]
    custom = await db.label_presets.find(
        tenant_filter(org_id, {}),
    ).sort("created_at", -1).to_list(200)
    return {
        "system": system_out,
        "custom": [_hydrate(d) for d in custom],
    }


@router.post("/orgs/{org_id}/label-presets", status_code=201)
async def create_label_preset(
    org_id: str, body: LabelPresetCreate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    if ctx.org_id != org_id:
        raise HTTPException(403, "active org does not match")
    key = _validate_key(body.key)
    payload = body.model_dump()
    payload["key"] = key
    _validate_custom_size(payload)
    db = get_db()
    dup = await db.label_presets.find_one(
        tenant_filter(org_id, {"key": key}),
    )
    if dup:
        raise HTTPException(409, {"code": "duplicate_key",
                                   "detail": f"A preset with key '{key}' already exists."})
    doc = {
        "_id": str(uuid.uuid4()),
        "org_id": org_id,
        "is_system": False,
        "created_by": ctx.user["_id"],
        "created_at": _now(),
        "updated_at": _now(),
        "deleted_at": None,
        **payload,
    }
    await db.label_presets.insert_one(doc)
    audit(bg, action="label_preset.created", actor_id=ctx.user["_id"], org_id=org_id,
          target_type="label_preset", target_id=doc["_id"],
          diff={"key": key, "cols": body.cols, "rows": body.rows}, request=request)
    return _hydrate(doc)


@router.patch("/label-presets/{pid}")
async def update_label_preset(
    pid: str, body: LabelPresetUpdate, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    doc = await db.label_presets.find_one({"_id": pid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "label preset not found")
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return _hydrate(doc)
    merged = {**doc, **updates}
    _validate_custom_size(merged)
    updates["updated_at"] = _now()
    await db.label_presets.update_one({"_id": pid}, {"$set": updates})
    fresh = await db.label_presets.find_one({"_id": pid})
    audit(bg, action="label_preset.updated", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="label_preset", target_id=pid,
          diff={k: v for k, v in updates.items() if k != "updated_at"},
          request=request)
    return _hydrate(fresh)


@router.delete("/label-presets/{pid}", status_code=204)
async def delete_label_preset(
    pid: str, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    db = get_db()
    doc = await db.label_presets.find_one({"_id": pid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "label preset not found")
    await db.label_presets.update_one(
        {"_id": pid}, {"$set": {"deleted_at": _now(), "updated_at": _now()}},
    )
    audit(bg, action="label_preset.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="label_preset", target_id=pid, request=request)
    return None
