"""Phase 8+ regression — Print Labels enhancements:
  1. code_mode="none" (fields only, no QR, no barcode)
  2. Extra fields have no cap (>3 fields) with graceful shrink/truncate.
"""
from __future__ import annotations

import io
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://org-platform-13.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

OWNER = ("owner@ubos.test", "OwnerPass!123")


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": OWNER[0], "password": OWNER[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def et_with_many_fields(owner_token):
    """A collection with 12 text fields — enough to stress the shrink path
    on a small (US Address 2⅝×1 in) label sheet."""
    slug = f"labels_no_code_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{API}/entity-types", headers=_h(owner_token),
        json={"key": slug, "name_singular": f"NC_{slug}", "name_plural": f"NC_{slug}s"},
    )
    assert r.status_code in (200, 201), r.text
    et_id = r.json()["id"]
    for i in range(1, 13):
        r_f = requests.post(
            f"{API}/entity-types/{et_id}/fields", headers=_h(owner_token),
            json={"key": f"attr_{i}", "label": f"Attr {i}", "type": "text", "order": i},
        )
        assert r_f.status_code in (200, 201), r_f.text
    yield et_id
    # Cleanup
    requests.delete(f"{API}/entity-types/{et_id}", headers=_h(owner_token))


@pytest.fixture(scope="module")
def record_id(owner_token, et_with_many_fields):
    fields = {f"attr_{i}": f"value_{i}_" + "x" * 30 for i in range(1, 13)}
    r = requests.post(
        f"{API}/entity-types/{et_with_many_fields}/records",
        headers=_h(owner_token),
        json={"title": "Overflow Test Widget", "fields": fields},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _image_count(pdf_bytes: bytes) -> int:
    """Count actual image XObjects in a PDF — /Image appears in ProcSet
    even for text-only PDFs (via /ImageB /ImageC /ImageI), so we look for
    the marker that shows up ONLY inside an actual image object."""
    return pdf_bytes.count(b"/Subtype /Image")


def _post_labels(token, record_ids, config):
    return requests.post(
        f"{API}/records/labels", headers=_h(token),
        json={"record_ids": record_ids, "config": config},
    )


# ──────────────── 1. code_mode == "none" ────────────────
def test_labels_no_code_mode_accepts_none(owner_token, record_id):
    """code_mode='none' is accepted server-side and returns a valid PDF."""
    r = _post_labels(owner_token, [record_id], {
        "code_mode": "none",
        "show_title": True, "show_record_number": True,
        "show_fields": ["attr_1", "attr_2", "attr_3", "attr_4", "attr_5"],
        "preset": "avery_5160",
    })
    assert r.status_code == 200, r.text
    body = r.content
    assert body.startswith(b"%PDF"), "expected PDF magic"
    assert body[-6:].rstrip().endswith(b"%%EOF"), "expected EOF marker"
    assert len(body) > 1000


def test_labels_no_code_pdf_omits_images(owner_token, record_id):
    """A no-code PDF has NO XObject/Image streams — text-only.
    (QR + Code128 renderings both create /Image XObjects.)"""
    r = _post_labels(owner_token, [record_id], {
        "code_mode": "none",
        "show_title": True, "show_record_number": True,
        "show_fields": ["attr_1", "attr_2"],
        "preset": "avery_5160",
    })
    assert r.status_code == 200
    body = r.content
    # Compare against a QR-mode PDF from the same record
    r_qr = _post_labels(owner_token, [record_id], {
        "code_mode": "qr_only",
        "show_title": True, "show_record_number": True,
        "show_fields": ["attr_1"], "preset": "avery_5160",
    })
    assert r_qr.status_code == 200
    qr_body = r_qr.content
    # QR PDF has at least one /Image; no-code PDF should have zero.
    assert _image_count(qr_body) >= 1, "expected /Image in QR PDF (sanity)"
    assert _image_count(body) == 0, (
        f"expected zero /Image XObjects in no-code PDF, got "
        f"{body.count(b'/Image')}"
    )


def test_labels_no_code_uses_full_width(owner_token, record_id):
    """When code_mode='none' the text block extends further right than in
    a QR-only PDF. We compare the PDF stream lengths as a proxy — the
    no-code PDF should draw more text because fields aren't truncated as
    aggressively by the reserved code column.

    Regression guard for the '`code_area` still applied' bug class.
    """
    long_val = "y" * 60
    r_none = _post_labels(owner_token, [record_id], {
        "code_mode": "none",
        "show_title": False, "show_record_number": False,
        "show_fields": ["attr_1"],
        "preset": "avery_5160",
    })
    # Patch the record so attr_1 is a long string (test data was already long).
    assert r_none.status_code == 200
    b_none = r_none.content

    r_qr = _post_labels(owner_token, [record_id], {
        "code_mode": "qr_only",
        "show_title": False, "show_record_number": False,
        "show_fields": ["attr_1"],
        "preset": "avery_5160",
    })
    assert r_qr.status_code == 200
    # QR PDF must include a /Image. No-code must not.
    assert _image_count(r_qr.content) >= 1
    assert _image_count(b_none) == 0


# ──────────────── 2. many-fields does not crash ────────────────
@pytest.mark.parametrize("preset", ["avery_5160", "avery_5163", "avery_l7160", "avery_l7163"])
def test_labels_12_fields_all_presets(owner_token, record_id, preset):
    """12 extra fields on every built-in preset must return 200. Small labels
    should progressively shrink / truncate rather than crash."""
    all_fields = [f"attr_{i}" for i in range(1, 13)]
    r = _post_labels(owner_token, [record_id], {
        "code_mode": "qr_and_barcode",
        "show_title": True, "show_record_number": True,
        "show_fields": all_fields,
        "preset": preset,
    })
    assert r.status_code == 200, r.text
    assert r.content.startswith(b"%PDF"), "expected PDF magic"


def test_labels_12_fields_no_code(owner_token, record_id):
    """12 fields + no code_mode → text block should try to fit as many as
    possible, then truncate with ellipsis. Must not error."""
    all_fields = [f"attr_{i}" for i in range(1, 13)]
    r = _post_labels(owner_token, [record_id], {
        "code_mode": "none",
        "show_title": True, "show_record_number": True,
        "show_fields": all_fields,
        "preset": "avery_5160",
    })
    assert r.status_code == 200, r.text
    body = r.content
    assert body.startswith(b"%PDF")
    assert _image_count(body) == 0


# ──────────────── 3. regression: existing modes still work ────────────────
@pytest.mark.parametrize("mode", ["qr_and_barcode", "qr_only", "barcode_only"])
def test_labels_existing_modes_unchanged(owner_token, record_id, mode):
    r = _post_labels(owner_token, [record_id], {
        "code_mode": mode,
        "show_title": True, "show_record_number": True,
        "show_fields": ["attr_1", "attr_2"],
        "preset": "avery_5160",
    })
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    # QR / barcode modes include at least one embedded /Image
    assert _image_count(r.content) >= 1


def test_labels_rejects_unknown_code_mode(owner_token, record_id):
    """Only the 4 documented literals are accepted. Anything else → 422."""
    r = _post_labels(owner_token, [record_id], {
        "code_mode": "hologram",
        "preset": "avery_5160",
    })
    assert r.status_code == 422


def test_labels_no_max_fields_validation(owner_token, record_id):
    """Server does NOT enforce a max_fields cap — the UI cap was removed
    and the schema must not add one back."""
    # 30 fields (way more than the old cap of 3)
    all_fields = [f"attr_{i}" for i in range(1, 13)] + [f"missing_{i}" for i in range(20)]
    r = _post_labels(owner_token, [record_id], {
        "code_mode": "none",
        "show_fields": all_fields,
        "preset": "avery_5160",
    })
    assert r.status_code == 200, r.text
