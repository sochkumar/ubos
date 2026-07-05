"""Phase 3 Sub-pass B backend tests: media (upload/dedup/thumb/serve/quota),
relationship instances (link/unlink/cardinality/cascade), image/file field
validation, org storage-quota admin.

Follows the phase3a pattern (pytest-xdist loadscope; module-scope fixtures)."""
from __future__ import annotations

import io
import os
import uuid
import pytest
import requests
from PIL import Image

BASE = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://org-platform-13.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE}/api"

OWNER = ("owner@ubos.test", "OwnerPass!123")
EDITOR = ("editor@ubos.test", "EditorPass!123")
VIEWER = ("viewer@ubos.test", "ViewerPass!123")

DEFAULT_QUOTA = 5 * 1024 * 1024 * 1024  # 5 GB


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return r.json()


def _h(tok):
    return {"Authorization": f"Bearer {tok['access_token']}"}


def _switch(tok, org_id):
    r = requests.post(f"{API}/orgs/{org_id}/switch", headers=_h(tok), timeout=15)
    if r.status_code == 200:
        return r.json()
    return tok


def _png_bytes(size_px=32, color=None):
    if color is None:
        color = (uuid.uuid4().int % 256, uuid.uuid4().int % 256, uuid.uuid4().int % 256)
    img = Image.new("RGB", (size_px, size_px), color)
    # Randomize a pixel to guarantee unique bytes across test runs (avoids org-scoped dedup)
    img.putpixel((0, 0), (uuid.uuid4().int % 256,
                          uuid.uuid4().int % 256,
                          uuid.uuid4().int % 256))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─────────── shared fixtures ───────────
@pytest.fixture(scope="module")
def owner():
    ed = _login(*EDITOR)
    tok = _login(*OWNER)
    return _switch(tok, ed["org_id"])


@pytest.fixture(scope="module")
def editor():
    return _login(*EDITOR)


@pytest.fixture(scope="module")
def viewer():
    return _login(*VIEWER)


@pytest.fixture(scope="module")
def et_id(owner):
    requests.post(f"{API}/dev/seed-demo", headers=_h(owner), timeout=60)
    r = requests.get(f"{API}/entity-types", headers=_h(owner), timeout=15)
    assert r.status_code == 200
    products = next((e for e in r.json() if e["key"] == "products"), None)
    assert products
    return products["id"]


@pytest.fixture(scope="module", autouse=True)
def _restore_quota(owner):
    """Ensure default quota is restored after the module finishes."""
    yield
    # best-effort reset — org id from a login
    ed = _login(*EDITOR)
    requests.patch(f"{API}/orgs/{ed['org_id']}/storage-quota",
                   json={"storage_quota_bytes": DEFAULT_QUOTA},
                   headers=_h(owner), timeout=15)


