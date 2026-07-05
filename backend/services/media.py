"""Media helpers — attach/detach diffing, image dimensions, thumbnails.

The thumbnail generator uses Pillow synchronously in a thread-pool via asyncio's
default executor. Non-image mimes fall back to a static SVG icon (returned as
bytes) so /media/:id/thumb never 500s.
"""
from __future__ import annotations

import asyncio
import io
from typing import Iterable

from motor.motor_asyncio import AsyncIOMotorDatabase

# Pillow is required for image thumbs — import guarded so the rest of the
# module still loads if Pillow is missing (thumb calls will fall back).
try:
    from PIL import Image, UnidentifiedImageError  # type: ignore
    _HAS_PILLOW = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    UnidentifiedImageError = Exception  # type: ignore
    _HAS_PILLOW = False


IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _resize_sync(data: bytes, size: int = 256) -> bytes:
    if not _HAS_PILLOW:
        raise RuntimeError("Pillow not installed")
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        im.thumbnail((size, size))
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue()


async def make_image_thumb(data: bytes, size: int = 256) -> bytes | None:
    if not _HAS_PILLOW:
        return None
    try:
        return await asyncio.get_running_loop().run_in_executor(None, _resize_sync, data, size)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


def _dimensions_sync(data: bytes) -> tuple[int, int] | None:
    if not _HAS_PILLOW:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            return int(im.width), int(im.height)
    except (UnidentifiedImageError, OSError, ValueError):
        return None


async def image_dimensions(data: bytes) -> tuple[int, int] | None:
    return await asyncio.get_running_loop().run_in_executor(None, _dimensions_sync, data)


# ---------- Static file-type icons (inline SVG) ----------
# One per family; served with Content-Type: image/svg+xml.
_ICON_CACHE: dict[str, bytes] = {}


def _svg_icon(letter: str, color: str) -> bytes:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<rect width="256" height="256" rx="24" fill="{color}"/>
<text x="50%" y="50%" text-anchor="middle" dy=".35em"
      font-family="system-ui, sans-serif" font-size="88" font-weight="700" fill="white">
{letter}
</text></svg>"""
    return svg.strip().encode()


def icon_for_mime(mime: str) -> bytes:
    if mime in _ICON_CACHE:
        return _ICON_CACHE[mime]
    m = (mime or "").lower()
    if m == "application/pdf":
        data = _svg_icon("PDF", "#dc2626")
    elif "word" in m or m == "application/msword":
        data = _svg_icon("DOC", "#2563eb")
    elif "sheet" in m or "excel" in m:
        data = _svg_icon("XLS", "#059669")
    elif "presentation" in m or "powerpoint" in m:
        data = _svg_icon("PPT", "#ea580c")
    elif m.startswith("text/"):
        data = _svg_icon("TXT", "#525252")
    elif m.startswith("video/"):
        data = _svg_icon("VID", "#7c3aed")
    elif m.startswith("audio/"):
        data = _svg_icon("AUD", "#0891b2")
    elif m.startswith("image/"):
        data = _svg_icon("IMG", "#0d9488")
    else:
        data = _svg_icon("?", "#6b7280")
    _ICON_CACHE[mime] = data
    return data


# ---------- record media attach/detach diffing ----------

def collect_media_ids_from_field(value, ftype: str) -> set[str]:
    """Extract media_id references from a stored field value.
    Value shapes: {"media_id": "..."} or [{"media_id": "..."}] or "media_id" or [ids]."""
    if value is None or value == "":
        return set()
    if ftype not in ("image", "file"):
        return set()
    out: set[str] = set()
    if isinstance(value, list):
        for v in value:
            out |= _extract_one(v)
    else:
        out |= _extract_one(value)
    return {x for x in out if isinstance(x, str) and x}


def _extract_one(v) -> set[str]:
    if isinstance(v, dict):
        mid = v.get("media_id") or v.get("id")
        return {mid} if isinstance(mid, str) else set()
    if isinstance(v, str):
        return {v}
    return set()


async def apply_media_diff(
    db: AsyncIOMotorDatabase,
    *,
    org_id: str,
    record_id: str,
    field_key: str,
    old_ids: Iterable[str],
    new_ids: Iterable[str],
) -> None:
    old = set(old_ids or [])
    new = set(new_ids or [])
    added = new - old
    removed = old - new
    for mid in added:
        await db.media.update_one(
            {"_id": mid, "org_id": org_id, "deleted_at": None},
            {"$addToSet": {"attached_to": {
                "record_id": record_id, "field_key": field_key, "role": "field",
            }}},
        )
    for mid in removed:
        await db.media.update_one(
            {"_id": mid, "org_id": org_id},
            {"$pull": {"attached_to": {
                "record_id": record_id, "field_key": field_key, "role": "field",
            }}},
        )
