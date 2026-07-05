"""Media upload / list / thumb / serve / attach endpoints."""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request,
    UploadFile, File, Form,
)
from fastapi.responses import Response, StreamingResponse

from audit import audit
from auth_deps import AuthContext, require_permission
from core.storage.factory import get_storage_adapter
from core.storage.local import LocalDiskAdapter, verify_token
from db import get_db, tenant_filter
from models import strip_id
from services import media as media_svc
from services import quota as quota_svc

log = logging.getLogger("ubos.media")

router = APIRouter(tags=["media"])

ALLOWED_MIMES = {
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "text/plain", "text/csv",
    "video/mp4", "video/quicktime",
    "application/zip",
    "application/octet-stream",
}
# SVG is rejected: server-side sanitisation isn't in scope for Sub-pass B.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/media/storage")
async def storage_status(ctx: AuthContext = Depends(require_permission("media.read"))):
    used, quota, max_upload = await quota_svc.quota_of(get_db(), ctx.org_id)
    return {
        "used_bytes": used, "quota_bytes": quota,
        "max_upload_bytes": max_upload,
        "percent": round((used / quota) * 100, 2) if quota else 0,
    }


@router.post("/media/upload", status_code=201)
async def upload_media(
    request: Request, bg: BackgroundTasks,
    files: list[UploadFile] = File(...),
    record_id: str | None = Form(default=None),
    field_key: str | None = Form(default=None),
    role: str = Form(default="field"),
    ctx: AuthContext = Depends(require_permission("media.manage")),
):
    if role not in ("field", "gallery", "attachment"):
        raise HTTPException(422, "role must be one of field|gallery|attachment")
    db = get_db()
    adapter = get_storage_adapter()

    created: list[dict] = []
    max_upload = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(25 * 1024 * 1024)))
    for up in files:
        # Stream-read with early bail — avoids loading a hostile giant body
        # into memory before quota_svc gets a chance to reject it.
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = await up.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_upload:
                raise HTTPException(
                    status_code=413,
                    detail={
                        "code": "file_too_large",
                        "detail": "File exceeds MAX_UPLOAD_SIZE_BYTES",
                        "max_bytes": max_upload,
                        "incoming_bytes": total,
                    },
                )
            chunks.append(chunk)
        data = b"".join(chunks)
        size = len(data)
        mime = up.content_type or "application/octet-stream"
        if mime not in ALLOWED_MIMES:
            raise HTTPException(415, {"detail": f"mime type '{mime}' is not allowed",
                                       "allowed": sorted(ALLOWED_MIMES)})
        await quota_svc.check_can_upload(db, ctx.org_id, size)

        # Dedup on checksum-per-org
        import hashlib as _h
        checksum = _h.sha256(data).hexdigest()
        existing = await db.media.find_one({
            "org_id": ctx.org_id, "checksum": checksum, "deleted_at": None,
        })
        if existing:
            # If a target record is specified, attach the existing media
            if record_id:
                await _attach_media(db, ctx.org_id, existing["_id"],
                                    record_id, field_key, role)
                existing = await db.media.find_one({"_id": existing["_id"]})
            created.append(strip_id(existing))
            continue

        obj = await adapter.put(
            org_id=ctx.org_id, key_prefix="", filename=up.filename or "file",
            data=data, mime=mime,
        )
        mid = str(uuid.uuid4())
        doc: dict = {
            "_id": mid, "org_id": ctx.org_id, "uploader_id": ctx.user["_id"],
            "filename": up.filename or "file",
            "mime": mime, "size": size, "checksum": checksum,
            "storage_backend": adapter.backend_name,
            "storage_key": obj.storage_key,
            "thumb_key": None,
            "attached_to": [],
            "created_at": _now(), "updated_at": _now(), "deleted_at": None,
        }
        if mime.startswith("image/"):
            dims = await media_svc.image_dimensions(data)
            if dims:
                doc["width"], doc["height"] = dims
        # PDF page-1 thumbnail (Phase 6-A). Fail-safe: falls back to icon.
        if mime == "application/pdf":
            try:
                thumb = await media_svc.make_pdf_thumb(data, size=256)
                if thumb:
                    thumb_key = obj.storage_key + ".thumb.jpg"
                    await adapter.put_bytes_at_key(thumb_key, thumb)
                    doc["thumb_key"] = thumb_key
                    log.info("pdf thumb generated on upload for %s (%d bytes)",
                             doc["filename"], len(thumb))
                else:
                    log.info("pdf thumb skipped (unrenderable) for %s", doc["filename"])
            except Exception as e:
                log.warning("pdf thumb failed for %s: %s", doc["filename"], e)
        await db.media.insert_one(doc)
        await quota_svc.add_bytes(db, ctx.org_id, size)

        if record_id:
            await _attach_media(db, ctx.org_id, mid, record_id, field_key, role)
            doc = await db.media.find_one({"_id": mid})

        audit(bg, action="media.uploaded", actor_id=ctx.user["_id"], org_id=ctx.org_id,
              target_type="media", target_id=mid,
              diff={"filename": doc["filename"], "size": size, "mime": mime},
              request=request)
        created.append(strip_id(doc))
    return created


