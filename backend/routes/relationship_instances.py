"""Record-to-record relationship instance CRUD (bidirectional + cardinality)."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from audit import audit
from auth_deps import AuthContext, require_permission
from db import get_db
from services import relationships as rel_svc

router = APIRouter(tags=["relationship-instances"])


@router.get("/records/{rid}/relationships")
async def list_record_relationships(
    rid: str, ctx: AuthContext = Depends(require_permission("records.read")),
):
    return await rel_svc.list_relationships_for_record(
        get_db(), org_id=ctx.org_id, record_id=rid,
    )


@router.post("/records/{rid}/relationships", status_code=201)
async def create_record_relationship(
    rid: str, body: dict, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    rel_def_id = body.get("rel_def_id")
    target_id = body.get("target_record_id") or body.get("target_id")
    if not rel_def_id or not target_id:
        raise HTTPException(422, "rel_def_id and target_record_id are required")
    result = await rel_svc.link_records(
        get_db(), org_id=ctx.org_id,
        source_id=rid, rel_def_id=rel_def_id, target_id=target_id,
    )
    if not result.get("already_linked"):
        audit(bg, action="record.linked", actor_id=ctx.user["_id"], org_id=ctx.org_id,
              target_type="record", target_id=rid,
              diff={"rel_def_id": rel_def_id, "target": target_id},
              request=request)
    return result


@router.delete("/records/{rid}/relationships/{target_id}", status_code=204)
async def delete_record_relationship(
    rid: str, target_id: str,
    rel_def_id: str = Query(...),
    bg: BackgroundTasks = None, request: Request = None,
    ctx: AuthContext = Depends(require_permission("records.update")),
):
    await rel_svc.unlink_records(
        get_db(), org_id=ctx.org_id,
        source_id=rid, rel_def_id=rel_def_id, target_id=target_id,
    )
    audit(bg, action="record.unlinked", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="record", target_id=rid,
          diff={"rel_def_id": rel_def_id, "target": target_id},
          request=request)
    return None
