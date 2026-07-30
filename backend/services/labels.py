"""Avery-style multi-per-page label PDFs via reportlab.

Coordinates are in points (1/72 inch); reportlab's origin is bottom-left."""
from __future__ import annotations

import io
from typing import Literal

from reportlab.lib.pagesizes import LETTER, A4, A3
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from services.qr_barcode import make_qr_png, make_barcode_png

_PAGE_SIZES = {
    "Letter": LETTER,
    "A4": A4,
    "A3": A3,
}


def preset_from_custom_doc(doc: dict) -> dict:
    """Convert a `label_presets` DB doc (mm) to the internal preset dict (points)."""
    page_size_key = doc.get("page_size", "A4")
    if page_size_key == "custom":
        page_size = (float(doc["page_width_mm"]) * mm, float(doc["page_height_mm"]) * mm)
    else:
        page_size = _PAGE_SIZES.get(page_size_key, A4)
    return {
        "page_size": page_size,
        "top": float(doc.get("margin_top_mm", 10.0)) * mm,
        "left": float(doc.get("margin_left_mm", 10.0)) * mm,
        "label_w": float(doc["label_w_mm"]) * mm,
        "label_h": float(doc["label_h_mm"]) * mm,
        "gx": float(doc.get("gutter_h_mm", 0.0)) * mm,
        "gy": float(doc.get("gutter_v_mm", 0.0)) * mm,
        "cols": int(doc["cols"]),
        "rows": int(doc["rows"]),
        "label_of": doc.get("name", "Custom"),
    }

# ─────────────────────── presets ───────────────────────
# Each preset: page_size, margins (top,left), label_size, gutter, cols, rows.
PRESETS = {
    "avery_5160": {
        "page_size": LETTER,
        "top": 0.5 * inch, "left": 0.1875 * inch,
        "label_w": 2.625 * inch, "label_h": 1.0 * inch,
        "gx": 0.125 * inch, "gy": 0.0 * inch,
        "cols": 3, "rows": 10, "label_of": "US Address (2⅝ × 1 in)",
    },
    "avery_5163": {
        "page_size": LETTER,
        "top": 0.5 * inch, "left": 0.15625 * inch,
        "label_w": 4.0 * inch, "label_h": 2.0 * inch,
        "gx": 0.1875 * inch, "gy": 0.0 * inch,
        "cols": 2, "rows": 5, "label_of": "US Shipping (2 × 4 in)",
    },
    "avery_l7160": {
        "page_size": A4,
        "top": 15.0 * mm, "left": 7.21 * mm,
        "label_w": 63.5 * mm, "label_h": 38.1 * mm,
        "gx": 2.54 * mm, "gy": 0.0 * mm,
        "cols": 3, "rows": 7, "label_of": "A4 Address (63.5 × 38.1 mm)",
    },
    "avery_l7163": {
        "page_size": A4,
        "top": 15.0 * mm, "left": 4.65 * mm,
        "label_w": 99.1 * mm, "label_h": 38.1 * mm,
        "gx": 2.54 * mm, "gy": 0.0 * mm,
        "cols": 2, "rows": 7, "label_of": "A4 Shipping (99.1 × 38.1 mm)",
    },
}