# ─────────────────────────── MEDIA CORE ───────────────────────────
class TestMediaCore:
    def test_upload_dedup_thumb_serve(self, owner):
        # baseline
        r = requests.get(f"{API}/media/storage", headers=_h(owner), timeout=15)
        assert r.status_code == 200
        used0 = r.json()["used_bytes"]

        png = _png_bytes(48)
        size = len(png)
        assert 100 < size < 20_000  # small PNG

        # 1st upload
        r = requests.post(
            f"{API}/media/upload", headers=_h(owner),
            files={"files": ("test.png", png, "image/png")}, timeout=30,
        )
        assert r.status_code == 201, r.text
        items = r.json()
        assert isinstance(items, list) and len(items) == 1
        m1 = items[0]
        assert m1["mime"] == "image/png"
        assert m1["size"] == size
        assert m1["checksum"]
        assert m1.get("width") and m1.get("height")
        assert m1["storage_key"]
        mid = m1["id"]

        # storage bumped
        r = requests.get(f"{API}/media/storage", headers=_h(owner), timeout=15)
        used1 = r.json()["used_bytes"]
        assert used1 == used0 + size, f"expected +{size}, got {used1 - used0}"

        # 2nd upload same bytes → dedup: same id, quota unchanged
        r = requests.post(
            f"{API}/media/upload", headers=_h(owner),
            files={"files": ("test-dup.png", png, "image/png")}, timeout=30,
        )
        assert r.status_code == 201
        m_dup = r.json()[0]
        assert m_dup["id"] == mid, "dedup should return same media_id"
        used2 = requests.get(f"{API}/media/storage", headers=_h(owner), timeout=15).json()["used_bytes"]
        assert used2 == used1, "dedup must not double-count quota"

        # Thumb → returns {url}
        r = requests.get(f"{API}/media/{mid}/thumb", headers=_h(owner), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "url" in j and "/api/media/serve/" in j["url"]
        # 2nd hit uses cached thumb_key: still 200, still json
        r2 = requests.get(f"{API}/media/{mid}/thumb", headers=_h(owner), timeout=15)
        assert r2.status_code == 200 and "url" in r2.json()

        # Serve token → jpeg (URL may be relative to backend)
        thumb_url = j["url"]
        if thumb_url.startswith("/"):
            thumb_url = BASE + thumb_url
        r = requests.get(thumb_url, timeout=15)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/jpeg")

        # /file returns url + metadata; hitting url streams the file
        r = requests.get(f"{API}/media/{mid}/file", headers=_h(owner), timeout=15)
        assert r.status_code == 200
        f = r.json()
        assert f["filename"] and f["mime"] == "image/png" and f["size"] == size
        r = requests.get(f["url"] if f["url"].startswith("http") else BASE + f["url"], timeout=15)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")
        assert "content-disposition" in {k.lower() for k in r.headers.keys()}

    def test_pdf_thumb_returns_svg_icon(self, owner):
        pdf_bytes = b"%PDF-1.4\n%stub\n" + b"0" * 200
        r = requests.post(f"{API}/media/upload", headers=_h(owner),
                          files={"files": ("stub.pdf", pdf_bytes, "application/pdf")}, timeout=30)
        assert r.status_code == 201, r.text
        mid = r.json()[0]["id"]
        r = requests.get(f"{API}/media/{mid}/thumb", headers=_h(owner), timeout=15)
        assert r.status_code == 200
        # Sub-pass B patch: thumb is now ALWAYS a JSON envelope, not raw SVG
        assert r.headers.get("content-type", "").startswith("application/json"), r.headers
        j = r.json()
        assert set(["url", "mime"]).issubset(j.keys())
        assert j["url"] == "/api/media/mime-icon/pdf"
        assert j["mime"] == "image/svg+xml"
        # Follow the URL (no auth required) → SVG bytes
        r2 = requests.get(BASE + j["url"], timeout=15)
        assert r2.status_code == 200
        assert r2.headers.get("content-type", "").startswith("image/svg+xml")
        assert r2.content.lstrip().startswith(b"<")

    def test_svg_upload_rejected(self, owner):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        r = requests.post(f"{API}/media/upload", headers=_h(owner),
                          files={"files": ("x.svg", svg, "image/svg+xml")}, timeout=15)
        assert r.status_code == 415, r.text


# ─────────────────────────── QUOTAS & RBAC ───────────────────────────
class TestQuotaAndRBAC:
    def test_quota_exceeded_413(self, owner):
        org_id = owner["org_id"]
        MIN_QUOTA = 100 * 1024 * 1024   # 100 MB (backend minimum)
        MAX_UPLOAD = 25 * 1024 * 1024   # per file cap

        # Pre-fill until used >= MIN_QUOTA (so we can set quota == MIN_QUOTA and any upload overflows)
        used0 = requests.get(f"{API}/media/storage", headers=_h(owner), timeout=15).json()["used_bytes"]
        target = MIN_QUOTA + 2 * 1024 * 1024  # 102 MB
        # First, raise quota high enough to allow the pre-fill (in case default was lowered previously)
        requests.patch(f"{API}/orgs/{org_id}/storage-quota",
                       json={"storage_quota_bytes": DEFAULT_QUOTA},
                       headers=_h(owner), timeout=15)
        blob_size = 20 * 1024 * 1024  # 20 MB (under MAX_UPLOAD)
        cur = used0
        safety = 0
        while cur < target and safety < 8:
            blob = os.urandom(blob_size)  # unique bytes each iteration (no dedup)
            r = requests.post(f"{API}/media/upload", headers=_h(owner),
                              files={"files": (f"fill-{safety}.bin", blob, "application/octet-stream")},
                              timeout=120)
            assert r.status_code == 201, r.text
            cur = requests.get(f"{API}/media/storage", headers=_h(owner), timeout=15).json()["used_bytes"]
            safety += 1
        assert cur >= MIN_QUOTA, f"could not pre-fill above {MIN_QUOTA}, at {cur}"

        # Now shrink quota to MIN — remaining is negative
        r = requests.patch(f"{API}/orgs/{org_id}/storage-quota",
                           json={"storage_quota_bytes": MIN_QUOTA},
                           headers=_h(owner), timeout=15)
        assert r.status_code == 200

        cur_used = requests.get(f"{API}/media/storage", headers=_h(owner), timeout=15).json()["used_bytes"]
        # Any small unique blob should overflow
        small = os.urandom(500 * 1024)  # 500 KB
        r = requests.post(f"{API}/media/upload", headers=_h(owner),
                          files={"files": ("over.bin", small, "application/octet-stream")}, timeout=60)
        assert r.status_code == 413, r.text
        body = r.json()
        detail = body.get("detail")
        assert isinstance(detail, dict) and detail.get("code") == "quota_exceeded", detail
        used_after = requests.get(f"{API}/media/storage",
                                  headers=_h(owner), timeout=15).json()["used_bytes"]
        assert used_after == cur_used, "no partial write on quota overflow"

        # restore
        r = requests.patch(f"{API}/orgs/{org_id}/storage-quota",
                           json={"storage_quota_bytes": DEFAULT_QUOTA},
                           headers=_h(owner), timeout=15)
        assert r.status_code == 200

    def test_max_upload_size_file_too_large(self, owner):
        # 30 MB blob > MAX_UPLOAD_SIZE_BYTES (25 MB)
        blob = os.urandom(30 * 1024 * 1024)
        r = requests.post(f"{API}/media/upload", headers=_h(owner),
                          files={"files": ("huge.bin", blob, "application/octet-stream")}, timeout=120)
        assert r.status_code == 413, r.text
        body = r.json()
        detail = body.get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "file_too_large", detail

    def test_rbac_viewer_editor_media(self, viewer, editor):
        png = _png_bytes(24)
        # viewer cannot upload
        rv = requests.post(f"{API}/media/upload", headers=_h(viewer),
                           files={"files": ("v.png", png, "image/png")}, timeout=15)
        assert rv.status_code == 403, rv.text

        # editor CAN upload
        re_ = requests.post(f"{API}/media/upload", headers=_h(editor),
                            files={"files": ("e.png", png, "image/png")}, timeout=15)
        assert re_.status_code == 201, re_.text
        mid = re_.json()[0]["id"]

        # viewer cannot delete
        rvd = requests.delete(f"{API}/media/{mid}", headers=_h(viewer), timeout=15)
        assert rvd.status_code == 403

        # viewer cannot attach
        rva = requests.post(f"{API}/media/{mid}/attach", json={"record_id": "x"},
                            headers=_h(viewer), timeout=15)
        assert rva.status_code == 403

        # editor CAN delete
        red = requests.delete(f"{API}/media/{mid}", headers=_h(editor), timeout=15)
        assert red.status_code == 204


# ─────────────────────── IMAGE/FILE FIELD VALIDATION ───────────────────────
@pytest.fixture(scope="module")
def image_field(owner, et_id):
    # create image field 'cover' (multiple=false)
    key = f"cover_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/entity-types/{et_id}/fields",
                      json={"key": key, "label": "Cover", "type": "image",
                            "config": {"multiple": False}},
                      headers=_h(owner), timeout=15)
    assert r.status_code == 201, r.text
    return r.json()  # has 'id', 'key'


