"""Per-user dashboard layout (Phase 6-B).

Widgets are identified by stable `widget_key` strings. The frontend still
receives all widget data from `GET /api/dashboard/summary`; layout only
governs order + visibility for rendering. Persisted on the user document
(`dashboard_layouts` map keyed by org_id).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from audit import audit
from auth_deps import AuthContext, get_current_user, require_permission
from db import get_db

router = APIRouter(tags=["dashboard-layout"])

WIDGET_KEYS = ["recent_records", "activity", "storage", "entity_types"]


def _default_layout() -> list[dict]:
    return [
        {"widget_key": k, "visible": True, "order": i}
        for i, k in enumerate(WIDGET_KEYS)
    ]


class WidgetSlot(BaseModel):
    model_config = ConfigDict(extra="ignore")
    widget_key: Literal["recent_records", "activity", "storage", "entity_types"]
    visible: bool = True
    order: int = Field(ge=0, le=99)


class LayoutBody(BaseModel):
    layout: list[WidgetSlot] = Field(min_length=1, max_length=32)


def _validate_and_normalize(layout: list[dict]) -> list[dict]:
    """Keep known widgets only, dedupe by widget_key, sort by order."""
    seen: dict[str, dict] = {}
    for slot in layout:
        k = slot["widget_key"]
        if k not in WIDGET_KEYS:
            continue
        seen[k] = {
            "widget_key": k,
            "visible": bool(slot.get("visible", True)),
            "order": int(slot.get("order", 0)),
        }
    # Fill in any missing widgets so users get new widgets we ship later
    max_order = max((s["order"] for s in seen.values()), default=-1)
    for k in WIDGET_KEYS:
        if k not in seen:
            max_order += 1
            seen[k] = {"widget_key": k, "visible": True, "order": max_order}
    return sorted(seen.values(), key=lambda s: (s["order"], s["widget_key"]))


async def _load_layout(db, user_id: str, org_id: str) -> list[dict]:
    u = await db.users.find_one({"_id": user_id}, {"dashboard_layouts": 1})
    layouts = (u or {}).get("dashboard_layouts") or {}
    saved = layouts.get(org_id)
    if not saved:
        return _default_layout()
    return _validate_and_normalize(saved)


@router.get("/dashboard/layout")
async def get_layout(
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    layout = await _load_layout(get_db(), ctx.user["_id"], ctx.org_id)
    return {"layout": layout, "defaults": _default_layout()}


@router.put("/dashboard/layout")
async def put_layout(
    body: LayoutBody,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    normalized = _validate_and_normalize([s.model_dump() for s in body.layout])
    now = datetime.now(timezone.utc).isoformat()
    await get_db().users.update_one(
        {"_id": ctx.user["_id"]},
        {"$set": {
            f"dashboard_layouts.{ctx.org_id}": normalized,
            "updated_at": now,
        }},
    )
    audit(bg, action="dashboard.layout.updated",
          actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="user", target_id=ctx.user["_id"],
          diff={"widget_count": len(normalized),
                "hidden": [s["widget_key"] for s in normalized if not s["visible"]]},
          request=request)
    return {"layout": normalized}


@router.post("/dashboard/layout/reset")
async def reset_layout(
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    now = datetime.now(timezone.utc).isoformat()
    await get_db().users.update_one(
        {"_id": ctx.user["_id"]},
        {"$unset": {f"dashboard_layouts.{ctx.org_id}": ""},
         "$set": {"updated_at": now}},
    )
    audit(bg, action="dashboard.layout.reset",
          actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="user", target_id=ctx.user["_id"],
          request=request)
    return {"layout": _default_layout()}