def _fit_and_render_fields(
    c, *, x, y_top, y_bot, width, entries, min_font=5, start_font=7,
):
    """Render as many field entries as fit inside the vertical band
    [y_bot, y_top] with width `width`. Progressive shrink from `start_font`
    down to `min_font`; if still too many lines to fit, truncate with ellipsis.

    entries: list of preformatted strings like "label: value".
    Returns the y-cursor after rendering (bottom of the last line drawn).
    """
    if not entries:
        return y_top
    avail_h = y_top - y_bot
    if avail_h <= 0:
        return y_top
    # Try font sizes 7 → min_font until every entry fits.
    for size in range(start_font, min_font - 1, -1):
        line_h = size + 1.5  # small leading
        max_lines = int(avail_h // line_h)
        if max_lines <= 0:
            continue
        if len(entries) <= max_lines:
            break
    else:
        size = min_font
        line_h = size + 1.5
        max_lines = max(1, int(avail_h // line_h))

    c.setFont("Helvetica", size)
    # Approx characters that fit at this font size — Helvetica avg char width ≈ 0.5 * size.
    max_chars = max(6, int(width / (0.5 * size)))
    cursor = y_top
    drawn = 0
    for s in entries:
        if drawn >= max_lines:
            break
        if drawn == max_lines - 1 and len(entries) > max_lines:
            s = "…"  # last visible slot is an overflow marker
        if len(s) > max_chars:
            s = s[: max_chars - 1] + "…"
        cursor -= line_h
        c.drawString(x, cursor, s)
        drawn += 1
    return cursor


def _draw_label(c, x, y, w, h, *, record, config):
    """Draw a single label at (x,y) top-left. Reportlab origin is bottom-left,
    so we flip inside this helper."""
    page_h = c._pagesize[1]
    y_bl = page_h - y - h  # bottom-left corner in reportlab coords
    pad = 4
    inner_x = x + pad
    inner_y_top = page_h - y - pad  # top of inner area
    text_left = inner_x
    text_width = w - 2 * pad

    code_mode = config.get("code_mode", "qr_and_barcode")
    show_title = config.get("show_title", True)
    show_rn = config.get("show_record_number", True)
    show_fields = config.get("show_fields") or []

    # Reserve space for the code(s) on the right side — SKIPPED when
    # code_mode == "none", so the text block gets the full width.
    code_area = 0
    if code_mode in ("qr_and_barcode", "qr_only"):
        qr_size = min(h - 2 * pad, 72)  # cap at 1 inch
        qr_png = make_qr_png(record.get("_qr_text") or f"/r/{record['id']}", size=256, border=1)
        c.drawImage(
            ImageReader(io.BytesIO(qr_png)),
            x + w - pad - qr_size, y_bl + (h - qr_size) / 2,
            width=qr_size, height=qr_size, preserveAspectRatio=True, mask="auto",
        )
        code_area = qr_size + pad
        text_width -= code_area
    if code_mode in ("qr_and_barcode", "barcode_only"):
        bc_h = max(18, min(h * 0.28, 42))
        bc_png = make_barcode_png(record.get("record_number") or "REC-000000",
                                  height=int(bc_h * 2), write_text=False)
        bc_w = w - 2 * pad - code_area
        c.drawImage(
            ImageReader(io.BytesIO(bc_png)),
            inner_x, y_bl + pad,
            width=bc_w, height=bc_h,
            preserveAspectRatio=True, anchor="sw", mask="auto",
        )

    # Text stacked from the top down
    cursor_y = inner_y_top
    if show_rn and record.get("record_number"):
        c.setFont("Helvetica-Bold", 8)
        cursor_y -= 9
        c.drawString(text_left, cursor_y, record["record_number"])
    if show_title and record.get("title"):
        c.setFont("Helvetica", 10)
        cursor_y -= 11
        title = record["title"]
        # simple ellipsis to fit
        max_chars = int(text_width / 5)
        if max_chars > 0 and len(title) > max_chars:
            title = title[: max_chars - 1] + "…"
        c.drawString(text_left, cursor_y, title)

    # Per-value icons (e.g. End Use → curtain / blind / upholstery). Drawn as a
    # horizontal strip under the title; wraps within the text column.
    value_icons = config.get("_value_icons") if config.get("show_value_icons") else None
    icon_pngs = config.get("_icon_pngs") or {}
    if value_icons and icon_pngs:
        record_fields = record.get("fields") or {}
        media_ids = []
        for fk, mapping in value_icons.items():
            v = record_fields.get(fk)
            vals = v if isinstance(v, list) else [v]
            for val in vals:
                mid = mapping.get(val)
                if mid and mid in icon_pngs and mid not in media_ids:
                    media_ids.append(mid)
        if media_ids:
            icon_sz = max(12, min(h * 0.22, 20))
            gap = 3
            ix = text_left
            iy_top = cursor_y - 2
            for mid in media_ids:
                if ix + icon_sz > text_left + text_width:  # wrap to next row
                    ix = text_left
                    iy_top -= icon_sz + gap
                try:
                    c.drawImage(
                        ImageReader(io.BytesIO(icon_pngs[mid])),
                        ix, iy_top - icon_sz, width=icon_sz, height=icon_sz,
                        preserveAspectRatio=True, mask="auto",
                    )
                except Exception:
                    pass
                ix += icon_sz + gap
            cursor_y = iy_top - icon_sz - 2  # push subsequent fields below icons

    # Extra fields — no cap. Use full width when code_mode="none"; otherwise
    # the text_width already excludes the reserved code column. When barcodes
    # are drawn along the bottom, reserve that band so text doesn't overlap.
    if show_fields:
        bottom_reserved = 0
        if code_mode in ("qr_and_barcode", "barcode_only"):
            bc_h = max(18, min(h * 0.28, 42))
            bottom_reserved = bc_h + pad
        field_y_bot = y_bl + pad + bottom_reserved
        entries = []
        record_fields = record.get("fields") or {}
        for fk in show_fields:
            v = record_fields.get(fk)
            if v in (None, ""):
                continue
            entries.append(f"{fk}: {v}")
        _fit_and_render_fields(
            c, x=text_left, y_top=cursor_y, y_bot=field_y_bot,
            width=text_width, entries=entries,
        )


def render_labels_pdf(records: list[dict], config: dict) -> bytes:
    preset_key = config.get("preset", "avery_5160")
    custom_preset = config.get("_custom_preset")
    if custom_preset:
        p = custom_preset
    elif preset_key in PRESETS:
        p = PRESETS[preset_key]
    else:
        raise ValueError(f"unknown preset '{preset_key}'")
    page_w, page_h = p["page_size"]
    label_w, label_h = p["label_w"], p["label_h"]
    top, left = p["top"], p["left"]
    gx, gy = p["gx"], p["gy"]
    cols, rows = p["cols"], p["rows"]
    per_page = cols * rows
    start = int(config.get("start_position", 0) or 0)
    copies = int(config.get("copies_per_record", 1) or 1)

    expanded = [r for r in records for _ in range(copies)]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.setTitle("UBOS Labels")

    slot = start
    for rec in expanded:
        page_slot = slot % per_page
        if slot > start and page_slot == 0:
            c.showPage()
        col = page_slot % cols
        row = page_slot // cols
        x = left + col * (label_w + gx)
        y = top + row * (label_h + gy)
        _draw_label(c, x, y, label_w, label_h, record=rec, config=config)
        slot += 1
    c.showPage()
    c.save()
    return buf.getvalue()


def preset_summary() -> list[dict]:
    return [
        {
            "key": k, "label": v["label_of"],
            "cols": v["cols"], "rows": v["rows"],
            "per_page": v["cols"] * v["rows"],
            "page": "Letter" if v["page_size"] == LETTER else "A4",
        }
        for k, v in PRESETS.items()
    ]
