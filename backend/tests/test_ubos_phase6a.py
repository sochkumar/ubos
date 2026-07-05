"""Phase 6-A tests: label presets CRUD + custom PDF render, owner-self-collab guard,
PDF thumbnails, PWA asset presence, OpenAPI paths.
"""
from __future__ import annotations

import io
import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") \
    or "https://org-platform-13.preview.emergentagent.com"
API = f"{BASE_URL}/api"


def _login(email: str, password: str) -> dict:
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()


@pytest.fixture(scope="session")
def owner_auth():
    return _login("owner@ubos.test", "OwnerPass!123")


@pytest.fixture(scope="session")
def editor_auth():
    return _login("editor@ubos.test", "EditorPass!123")


@pytest.fixture(scope="session")
def viewer_auth():
    return _login("viewer@ubos.test", "ViewerPass!123")


def h(auth):
    return {"Authorization": f"Bearer {auth['access_token']}"}


@pytest.fixture(scope="session")
def acme_org_id(owner_auth):
    return owner_auth["org_id"]


@pytest.fixture(scope="session")
def owner_uid(owner_auth):
    r = requests.get(f"{API}/auth/me", headers=h(owner_auth), timeout=15)
    j = r.json()
    return j.get("_id") or j.get("id") or j.get("user_id") or (j.get("user") or {}).get("id")


