"""Phase 7 Sub-pass A — Terminology & vocabulary layer regression tests.

Covers:
- Backend PATCH /api/orgs/:id with settings.terminology (owner allowed, viewer 403)
- GET /api/orgs/:id returns settings.terminology
- Reset (empty dict) works
- REGRESSION: entity-types / records / fields / views / audit-logs GET still 2xx
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
           (open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip())
API = f"{BASE_URL}/api"

OWNER = {"email": "owner@ubos.test", "password": "OwnerPass!123"}
EDITOR = {"email": "editor@ubos.test", "password": "EditorPass!123"}
VIEWER = {"email": "viewer@ubos.test", "password": "ViewerPass!123"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"Login failed for {creds['email']}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def owner_session():
    data = _login(OWNER)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}", "Content-Type": "application/json"})
    return s, data["org_id"]


@pytest.fixture(scope="module")
def viewer_session():
    data = _login(VIEWER)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}", "Content-Type": "application/json"})
    return s, data["org_id"]


@pytest.fixture(scope="module")
def editor_session():
    data = _login(EDITOR)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {data['access_token']}", "Content-Type": "application/json"})
    return s, data["org_id"]


@pytest.fixture(scope="module", autouse=True)
def _cleanup_terminology(owner_session):
    # Ensure clean starting state
    s, oid = owner_session
    s.patch(f"{API}/orgs/{oid}", json={"settings": {"terminology": {}}})
    yield
    s.patch(f"{API}/orgs/{oid}", json={"settings": {"terminology": {}}})


# ═══════════════════════ Terminology backend ═══════════════════════

class TestTerminologyPatch:

    def test_get_org_returns_settings(self, owner_session):
        s, oid = owner_session
        r = s.get(f"{API}/orgs/{oid}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == oid
        assert "settings" in body

    def test_owner_can_set_terminology(self, owner_session):
        s, oid = owner_session
        payload = {"settings": {"terminology": {
            "collection.singular": "Product Line",
            "collection.plural": "Product Lines",
            "collection.new": "Add new Product Line",
        }}}
        r = s.patch(f"{API}/orgs/{oid}", json=payload)
        assert r.status_code == 200, r.text
        term = r.json().get("settings", {}).get("terminology", {})
        assert term.get("collection.singular") == "Product Line"
        assert term.get("collection.plural") == "Product Lines"
        assert term.get("collection.new") == "Add new Product Line"

        # Verify persistence via GET
        r2 = s.get(f"{API}/orgs/{oid}")
        assert r2.status_code == 200
        term2 = r2.json().get("settings", {}).get("terminology", {})
        assert term2.get("collection.singular") == "Product Line"

    def test_settings_deep_merge_preserves_other_keys(self, owner_session):
        s, oid = owner_session
        # Get current settings (should have terminology from prior test)
        before = s.get(f"{API}/orgs/{oid}").json().get("settings", {})
        # Patch a different setting key
        r = s.patch(f"{API}/orgs/{oid}", json={"settings": {"support_email": "hi@acme.test"}})
        assert r.status_code == 200
        after = r.json().get("settings", {})
        # terminology should be preserved
        assert after.get("terminology", {}).get("collection.singular") == "Product Line"
        assert after.get("support_email") == "hi@acme.test"

    def test_reset_terminology_with_empty_dict(self, owner_session):
        s, oid = owner_session
        r = s.patch(f"{API}/orgs/{oid}", json={"settings": {"terminology": {}}})
        assert r.status_code == 200
        term = r.json().get("settings", {}).get("terminology", {})
        assert term == {} or term is None or len(term) == 0

    def test_viewer_cannot_patch_terminology(self, viewer_session):
        s, oid = viewer_session
        r = s.patch(f"{API}/orgs/{oid}", json={"settings": {"terminology": {"collection.singular": "X"}}})
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_editor_cannot_patch_terminology(self, editor_session):
        s, oid = editor_session
        r = s.patch(f"{API}/orgs/{oid}", json={"settings": {"terminology": {"collection.singular": "X"}}})
        assert r.status_code == 403, f"Expected 403 for editor, got {r.status_code}: {r.text}"

    def test_viewer_can_read_org(self, viewer_session):
        s, oid = viewer_session
        r = s.get(f"{API}/orgs/{oid}")
        assert r.status_code == 200


# ═══════════════════════ Regression sweep ═══════════════════════

class TestPhase7ARegression:
    """Verify that renaming UI didn't break the underlying API contracts."""

    def test_entity_types_list(self, owner_session):
        s, _ = owner_session
        r = s.get(f"{API}/entity-types")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) or "items" in data

    def test_records_flow_create_read_update_delete(self, owner_session):
        s, _ = owner_session
        # Get first entity type
        r = s.get(f"{API}/entity-types")
        ets = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        assert len(ets) > 0, "No entity types in Acme"
        et = ets[0]
        et_id = et["id"]

        # List records
        r = s.get(f"{API}/entity-types/{et_id}/records", params={"limit": 5})
        assert r.status_code == 200

        # Get fields
        r = s.get(f"{API}/entity-types/{et_id}/fields")
        assert r.status_code == 200

        # Create record
        r = s.post(f"{API}/entity-types/{et_id}/records", json={
            "values": {},
            "name": "TEST_phase7a_record",
        })
        assert r.status_code in (200, 201), r.text
        rec_id = r.json()["id"]

        # Read it
        r = s.get(f"{API}/records/{rec_id}")
        assert r.status_code == 200

        # Update
        r = s.patch(f"{API}/records/{rec_id}", json={"name": "TEST_phase7a_updated"})
        assert r.status_code in (200, 204)

        # Delete
        r = s.delete(f"{API}/records/{rec_id}")
        assert r.status_code in (200, 204)

    def test_views_endpoint(self, owner_session):
        s, _ = owner_session
        r = s.get(f"{API}/entity-types")
        ets = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        if ets:
            r = s.get(f"{API}/entity-types/{ets[0]['id']}/views")
            assert r.status_code == 200

    def test_audit_logs_endpoint(self, owner_session):
        s, _ = owner_session
        r = s.get(f"{API}/audit-logs", params={"limit": 5})
        assert r.status_code == 200
