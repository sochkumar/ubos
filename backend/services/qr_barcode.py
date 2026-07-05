"""QR + Code128 PNG helpers with a small LRU cache."""
from __future__ import annotations

import io
from functools import lru_cache

import qrcode
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
import barcode as _barcode
from barcode.writer import ImageWriter

_LEVELS = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}


@lru_cache(maxsize=500)
def _qr_cached(text: str, size: int, border: int, level: str) -> bytes:
    qr = qrcode.QRCode(
        version=None, error_correction=_LEVELS.get(level, ERROR_CORRECT_M),
        box_size=10, border=border,
    )
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((size, size))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def make_qr_png(text: str, size: int = 256, border: int = 4, level: str = "M") -> bytes:
    return _qr_cached(text, int(size), int(border), level)


@lru_cache(maxsize=500)
def _bc_cached(text: str, height: int, write_text: bool) -> bytes:
    Code128 = _barcode.get_barcode_class("code128")
    writer = ImageWriter()
    opts = {"module_height": max(6.0, height / 10.0),
            "write_text": write_text, "quiet_zone": 4}
    bc = Code128(text, writer=writer)
    buf = io.BytesIO()
    bc.write(buf, options=opts)
    return buf.getvalue()


def make_barcode_png(text: str, height: int = 80, write_text: bool = True) -> bytes:
    return _bc_cached(text, int(height), bool(write_text))