async def _attach_media(db, org_id, media_id, record_id, field_key, role):
    if not await db.records.find_one(tenant_filter(org_id, {"_id": record_id}), {"_id": 1}):
        raise HTTPException(404, f"record {record_id} not found")
    await db.media.update_one(
        {"_id": media_id, "org_id": org_id, "deleted_at": None},
        {"$addToSet": {"attached_to": {
            "record_id": record_id, "field_key": field_key, "role": role,
        }}, "$set": {"updated_at": _now()}},
    )


@router.get("/media")
async def list_media(
    record_id: str | None = Query(default=None),
    mime: str | None = Query(default=None),
    uploader_id: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(require_permission("media.read")),
):
    db = get_db()
    filt: dict = {"org_id": ctx.org_id, "deleted_at": None}
    if record_id:
        filt["attached_to.record_id"] = record_id
    if mime:
        if mime.endswith("/*"):
            filt["mime"] = {"$regex": f"^{mime[:-2]}/"}
        else:
            filt["mime"] = mime
    if uploader_id:
        filt["uploader_id"] = uploader_id
    if q:
        filt["filename"] = {"$regex": q, "$options": "i"}
    total = await db.media.count_documents(filt)
    cursor = db.media.find(filt).sort("created_at", -1).skip(skip).limit(limit)
    return {"total": total, "items": [strip_id(d) for d in await cursor.to_list(limit)]}