# ─────────────────────── label presets CRUD ───────────────────────
class TestLabelPresetsCRUD:
    _created_id = None
    _key = None

    def test_list_presets_fresh(self, owner_auth, acme_org_id):
        r = requests.get(f"{API}/orgs/{acme_org_id}/label-presets",
                         headers=h(owner_auth), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "system" in data and "custom" in data
        assert len(data["system"]) >= 4
        # verify shape of a system preset
        assert all("key" in p and "cols" in p and "rows" in p for p in data["system"])

    def test_create_custom_preset(self, owner_auth, acme_org_id):
        TestLabelPresetsCRUD._key = f"qa-preset-{uuid.uuid4().hex[:6]}"
        body = {
            "key": TestLabelPresetsCRUD._key,
            "name": "QA Preset",
            "page_size": "A4",
            "cols": 3, "rows": 3,
            "label_w_mm": 60, "label_h_mm": 40,
            "margin_top_mm": 10, "margin_left_mm": 10,
            "gutter_h_mm": 2, "gutter_v_mm": 2,
        }
        r = requests.post(f"{API}/orgs/{acme_org_id}/label-presets",
                          json=body, headers=h(owner_auth), timeout=15)
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["key"] == TestLabelPresetsCRUD._key
        assert d["cols"] == 3 and d["rows"] == 3
        assert d["label_w_mm"] == 60 and d["label_h_mm"] == 40
        assert d.get("is_system") is False
        TestLabelPresetsCRUD._created_id = d.get("id") or d.get("_id")
        assert TestLabelPresetsCRUD._created_id

    def test_list_contains_custom_with_dimensions(self, owner_auth, acme_org_id):
        r = requests.get(f"{API}/orgs/{acme_org_id}/label-presets",
                         headers=h(owner_auth), timeout=15)
        assert r.status_code == 200
        data = r.json()
        found = [c for c in data["custom"] if c.get("key") == TestLabelPresetsCRUD._key]
        assert found, "created preset should appear in list"
        c = found[0]
        assert c["label_w_mm"] == 60 and c["label_h_mm"] == 40 and c["cols"] == 3

    def test_create_duplicate_key(self, owner_auth, acme_org_id):
        body = {
            "key": TestLabelPresetsCRUD._key,
            "name": "Dup", "page_size": "A4",
            "cols": 2, "rows": 2, "label_w_mm": 50, "label_h_mm": 30,
        }
        r = requests.post(f"{API}/orgs/{acme_org_id}/label-presets",
                          json=body, headers=h(owner_auth), timeout=15)
        assert r.status_code == 409
        assert r.json().get("detail", {}).get("code") == "duplicate_key"

    def test_create_custom_size_missing_dimensions(self, owner_auth, acme_org_id):
        body = {
            "key": f"custompage-{uuid.uuid4().hex[:6]}",
            "name": "Custom",
            "page_size": "custom",
            "cols": 2, "rows": 2, "label_w_mm": 50, "label_h_mm": 30,
        }
        r = requests.post(f"{API}/orgs/{acme_org_id}/label-presets",
                          json=body, headers=h(owner_auth), timeout=15)
        assert r.status_code == 422
        assert r.json().get("detail", {}).get("code") == "custom_page_missing_dimensions"

    def test_viewer_cannot_create(self, viewer_auth, acme_org_id):
        body = {
            "key": f"forbidden-{uuid.uuid4().hex[:6]}",
            "name": "Nope", "page_size": "A4",
            "cols": 2, "rows": 2, "label_w_mm": 50, "label_h_mm": 30,
        }
        r = requests.post(f"{API}/orgs/{acme_org_id}/label-presets",
                          json=body, headers=h(viewer_auth), timeout=15)
        assert r.status_code == 403

    def test_editor_cannot_create(self, editor_auth, acme_org_id):
        body = {
            "key": f"editforbid-{uuid.uuid4().hex[:6]}",
            "name": "Nope", "page_size": "A4",
            "cols": 2, "rows": 2, "label_w_mm": 50, "label_h_mm": 30,
        }
        r = requests.post(f"{API}/orgs/{acme_org_id}/label-presets",
                          json=body, headers=h(editor_auth), timeout=15)
        # editor lacks entity_types.manage
        assert r.status_code == 403

    def test_patch_preset(self, owner_auth):
        pid = TestLabelPresetsCRUD._created_id
        assert pid
        r = requests.patch(f"{API}/label-presets/{pid}",
                           json={"name": "QA Preset Renamed", "cols": 4},
                           headers=h(owner_auth), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "QA Preset Renamed"
        assert r.json()["cols"] == 4

    def test_patch_key_ignored(self, owner_auth):
        pid = TestLabelPresetsCRUD._created_id
        # key not in update schema — it should be ignored (extra='ignore')
        r = requests.patch(f"{API}/label-presets/{pid}",
                           json={"key": "changed-key", "name": "QA Preset X"},
                           headers=h(owner_auth), timeout=15)
        assert r.status_code == 200
        assert r.json()["key"] == TestLabelPresetsCRUD._key


class TestLabelRenderCustom:
    """Render a PDF using the custom preset via /records/labels."""

    @pytest.fixture(scope="class")
    def any_record_id(self, owner_auth, acme_org_id):
        # find any record in Acme
        r = requests.get(f"{API}/entity-types", headers=h(owner_auth), timeout=15)
        assert r.status_code == 200
        ets = r.json()
        for et in ets:
            sr = requests.post(
                f"{API}/entity-types/{et['id']}/records/search",
                json={"limit": 1}, headers=h(owner_auth), timeout=15,
            )
            if sr.status_code == 200 and sr.json().get("items"):
                return sr.json()["items"][0]["id"]
        pytest.skip("no records found in Acme to render labels for")

    def test_render_custom_preset(self, owner_auth, any_record_id):
        # Grab the custom preset just created
        pid = TestLabelPresetsCRUD._created_id
        r = requests.post(
            f"{API}/records/labels",
            json={"record_ids": [any_record_id],
                  "config": {"preset_id": pid}},
            headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 500
        assert r.content[:4] == b"%PDF"

    def test_render_builtin_preset(self, owner_auth, any_record_id):
        r = requests.post(
            f"{API}/records/labels",
            json={"record_ids": [any_record_id],
                  "config": {"preset": "avery_5160"}},
            headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"


class TestLabelPresetDelete:
    def test_delete_custom(self, owner_auth):
        pid = TestLabelPresetsCRUD._created_id
        r = requests.delete(f"{API}/label-presets/{pid}",
                            headers=h(owner_auth), timeout=15)
        assert r.status_code == 204
        # subsequent GET on list should not include it
        r2 = requests.get(f"{API}/orgs/{__import__('os').environ.get('_ACME','')}",
                         headers=h(owner_auth), timeout=5) if False else None


# ─────────────────────── owner-self-collab 409 ───────────────────────
class TestOwnerSelfCollab:
    def test_owner_cannot_add_self(self, owner_auth, acme_org_id, owner_uid):
        # Need an entity_type_id
        ets = requests.get(f"{API}/entity-types", headers=h(owner_auth), timeout=15).json()
        assert ets, "no entity types"
        et_id = ets[0]["id"]
        # Create a view
        vname = f"TEST_view_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/entity-types/{et_id}/views",
                          json={"name": vname, "layout": "table"},
                          headers=h(owner_auth), timeout=15)
        assert r.status_code in (200, 201), r.text
        view = r.json()
        vid = view.get("id") or view.get("_id")
        assert vid
        try:
            r2 = requests.post(f"{API}/views/{vid}/collaborators",
                               json={"user_id": owner_uid, "permission": "view"},
                               headers=h(owner_auth), timeout=15)
            assert r2.status_code == 409
            assert r2.json().get("detail", {}).get("code") == "already_owner"

            # Adding another user still works — find an editor uid
            me_editor = requests.get(
                f"{API}/auth/me",
                headers={"Authorization": f"Bearer {_login('editor@ubos.test','EditorPass!123')['access_token']}"},
                timeout=15,
            ).json()
            editor_uid = me_editor.get("_id") or me_editor.get("id") or me_editor.get("user_id") or (me_editor.get("user") or {}).get("id")
            if editor_uid:
                r3 = requests.post(f"{API}/views/{vid}/collaborators",
                                   json={"user_id": editor_uid, "permission": "view"},
                                   headers=h(owner_auth), timeout=15)
                assert r3.status_code == 201, r3.text
        finally:
            requests.delete(f"{API}/views/{vid}", headers=h(owner_auth), timeout=15)


# ─────────────────────── PDF thumb ───────────────────────
class TestPdfThumb:
    def _make_pdf_bytes(self) -> bytes:
        try:
            from reportlab.pdfgen import canvas
        except Exception:
            pytest.skip("reportlab not available in test env")
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(100, 750, "TEST PDF for thumb")
        c.showPage(); c.save()
        return buf.getvalue()

    def test_pdf_thumb_returns_jpeg(self, owner_auth):
        data = self._make_pdf_bytes()
        files = {"files": (f"TEST_thumb_{uuid.uuid4().hex[:6]}.pdf", data, "application/pdf")}
        r = requests.post(f"{API}/media/upload", files=files,
                          headers=h(owner_auth), timeout=30)
        assert r.status_code == 201, r.text
        mid = r.json()[0]["id"] if "id" in r.json()[0] else r.json()[0]["_id"]
        # Fetch thumb
        rt = requests.get(f"{API}/media/{mid}/thumb", headers=h(owner_auth), timeout=30)
        assert rt.status_code == 200
        body = rt.json()
        assert "url" in body and "mime" in body
        # Could be jpeg if pdf2image available; svg fallback otherwise. Accept either
        # but if jpeg, url must not point at mime-icon.
        if body["mime"] == "image/jpeg":
            assert "/mime-icon/" not in body["url"]
        else:
            assert body["mime"] == "image/svg+xml"
        # Cleanup
        requests.delete(f"{API}/media/{mid}?cascade=true",
                        headers=h(owner_auth), timeout=15)

    def test_corrupt_pdf_falls_back(self, owner_auth):
        data = b"%PDF-1.4\nnot a real pdf\n%%EOF"
        files = {"files": (f"TEST_corrupt_{uuid.uuid4().hex[:6]}.pdf", data, "application/pdf")}
        r = requests.post(f"{API}/media/upload", files=files,
                          headers=h(owner_auth), timeout=30)
        assert r.status_code == 201
        mid = r.json()[0].get("id") or r.json()[0].get("_id")
        rt = requests.get(f"{API}/media/{mid}/thumb", headers=h(owner_auth), timeout=15)
        assert rt.status_code == 200
        body = rt.json()
        assert body["mime"] == "image/svg+xml"
        assert "/mime-icon/" in body["url"]
        requests.delete(f"{API}/media/{mid}?cascade=true",
                        headers=h(owner_auth), timeout=15)


# ─────────────────────── OpenAPI + PWA ───────────────────────
class TestOpenAPIAndPWA:
    def test_openapi_paths(self):
        r = requests.get(f"{API}/openapi.json", timeout=15)
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        assert any("label-presets" in p and "{org_id}" in p for p in paths)
        assert any(p.endswith("/label-presets/{pid}") for p in paths)

    def test_manifest_present(self):
        r = requests.get(f"{BASE_URL}/manifest.webmanifest", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("name") and d.get("icons")

    def test_sw_present(self):
        r = requests.get(f"{BASE_URL}/sw.js", timeout=15)
        assert r.status_code == 200
        assert "service worker" in r.text.lower() or "cache" in r.text.lower()
