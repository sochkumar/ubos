"""Developer helpers — demo seed via the reusable TemplateApplier."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth_deps import AuthContext, require_permission
from db import get_db
from services.template_applier import apply_template

router = APIRouter(prefix="/dev", tags=["dev"])


@router.post("/seed-demo")
async def seed_demo(ctx: AuthContext = Depends(require_permission("entity_types.manage"))):
    """Idempotent demo seed scoped to the caller's active org (uses `demo_basic` template)."""
    return await apply_template(
        get_db(), org_id=ctx.org_id, key="demo_basic", conflict_policy="skip",
    )