@router.get("/media/{mid}")
async def get_media(mid: str, ctx: AuthContext = Depends(require_permission("media.read"))):
    db = get_db()
    doc = await db.media.find_one({"_id": mid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "media not found")
    # Hydrate attached_to record titles
    att = doc.get("attached_to") or []
    rids = list({a.get("record_id") for a in att if a.get("record_id")})
    if rids:
        recs = {r["_id"]: r for r in await db.records.find(
            tenant_filter(ctx.org_id, {"_id": {"$in": rids}}),
            {"title": 1, "record_number": 1, "entity_type_id": 1},
        ).to_list(1000)}
        for a in att:
            r = recs.get(a.get("record_id"))
            if r:
                a["record_title"] = r.get("title") or r.get("record_number")
                a["record_number"] = r.get("record_number")
                a["entity_type_id"] = r.get("entity_type_id")
    doc["attached_to"] = att
    return strip_id(doc)


@router.get("/media/{mid}/file")
async def get_media_file(
    mid: str, ctx: AuthContext = Depends(require_permission("media.read")),
):
    db = get_db()
    doc = await db.media.find_one({"_id": mid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "media not found")
    adapter = get_storage_adapter()
    url = await adapter.presigned_get(doc["storage_key"])
    return {"url": url, "filename": doc["filename"], "mime": doc["mime"], "size": doc["size"]}


@router.get("/media/mime-icon/{family}", include_in_schema=False)
async def mime_icon(family: str, request: Request):
    """Public static icon endpoint. Serves the same colored-letter SVG that
    /media/:id/thumb points at for non-image files.

    Cache strategy — the origin sets `Cache-Control: public, max-age=86400` and
    `CDN-Cache-Control: public, max-age=86400`. If an upstream proxy strips
    Cache-Control (some do), browsers can still avoid re-downloading via the
    strong `ETag` + `Last-Modified` validators — a subsequent hit with
    `If-None-Match` gets a cheap 304 with no body.

    `family` may be a mime string (e.g. `application/pdf`) or a family shortcut
    (`pdf`, `doc`, `xls`, `ppt`, `txt`, `video`, `audio`, `image`, `generic`)."""
    shortcuts = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "xls": "application/vnd.ms-excel",
        "ppt": "application/vnd.ms-powerpoint",
        "txt": "text/plain",
        "video": "video/mp4",
        "audio": "audio/mpeg",
        "image": "image/generic",
        "generic": "application/octet-stream",
    }
    from urllib.parse import unquote
    key = shortcuts.get(family.lower(), unquote(family))
    body = media_svc.icon_for_mime(key)
    # Strong ETag — SVGs are content-addressed by their bytes.
    import hashlib as _h
    etag = '"' + _h.md5(body).hexdigest() + '"'

    # 304 short-circuit on If-None-Match. Use weak comparison per RFC 7232
    # §2.3.2 — CDNs (Cloudflare, Fastly) that re-gzip the body convert our
    # strong `"..."` tag into a weak `W/"..."` tag; browsers then echo the
    # weak form back on revalidation. Stripping the optional `W/` prefix
    # from both sides makes the match still succeed end-to-end.
    def _normalize_etag(t: str) -> str:
        t = t.strip()
        if t.startswith("W/"):
            t = t[2:]
        return t
    inm = request.headers.get("if-none-match")
    if inm:
        tags = [_normalize_etag(t) for t in inm.split(",")]
        if _normalize_etag(etag) in tags or "*" in tags:
            return Response(status_code=304, headers={
                "ETag": etag,
                "Cache-Control": "public, max-age=86400, immutable",
                "CDN-Cache-Control": "public, max-age=86400, immutable",
            })

    return Response(
        content=body,
        media_type="image/svg+xml",
        headers={
            "ETag": etag,
            "Cache-Control": "public, max-age=86400, immutable",
            # Some CDNs (Cloudflare, Fastly, Akamai) respect this even when
            # they rewrite the browser-facing Cache-Control.
            "CDN-Cache-Control": "public, max-age=86400, immutable",
            "Last-Modified": "Sat, 01 Jan 2000 00:00:00 GMT",
            "Vary": "Accept-Encoding",
        },
    )


def _icon_family_for(mime: str) -> str:
    m = (mime or "").lower()
    if m == "application/pdf":
        return "pdf"
    if "word" in m or m == "application/msword":
        return "doc"
    if "sheet" in m or "excel" in m:
        return "xls"
    if "presentation" in m or "powerpoint" in m:
        return "ppt"
    if m.startswith("text/"):
        return "txt"
    if m.startswith("video/"):
        return "video"
    if m.startswith("audio/"):
        return "audio"
    if m.startswith("image/"):
        return "image"
    return "generic"


@router.get("/media/{mid}/thumb",
             description=(
                 "Returns a JSON envelope `{url, mime}` regardless of the "
                 "underlying media type. For image mimes the URL is a signed, "
                 "time-limited link to a Pillow-generated 256×256 JPEG "
                 "(generated on first hit, cached in `thumb_key`). For every "
                 "other mime family the URL points to a stable, publicly "
                 "cacheable SVG icon under `/api/media/mime-icon/{family}`. "
                 "Clients should always follow the URL rather than parse "
                 "response body bytes."
             ))
async def get_media_thumb(
    mid: str, ctx: AuthContext = Depends(require_permission("media.read")),
):
    db = get_db()
    doc = await db.media.find_one({"_id": mid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "media not found")
    adapter = get_storage_adapter()
    mime = doc.get("mime") or ""

    # PDF path: render first page via pdf2image → JPEG (Phase 6-A)
    if mime == "application/pdf":
        if doc.get("thumb_key") and await adapter.exists(doc["thumb_key"]):
            url = await adapter.presigned_get(doc["thumb_key"])
            return {"url": url, "mime": "image/jpeg"}
        if not isinstance(adapter, LocalDiskAdapter):
            return {
                "url": f"/api/media/mime-icon/{_icon_family_for(mime)}",
                "mime": "image/svg+xml",
            }
        try:
            data = await adapter.read_all(doc["storage_key"])
            thumb = await media_svc.make_pdf_thumb(data, size=256)
        except Exception:
            thumb = None
        if not thumb:
            return {
                "url": f"/api/media/mime-icon/{_icon_family_for(mime)}",
                "mime": "image/svg+xml",
            }
        thumb_key = doc["storage_key"] + ".thumb.jpg"
        await adapter.put_bytes_at_key(thumb_key, thumb)
        await db.media.update_one({"_id": mid}, {"$set": {"thumb_key": thumb_key}})
        url = await adapter.presigned_get(thumb_key)
        return {"url": url, "mime": "image/jpeg"}

    # Non-image (including image/svg+xml which we don't render) → static icon URL
    if not mime.startswith("image/") or mime == "image/svg+xml":
        return {
            "url": f"/api/media/mime-icon/{_icon_family_for(mime)}",
            "mime": "image/svg+xml",
        }

    # Image path: signed URL to generated JPEG thumbnail
    if doc.get("thumb_key") and await adapter.exists(doc["thumb_key"]):
        url = await adapter.presigned_get(doc["thumb_key"])
        return {"url": url, "mime": "image/jpeg"}

    if not isinstance(adapter, LocalDiskAdapter):
        # Storage backend doesn't support inline thumb generation yet
        return {
            "url": f"/api/media/mime-icon/{_icon_family_for(mime)}",
            "mime": "image/svg+xml",
        }

    data = await adapter.read_all(doc["storage_key"])
    thumb = await media_svc.make_image_thumb(data, size=256)
    if not thumb:
        # Corrupt image, degrade to family icon
        return {
            "url": f"/api/media/mime-icon/{_icon_family_for(mime)}",
            "mime": "image/svg+xml",
        }
    thumb_key = doc["storage_key"] + ".thumb.jpg"
    await adapter.put_bytes_at_key(thumb_key, thumb)
    await db.media.update_one({"_id": mid}, {"$set": {"thumb_key": thumb_key}})
    url = await adapter.presigned_get(thumb_key)
    return {"url": url, "mime": "image/jpeg"}


@router.get("/media/serve/{token}", include_in_schema=False)
async def serve_media(token: str):
    """LocalDiskAdapter's presigned URL landing page — streams the file."""
    adapter = get_storage_adapter()
    if not isinstance(adapter, LocalDiskAdapter):
        raise HTTPException(404, "not supported for this storage backend")
    key = verify_token(token, os.environ["MEDIA_SIGNING_SECRET"])
    if not key:
        raise HTTPException(403, "invalid or expired token")
    if not await adapter.exists(key):
        raise HTTPException(404, "file not found")

    db = get_db()
    # Look up the media doc for its filename + mime so headers are useful.
    doc = await db.media.find_one({"storage_key": key})
    if not doc:
        # Might be a thumb — try suffix match
        if key.endswith(".thumb.jpg"):
            doc = {"filename": "thumb.jpg", "mime": "image/jpeg"}
        else:
            doc = {"filename": "file", "mime": "application/octet-stream"}

    async def gen():
        async for chunk in adapter.get_stream(key):
            yield chunk

    fn = doc.get("filename") or "file"
    return StreamingResponse(
        gen(), media_type=doc.get("mime") or "application/octet-stream",
        headers={
            "Content-Disposition": f'inline; filename="{fn}"',
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )


@router.post("/media/{mid}/attach")
async def attach_media(
    mid: str, body: dict, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("media.manage")),
):
    db = get_db()
    doc = await db.media.find_one({"_id": mid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "media not found")
    record_id = body.get("record_id")
    field_key = body.get("field_key")
    role = body.get("role", "attachment")
    if role not in ("field", "gallery", "attachment"):
        raise HTTPException(422, "role must be one of field|gallery|attachment")
    if not record_id:
        raise HTTPException(422, "record_id is required")
    await _attach_media(db, ctx.org_id, mid, record_id, field_key, role)
    audit(bg, action="media.attached", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="media", target_id=mid,
          diff={"record_id": record_id, "field_key": field_key, "role": role},
          request=request)
    fresh = await db.media.find_one({"_id": mid})
    return strip_id(fresh)


@router.post("/media/{mid}/detach")
async def detach_media(
    mid: str, body: dict, bg: BackgroundTasks, request: Request,
    ctx: AuthContext = Depends(require_permission("media.manage")),
):
    db = get_db()
    doc = await db.media.find_one({"_id": mid, "org_id": ctx.org_id})
    if not doc:
        raise HTTPException(404, "media not found")
    record_id = body.get("record_id")
    field_key = body.get("field_key")
    role = body.get("role")
    if not record_id:
        raise HTTPException(422, "record_id is required")
    pull: dict = {"record_id": record_id}
    if field_key is not None:
        pull["field_key"] = field_key
    if role is not None:
        pull["role"] = role
    await db.media.update_one(
        {"_id": mid, "org_id": ctx.org_id},
        {"$pull": {"attached_to": pull}, "$set": {"updated_at": _now()}},
    )
    audit(bg, action="media.detached", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="media", target_id=mid, diff=pull, request=request)
    return strip_id(await db.media.find_one({"_id": mid}))


@router.delete("/media/{mid}", status_code=204)
async def delete_media(
    mid: str, bg: BackgroundTasks, request: Request,
    cascade: bool = Query(default=False),
    ctx: AuthContext = Depends(require_permission("media.manage")),
):
    db = get_db()
    doc = await db.media.find_one({"_id": mid, "org_id": ctx.org_id, "deleted_at": None})
    if not doc:
        raise HTTPException(404, "media not found")
    # uploader OR admin+ can delete
    if doc["uploader_id"] != ctx.user["_id"] and ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "only the uploader or an admin can delete media")

    att = doc.get("attached_to") or []
    if att and not cascade:
        raise HTTPException(
            status_code=409,
            detail={"code": "media_in_use", "detail": "media is attached to records",
                    "attached_to": att, "hint": "pass ?cascade=true to detach & delete"},
        )

    # cascade: pull the media_id from records.fields.<field_key> too
    for a in att:
        r_id = a.get("record_id")
        f_key = a.get("field_key")
        if not r_id or not f_key:
            continue
        r = await db.records.find_one({"_id": r_id, "org_id": ctx.org_id})
        if not r:
            continue
        cur = (r.get("fields") or {}).get(f_key)
        matches = lambda v: (  # noqa: E731
            (isinstance(v, dict) and (v.get("media_id") == mid or v.get("id") == mid))
            or v == mid
        )
        if isinstance(cur, list):
            kept = [v for v in cur if not matches(v)]
            new = kept if kept else None   # normalise empty → None (align w/ scalar)
        elif matches(cur):
            new = None
        else:
            continue
        await db.records.update_one(
            {"_id": r_id, "org_id": ctx.org_id},
            {"$set": {f"fields.{f_key}": new, "updated_at": _now()}},
        )

    now = _now()
    await db.media.update_one({"_id": mid},
        {"$set": {"deleted_at": now, "updated_at": now, "attached_to": []}})
    await quota_svc.add_bytes(db, ctx.org_id, -int(doc.get("size", 0)))

    # Best-effort: remove original + cached thumb from disk.
    adapter = get_storage_adapter()
    for k in (doc.get("storage_key"), doc.get("thumb_key")):
        if not k:
            continue
        try:
            await adapter.delete(k)
        except Exception:  # pragma: no cover
            pass

    audit(bg, action="media.deleted", actor_id=ctx.user["_id"], org_id=ctx.org_id,
          target_type="media", target_id=mid,
          diff={"filename": doc["filename"], "size": doc["size"], "cascade": cascade},
          request=request)
    return None
