"""Templates gallery + apply endpoint."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db
from models import TemplateApplyBody
from services.template_applier import apply_template, list_library, load_spec

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
async def list_templates(
    ctx: AuthContext = Depends(require_permission("records.read")),
):
    return list_library()


@router.get("/{key}")
async def get_template(
    key: str, ctx: AuthContext = Depends(require_permission("records.read"))
):
    spec = load_spec(key)
    # Return a scrubbed preview version (no server-only knobs)
    return {
        "key": spec.get("key"),
        "name": spec.get("name"),
        "description": spec.get("description"),
        "icon": spec.get("icon"),
        "cover_image": spec.get("cover_image"),
        "entity_types": [
            {
                "key": e["key"],
                "name_singular": e.get("name_singular", e["key"]),
                "name_plural": e.get("name_plural", e["key"]),
                "icon": e.get("icon"),
                "color": e.get("color"),
                "field_count": len(e.get("fields") or []),
                "fields": [
                    {"key": f["key"], "label": f.get("label", f["key"]), "type": f["type"],
                     "required": bool(f.get("required")), "unique": bool(f.get("unique"))}
                    for f in (e.get("fields") or [])
                ],
                "categories": e.get("categories") or [],
            }
            for e in (spec.get("entity_types") or [])
        ],
        "relationships": spec.get("relationships") or [],
        "tags": spec.get("tags") or [],
    }


@router.post("/{key}/apply")
async def apply_template_endpoint(
    key: str,
    payload: TemplateApplyBody,
    bg: BackgroundTasks,
    request: Request,
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    result = await apply_template(
        get_db(),
        org_id=ctx.org_id,
        key=key,
        conflict_policy=payload.conflict_policy,
        dry_run=payload.dry_run,
    )
    if not payload.dry_run:
        audit(bg, action="template.applied", actor_id=ctx.user["_id"], org_id=ctx.org_id,
              target_type="template", target_id=key,
              diff={"conflict_policy": payload.conflict_policy,
                    "inserted": result.get("inserted", {})},
              request=request)
    return result
