"""Sub-pass B PATCH tests: thumb JSON envelope contract, audit filters
(target_type/target_id), cascade_delete audit event, mime-icon public
endpoint, and fresh-org storage_quota_bytes initialisation.

These are additive to test_ubos_phase3b.py (18 base tests) and target only
the 3 patch-pass fixes.
"""
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

DEFAULT_QUOTA = 5 * 1024 * 1024 * 1024  # 5 GB (matches DEFAULT_ORG_STORAGE_QUOTA_BYTES)


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


def _png(size=32):
    img = Image.new("RGB", (size, size),
                    (uuid.uuid4().int % 256, uuid.uuid4().int % 256, uuid.uuid4().int % 256))
    img.putpixel((0, 0),
                 (uuid.uuid4().int % 256, uuid.uuid4().int % 256, uuid.uuid4().int % 256))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _upload(tok, name, data, mime):
    r = requests.post(f"{API}/media/upload", headers=_h(tok),
                      files={"files": (name, data, mime)}, timeout=30)
    assert r.status_code == 201, f"upload {name} -> {r.status_code} {r.text}"
    return r.json()[0]


@pytest.fixture(scope="module")
def owner():
    ed = _login(*EDITOR)
    tok = _login(*OWNER)
    return _switch(tok, ed["org_id"])


# ─────────────────────── FIX 1 — thumb envelope ───────────────────────
class TestThumbEnvelope:
    """/api/media/{id}/thumb must ALWAYS return {url, mime} JSON envelope,
    NEVER raw SVG bytes."""

    def test_image_thumb_envelope(self, owner):
        m = _upload(owner, "img.png", _png(48), "image/png")
        r = requests.get(f"{API}/media/{m['id']}/thumb",
                         headers=_h(owner), timeout=15)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/json")
        j = r.json()
        assert set(j.keys()) >= {"url", "mime"}
        assert j["mime"] == "image/jpeg"
        assert j["url"].startswith("/api/media/serve/") or j["url"].startswith("http")
        # Following URL yields JPEG bytes
        url = j["url"] if j["url"].startswith("http") else BASE + j["url"]
        r2 = requests.get(url, timeout=15)
        assert r2.status_code == 200
        assert r2.headers.get("content-type", "").startswith("image/jpeg")

    @pytest.mark.parametrize("filename, mime, family", [
        ("f.pdf", "application/pdf", "pdf"),
        ("f.doc", "application/msword", "doc"),
        ("f.docx",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "doc"),
        ("f.xls", "application/vnd.ms-excel", "xls"),
        ("f.xlsx",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "xls"),
        ("f.ppt", "application/vnd.ms-powerpoint", "ppt"),
        ("f.txt", "text/plain", "txt"),
        ("f.mp4", "video/mp4", "video"),
        # audio/mpeg not in default allowed_mimes → skip upload test but covered by mime-icon direct test
        ("f.bin", "application/octet-stream", "generic"),
    ])
    def test_non_image_thumb_returns_family_icon(self, owner, filename, mime, family):
        # Unique bytes to avoid cross-run dedup
        blob = os.urandom(256) + uuid.uuid4().bytes
        m = _upload(owner, filename, blob, mime)
        r = requests.get(f"{API}/media/{m['id']}/thumb",
                         headers=_h(owner), timeout=15)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/json"), \
            f"thumb for {mime} must be JSON, got {r.headers.get('content-type')}"
        j = r.json()
        assert set(j.keys()) >= {"url", "mime"}
        assert j["mime"] == "image/svg+xml"
        assert j["url"] == f"/api/media/mime-icon/{family}", j

    def test_thumb_never_returns_raw_svg(self, owner):
        # Explicit end-to-end guard: content-type is always application/json
        m = _upload(owner, "guard.pdf", b"%PDF-1.4\n" + os.urandom(200),
                    "application/pdf")
        r = requests.get(f"{API}/media/{m['id']}/thumb",
                         headers=_h(owner), timeout=15)
        assert r.status_code == 200
        assert "svg" not in r.headers.get("content-type", "").lower()
        assert r.text.lstrip().startswith("{"), \
            f"thumb body must be JSON, got: {r.text[:80]}"


# ─────────────────────── FIX 1b — /media/mime-icon/{family} public ─────
class TestMimeIconEndpoint:
    """/api/media/mime-icon/{family} must be publicly accessible (no auth)
    and return a valid SVG."""

    @pytest.mark.parametrize("family", [
        "pdf", "doc", "xls", "ppt", "txt", "video", "audio", "image", "generic",
    ])
    def test_public_no_auth(self, family):
        r = requests.get(f"{API}/media/mime-icon/{family}", timeout=15)
        assert r.status_code == 200, f"{family}: {r.status_code} {r.text[:120]}"
        assert r.headers.get("content-type", "").startswith("image/svg+xml")
        body = r.text.lstrip()
        assert body.startswith("<"), body[:80]
        assert "svg" in body.lower()

    def test_unknown_family_fallback(self):
        # Unknown family string should not 500 — falls back to generic/default
        r = requests.get(f"{API}/media/mime-icon/wibble", timeout=15)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("image/svg+xml")


