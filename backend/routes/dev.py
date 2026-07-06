"""Developer helpers — demo seed + PDF thumb backfill + IP debug."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from auth_deps import AuthContext, require_permission
from core.request_ip import get_client_ip
from core.storage.factory import get_storage_adapter
from core.storage.local import LocalDiskAdapter
from db import get_db, tenant_filter
from services import media as media_svc
from services.template_applier import apply_template

router = APIRouter(prefix="/dev", tags=["dev"])
log = logging.getLogger("ubos.dev")


@router.post("/seed-demo")
async def seed_demo(ctx: AuthContext = Depends(require_permission("entity_types.manage"))):
    """Idempotent demo seed scoped to the caller's active org (uses `demo_basic` template)."""
    return await apply_template(
        get_db(), org_id=ctx.org_id, key="demo_basic", conflict_policy="skip",
    )


@router.get("/whoami-ip")
async def whoami_ip(
    request: Request,
    ctx: AuthContext = Depends(require_permission("org.update")),
):
    """Echo the layered client-IP resolution.

    Ops uses this to sanity-check rate-limit bucketing behind any reverse
    proxy stack (Cloudflare, K8s ingress, ALB, direct). Admin+ only so this
    doesn't leak infra topology to viewers.
    """
    return {
        "resolved_ip": get_client_ip(request),
        "cf_connecting_ip": request.headers.get("cf-connecting-ip"),
        "x_forwarded_for": request.headers.get("x-forwarded-for"),
        "x_real_ip": request.headers.get("x-real-ip"),
        "remote_addr": request.client.host if request.client else None,
    }


@router.post("/rebuild-pdf-thumbnails")
async def rebuild_pdf_thumbnails(
    ctx: AuthContext = Depends(require_permission("entity_types.manage")),
):
    """Regenerate missing PDF thumbnails for the caller's org. Idempotent —
    skips docs that already have a valid thumb_key on disk."""
    db = get_db()
    adapter = get_storage_adapter()
    if not isinstance(adapter, LocalDiskAdapter):
        return {"skipped": True, "reason": "storage backend is not local disk"}

    cursor = db.media.find(tenant_filter(ctx.org_id, {
        "mime": "application/pdf",
    }), {"_id": 1, "storage_key": 1, "thumb_key": 1, "filename": 1})

    scanned = generated = skipped = failed = 0
    async for doc in cursor:
        scanned += 1
        if doc.get("thumb_key") and await adapter.exists(doc["thumb_key"]):
            skipped += 1
            continue
        try:
            data = await adapter.read_all(doc["storage_key"])
        except Exception as e:
            log.warning("could not read pdf %s: %s", doc["_id"], e)
            failed += 1
            continue
        try:
            thumb = await media_svc.make_pdf_thumb(data, size=256)
        except Exception as e:
            log.warning("pdf thumb failed for %s: %s", doc["_id"], e)
            failed += 1
            continue
        if not thumb:
            log.info("pdf thumb unrenderable for %s (%s)", doc["_id"], doc.get("filename"))
            failed += 1
            continue
        thumb_key = doc["storage_key"] + ".thumb.jpg"
        try:
            await adapter.put_bytes_at_key(thumb_key, thumb)
            await db.media.update_one(
                {"_id": doc["_id"]},
                {"$set": {"thumb_key": thumb_key}},
            )
            generated += 1
        except Exception as e:
            log.warning("could not persist thumb for %s: %s", doc["_id"], e)
            failed += 1

    return {
        "org_id": ctx.org_id,
        "scanned": scanned, "generated": generated,
        "skipped_existing": skipped, "failed_or_unrenderable": failed,
    }