@pytest.fixture(scope="module")
def pdf_field(owner, et_id):
    key = f"docs_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/entity-types/{et_id}/fields",
                      json={"key": key, "label": "Docs", "type": "file",
                            "config": {"multiple": True, "allowed_mimes": ["application/pdf"]}},
                      headers=_h(owner), timeout=15)
    assert r.status_code == 201, r.text
    return r.json()


def _upload_png(tok):
    png = _png_bytes(32, color=(uuid.uuid4().int % 200, 10, 10))
    # make bytes unique to avoid dedup with global tests
    png = png + os.urandom(16)
    r = requests.post(f"{API}/media/upload", headers=_h(tok),
                      files={"files": ("x.png", png, "image/png")}, timeout=30)
    assert r.status_code == 201, r.text
    return r.json()[0]


def _upload_pdf(tok):
    pdf = b"%PDF-1.4\n" + os.urandom(300)
    r = requests.post(f"{API}/media/upload", headers=_h(tok),
                      files={"files": ("d.pdf", pdf, "application/pdf")}, timeout=30)
    assert r.status_code == 201, r.text
    return r.json()[0]


class TestImageFileFields:
    def test_image_field_lifecycle(self, owner, et_id, image_field):
        media = _upload_png(owner)
        # create record with cover
        r = requests.post(
            f"{API}/entity-types/{et_id}/records",
            json={"fields": {"sku": f"T-{uuid.uuid4().hex[:6]}", "price": 5.0,
                             image_field["key"]: {"media_id": media["id"]}}},
            headers=_h(owner), timeout=15,
        )
        assert r.status_code == 201, r.text
        rec = r.json()
        rid = rec["id"]
        cover = (rec.get("fields") or {}).get(image_field["key"])
        assert isinstance(cover, dict) and cover.get("media_id") == media["id"]

        # media.attached_to now includes the record
        m = requests.get(f"{API}/media/{media['id']}", headers=_h(owner), timeout=15).json()
        assert any(a.get("record_id") == rid and a.get("field_key") == image_field["key"]
                   and a.get("role") == "field" for a in (m.get("attached_to") or [])), m

        # PATCH cover:null → detached
        r = requests.patch(f"{API}/records/{rid}",
                           json={"fields": {image_field["key"]: None}},
                           headers=_h(owner), timeout=15)
        assert r.status_code == 200, r.text
        m2 = requests.get(f"{API}/media/{media['id']}", headers=_h(owner), timeout=15).json()
        assert not any(a.get("record_id") == rid and a.get("field_key") == image_field["key"]
                       for a in (m2.get("attached_to") or []))

    def test_image_validation_errors(self, owner, et_id, image_field):
        # non-existent media_id
        r = requests.post(
            f"{API}/entity-types/{et_id}/records",
            json={"fields": {"sku": f"T-{uuid.uuid4().hex[:6]}", "price": 5.0,
                             image_field["key"]: {"media_id": "ghost-media"}}},
            headers=_h(owner), timeout=15,
        )
        assert r.status_code == 422, r.text
        assert "does not exist" in r.text.lower() or "not exist" in r.text.lower()

        # pdf pointing at image field → 'is not an image'
        pdf = _upload_pdf(owner)
        r = requests.post(
            f"{API}/entity-types/{et_id}/records",
            json={"fields": {"sku": f"T-{uuid.uuid4().hex[:6]}", "price": 5.0,
                             image_field["key"]: {"media_id": pdf["id"]}}},
            headers=_h(owner), timeout=15,
        )
        assert r.status_code == 422, r.text
        assert "image" in r.text.lower()

    def test_file_field_mime_restriction(self, owner, et_id, pdf_field):
        # png on pdf-only field → 422
        png = _upload_png(owner)
        # create record first
        r = requests.post(
            f"{API}/entity-types/{et_id}/records",
            json={"fields": {"sku": f"T-{uuid.uuid4().hex[:6]}", "price": 5.0}},
            headers=_h(owner), timeout=15,
        )
        rid = r.json()["id"]
        r = requests.patch(
            f"{API}/records/{rid}",
            json={"fields": {pdf_field["key"]: [{"media_id": png["id"]}]}},
            headers=_h(owner), timeout=15,
        )
        assert r.status_code == 422, r.text
        assert "mime" in r.text.lower() or "allowed" in r.text.lower()