# ─────────────────────── FIX 2 — audit filters ────────────────────────
class TestAuditFilters:
    def _create_et(self, owner, key_hint):
        key = f"{key_hint}_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/entity-types",
                          json={"key": key, "name_singular": key.title(),
                                "name_plural": key.title() + "s"},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 201, r.text
        return r.json()

    def _create_record(self, owner, et_id):
        r = requests.post(f"{API}/entity-types/{et_id}/records",
                          json={"fields": {}}, headers=_h(owner), timeout=15)
        assert r.status_code == 201, r.text
        return r.json()

    def test_audit_filters_action_target_type_target_id(self, owner):
        # Setup: create ET_A → ET_B cascade rel + link + delete source
        et_a = self._create_et(owner, "auda")["id"]
        et_b = self._create_et(owner, "audb")["id"]
        r = requests.post(f"{API}/entity-types/{et_a}/relationships",
                          json={"to_entity_type_id": et_b,
                                "key": f"rl_{uuid.uuid4().hex[:6]}",
                                "from_label": "kids", "to_label": "parents",
                                "cardinality": "one_to_many",
                                "cascade_delete": True},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 201, r.text
        rd = r.json()
        a = self._create_record(owner, et_a)["id"]
        b = self._create_record(owner, et_b)["id"]
        r = requests.post(f"{API}/records/{a}/relationships",
                          json={"rel_def_id": rd["id"], "target_record_id": b},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 201
        # Delete source → should produce record.cascade_deleted audit
        r = requests.delete(f"{API}/records/{a}", headers=_h(owner), timeout=15)
        assert r.status_code == 204

        # Filter by action → all entries have that action
        r = requests.get(f"{API}/audit-logs?action=record.cascade_deleted&limit=100",
                         headers=_h(owner), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["total"] >= 1, j
        for e in j["items"]:
            assert e["action"] == "record.cascade_deleted"

        # Find the one for our source record
        mine = [e for e in j["items"] if e.get("target_id") == a]
        assert mine, f"no cascade_deleted event for source={a}"
        ev = mine[0]
        assert ev["target_type"] == "record"
        assert ev["target_id"] == a
        assert ev.get("actor_id") == owner["user"]["id"] if isinstance(owner.get("user"), dict) else True
        diff = ev.get("diff") or {}
        cascaded = diff.get("cascaded_ids") or diff.get("cascaded") or []
        assert b in cascaded, f"expected {b} in cascaded_ids, diff={diff}"
        assert (diff.get("count") == len(cascaded)) or diff.get("count") is not None

        # Filter by target_id only
        r = requests.get(f"{API}/audit-logs?target_id={a}",
                         headers=_h(owner), timeout=15)
        assert r.status_code == 200
        j2 = r.json()
        assert j2["total"] >= 1
        for e in j2["items"]:
            assert e["target_id"] == a

        # Filter by target_type=record
        r = requests.get(f"{API}/audit-logs?target_type=record&limit=5",
                         headers=_h(owner), timeout=15)
        assert r.status_code == 200
        for e in r.json()["items"]:
            assert e["target_type"] == "record"

        # Combine action + target_id → narrows to exactly our entry
        r = requests.get(
            f"{API}/audit-logs?action=record.cascade_deleted&target_id={a}",
            headers=_h(owner), timeout=15)
        assert r.status_code == 200
        j3 = r.json()
        assert j3["total"] >= 1
        for e in j3["items"]:
            assert e["action"] == "record.cascade_deleted"
            assert e["target_id"] == a


# ─────────────────────── BONUS — fresh org quota ──────────────────────
class TestFreshOrgQuota:
    def test_new_org_has_default_storage_quota(self, fresh_org):
        """A newly-created org must ship with the default storage quota.

        Uses the `fresh_org` fixture (a brand-new user + org) instead of the
        shared Acme owner: creating an org via `POST /api/orgs` sets the
        caller's `default_org_id`, so previously this test poisoned owner's
        active org and made downstream tests (Phase 2 templates etc.) flaky.
        """
        # The fresh_org fixture already gave us a newly-created org.
        oid = fresh_org.org_id
        r = requests.get(f"{API}/orgs/{oid}", headers=fresh_org.h(), timeout=15)
        assert r.status_code == 200, r.text
        got = r.json()
        assert (got.get("settings") or {}).get("storage_quota_bytes") == DEFAULT_QUOTA, got

        # Media storage for the fresh org reflects the same quota.
        r = requests.get(f"{API}/media/storage", headers=fresh_org.h(), timeout=15)
        assert r.status_code == 200, r.text
        st = r.json()
        assert st.get("quota_bytes") == DEFAULT_QUOTA, st
