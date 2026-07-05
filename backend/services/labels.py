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

    # Reserve space for the code(s) on the right side
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
        if len(title) > max_chars:
            title = title[: max_chars - 1] + "…"
        c.drawString(text_left, cursor_y, title)
    if show_fields:
        c.setFont("Helvetica", 7)
        for fk in show_fields[:3]:
            v = (record.get("fields") or {}).get(fk)
            if v in (None, ""):
                continue
            s = f"{fk}: {v}"
            if len(s) > int(text_width / 4):
                s = s[: int(text_width / 4) - 1] + "…"
            cursor_y -= 8.5
            if cursor_y < y_bl + 4:
                break
            c.drawString(text_left, cursor_y, s)


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