class TestMediaDeleteCascade:
    def test_delete_attached_conflict_and_cascade(self, owner, et_id, image_field):
        media = _upload_png(owner)
        r = requests.post(
            f"{API}/entity-types/{et_id}/records",
            json={"fields": {"sku": f"T-{uuid.uuid4().hex[:6]}", "price": 3.0,
                             image_field["key"]: {"media_id": media["id"]}}},
            headers=_h(owner), timeout=15,
        )
        assert r.status_code == 201
        rid = r.json()["id"]

        # DELETE without cascade → 409
        r = requests.delete(f"{API}/media/{media['id']}", headers=_h(owner), timeout=15)
        assert r.status_code == 409, r.text
        body = r.json()
        assert body.get("detail", {}).get("code") == "media_in_use"

        # baseline used_bytes before cascade
        used_before = requests.get(f"{API}/media/storage",
                                   headers=_h(owner), timeout=15).json()["used_bytes"]
        # DELETE with cascade → 204
        r = requests.delete(f"{API}/media/{media['id']}?cascade=true",
                            headers=_h(owner), timeout=15)
        assert r.status_code == 204, r.text

        # record.fields.<key> cleared
        rec = requests.get(f"{API}/records/{rid}", headers=_h(owner), timeout=15).json()
        assert (rec.get("fields") or {}).get(image_field["key"]) in (None, {}, [])

        # quota refunded
        used_after = requests.get(f"{API}/media/storage",
                                  headers=_h(owner), timeout=15).json()["used_bytes"]
        assert used_after <= used_before, f"quota not refunded: before={used_before}, after={used_after}"


# ─────────────────────── RELATIONSHIP INSTANCES ───────────────────────
def _create_et(owner, key_hint):
    key = f"{key_hint}_{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/entity-types",
                      json={"key": key, "name_singular": key.title(),
                            "name_plural": key.title() + "s"},
                      headers=_h(owner), timeout=15)
    assert r.status_code == 201, r.text
    return r.json()


def _create_record(owner, et_id):
    r = requests.post(f"{API}/entity-types/{et_id}/records",
                      json={"fields": {}}, headers=_h(owner), timeout=15)
    assert r.status_code == 201, r.text
    return r.json()


def _create_rel_def(owner, from_et, to_et, card, cascade=False):
    key = f"rl_{uuid.uuid4().hex[:6]}"
    r = requests.post(
        f"{API}/entity-types/{from_et}/relationships",
        json={"to_entity_type_id": to_et, "key": key,
              "from_label": "targets", "to_label": "sources",
              "cardinality": card, "cascade_delete": cascade},
        headers=_h(owner), timeout=15,
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestRelationshipInstances:
    def test_one_to_many(self, owner):
        et_a = _create_et(owner, "eta")["id"]
        et_b = _create_et(owner, "etb")["id"]
        rd = _create_rel_def(owner, et_a, et_b, "one_to_many")
        a1 = _create_record(owner, et_a)["id"]
        a2 = _create_record(owner, et_a)["id"]
        b1 = _create_record(owner, et_b)["id"]
        b2 = _create_record(owner, et_b)["id"]
        # a1→b1
        r = requests.post(f"{API}/records/{a1}/relationships",
                         json={"rel_def_id": rd["id"], "target_record_id": b1},
                         headers=_h(owner), timeout=15)
        assert r.status_code == 201, r.text
        # a1→b2 (source can have many)
        r = requests.post(f"{API}/records/{a1}/relationships",
                         json={"rel_def_id": rd["id"], "target_record_id": b2},
                         headers=_h(owner), timeout=15)
        assert r.status_code == 201, r.text
        # a2→b1 (target already linked)
        r = requests.post(f"{API}/records/{a2}/relationships",
                         json={"rel_def_id": rd["id"], "target_record_id": b1},
                         headers=_h(owner), timeout=15)
        assert r.status_code == 409, r.text

        # GET a1 relationships
        r = requests.get(f"{API}/records/{a1}/relationships", headers=_h(owner), timeout=15)
        assert r.status_code == 200
        g = r.json()["groups"]
        grp = next((x for x in g if x["rel_def_id"] == rd["id"] and x["direction"] == "from"), None)
        assert grp and len(grp["items"]) == 2

        # GET b1 shows 1 item, direction='to'
        r = requests.get(f"{API}/records/{b1}/relationships", headers=_h(owner), timeout=15)
        g = r.json()["groups"]
        grp = next((x for x in g if x["rel_def_id"] == rd["id"] and x["direction"] == "to"), None)
        assert grp and len(grp["items"]) == 1

    def test_one_to_one(self, owner):
        et_a = _create_et(owner, "eta1")["id"]
        et_b = _create_et(owner, "etb1")["id"]
        rd = _create_rel_def(owner, et_a, et_b, "one_to_one")
        a1 = _create_record(owner, et_a)["id"]
        a2 = _create_record(owner, et_a)["id"]
        b1 = _create_record(owner, et_b)["id"]
        b2 = _create_record(owner, et_b)["id"]
        # a1↔b1
        r = requests.post(f"{API}/records/{a1}/relationships",
                          json={"rel_def_id": rd["id"], "target_record_id": b1},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 201
        # a1↔b2 → 409 (source already linked)
        r = requests.post(f"{API}/records/{a1}/relationships",
                          json={"rel_def_id": rd["id"], "target_record_id": b2},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 409
        # a2↔b1 → 409 (target already linked)
        r = requests.post(f"{API}/records/{a2}/relationships",
                          json={"rel_def_id": rd["id"], "target_record_id": b1},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 409

    def test_many_to_many(self, owner):
        et_a = _create_et(owner, "eta2")["id"]
        et_b = _create_et(owner, "etb2")["id"]
        rd = _create_rel_def(owner, et_a, et_b, "many_to_many")
        a1 = _create_record(owner, et_a)["id"]
        a2 = _create_record(owner, et_a)["id"]
        b1 = _create_record(owner, et_b)["id"]
        for src, tgt in [(a1, b1), (a2, b1), (a1, b1)]:  # last is idempotent
            r = requests.post(f"{API}/records/{src}/relationships",
                              json={"rel_def_id": rd["id"], "target_record_id": tgt},
                              headers=_h(owner), timeout=15)
            assert r.status_code == 201, r.text

    def test_cascade_delete(self, owner):
        et_a = _create_et(owner, "casa")["id"]
        et_b = _create_et(owner, "casb")["id"]
        rd = _create_rel_def(owner, et_a, et_b, "one_to_many", cascade=True)
        a1 = _create_record(owner, et_a)["id"]
        b1 = _create_record(owner, et_b)["id"]
        r = requests.post(f"{API}/records/{a1}/relationships",
                          json={"rel_def_id": rd["id"], "target_record_id": b1},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 201
        # delete source
        r = requests.delete(f"{API}/records/{a1}", headers=_h(owner), timeout=15)
        assert r.status_code == 204
        # target should be soft-deleted → GET returns 404
        r = requests.get(f"{API}/records/{b1}", headers=_h(owner), timeout=15)
        assert r.status_code == 404, r.text

    def test_unlink_idempotent(self, owner):
        et_a = _create_et(owner, "uxa")["id"]
        et_b = _create_et(owner, "uxb")["id"]
        rd = _create_rel_def(owner, et_a, et_b, "many_to_many")
        a1 = _create_record(owner, et_a)["id"]
        b1 = _create_record(owner, et_b)["id"]
        requests.post(f"{API}/records/{a1}/relationships",
                      json={"rel_def_id": rd["id"], "target_record_id": b1},
                      headers=_h(owner), timeout=15)
        r = requests.delete(
            f"{API}/records/{a1}/relationships/{b1}?rel_def_id={rd['id']}",
            headers=_h(owner), timeout=15)
        assert r.status_code == 204
        # both sides cleared
        gA = requests.get(f"{API}/records/{a1}/relationships",
                          headers=_h(owner), timeout=15).json()
        gB = requests.get(f"{API}/records/{b1}/relationships",
                          headers=_h(owner), timeout=15).json()
        assert not any(rd["id"] == x["rel_def_id"] for x in gA["groups"])
        assert not any(rd["id"] == x["rel_def_id"] for x in gB["groups"])
        # idempotent
        r = requests.delete(
            f"{API}/records/{a1}/relationships/{b1}?rel_def_id={rd['id']}",
            headers=_h(owner), timeout=15)
        assert r.status_code == 204

    def test_rbac_viewer_cannot_link(self, owner, viewer):
        et_a = _create_et(owner, "rba")["id"]
        et_b = _create_et(owner, "rbb")["id"]
        rd = _create_rel_def(owner, et_a, et_b, "one_to_many")
        a1 = _create_record(owner, et_a)["id"]
        b1 = _create_record(owner, et_b)["id"]
        r = requests.post(f"{API}/records/{a1}/relationships",
                          json={"rel_def_id": rd["id"], "target_record_id": b1},
                          headers=_h(viewer), timeout=15)
        assert r.status_code == 403


# ─────────────────────── ORG STORAGE-QUOTA ADMIN ───────────────────────
class TestStorageQuotaAdmin:
    def test_editor_cannot_change_quota(self, owner, editor):
        org_id = owner["org_id"]
        r = requests.patch(f"{API}/orgs/{org_id}/storage-quota",
                           json={"storage_quota_bytes": DEFAULT_QUOTA},
                           headers=_h(editor), timeout=15)
        assert r.status_code == 403

    def test_owner_can_change_quota(self, owner):
        org_id = owner["org_id"]
        r = requests.patch(f"{API}/orgs/{org_id}/storage-quota",
                           json={"storage_quota_bytes": DEFAULT_QUOTA},
                           headers=_h(owner), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert (j.get("storage_quota_bytes")
                or (j.get("settings") or {}).get("storage_quota_bytes")) == DEFAULT_QUOTA
