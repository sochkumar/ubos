"""Phase 5-B tests: user invitations + view sharing (public + collaborators) + nudges.

Uses seeded test users owner/editor/viewer@ubos.test in Acme Furniture org.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "https://org-platform-13.preview.emergentagent.com"
API = f"{BASE_URL}/api"


# ─────────────────────── helpers / fixtures ───────────────────────
def _login(email: str, password: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
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


# ─────────────────────── invitations ───────────────────────
class TestInvitations:
    def test_create_batch_dev_email(self, owner_auth, acme_org_id):
        email = f"newuser+testagent-{uuid.uuid4().hex[:6]}@ubos.test"
        r = requests.post(
            f"{API}/orgs/{acme_org_id}/invitations",
            json={"emails": [email], "role_name": "editor"},
            headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert "invitations" in data and len(data["invitations"]) == 1
        inv = data["invitations"][0]
        assert inv.get("token")
        assert inv.get("accept_url", "").endswith(f"/invitations/{inv['token']}/accept")
        assert inv.get("email_delivery", {}).get("ok") is True
        assert inv["email_delivery"]["provider"] == "dev"
        pytest.INVITATION = inv  # stash

    def test_get_public_meta(self, owner_auth):
        inv = pytest.INVITATION
        r = requests.get(f"{API}/invitations/{inv['token']}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "pending"
        assert j["email"] == inv["email"]
        assert j["role_name"] == "editor"
        assert j["org_name"]  # populated
        assert j["inviter"]["email"] == "owner@ubos.test"
        assert j["expires_at"]

    def test_get_public_unknown_token(self):
        r = requests.get(f"{API}/invitations/nonexistent-token-xyz", timeout=30)
        assert r.status_code == 404

    def test_accept_email_mismatch(self, editor_auth):
        inv = pytest.INVITATION
        r = requests.post(f"{API}/invitations/{inv['token']}/accept",
                          headers=h(editor_auth), timeout=30)
        assert r.status_code == 403, r.text
        detail = r.json().get("detail")
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "email_mismatch", r.text

    def test_duplicate_pending(self, owner_auth, acme_org_id):
        inv = pytest.INVITATION
        r = requests.post(
            f"{API}/orgs/{acme_org_id}/invitations",
            json={"emails": [inv["email"]], "role_name": "editor"},
            headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 201
        results = r.json()["invitations"]
        assert results[0].get("code") == "duplicate_pending", results

    def test_already_member(self, owner_auth, acme_org_id):
        r = requests.post(
            f"{API}/orgs/{acme_org_id}/invitations",
            json={"emails": ["editor@ubos.test"], "role_name": "editor"},
            headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 201
        results = r.json()["invitations"]
        assert results[0].get("code") == "already_member", results

    def test_resend_rotates_token(self, owner_auth, acme_org_id):
        inv = pytest.INVITATION
        old_token = inv["token"]
        # Find the invitation id from list
        lst = requests.get(f"{API}/orgs/{acme_org_id}/invitations", headers=h(owner_auth), timeout=30)
        assert lst.status_code == 200
        iid = next(i["id"] for i in lst.json() if i["email"] == inv["email"] and i["status"] == "pending")
        r = requests.post(f"{API}/orgs/{acme_org_id}/invitations/{iid}/resend",
                          json={}, headers=h(owner_auth), timeout=30)
        assert r.status_code == 200, r.text
        new_token = r.json()["token"]
        assert new_token != old_token
        # Old token 404
        r2 = requests.get(f"{API}/invitations/{old_token}", timeout=30)
        assert r2.status_code == 404
        # New token works
        r3 = requests.get(f"{API}/invitations/{new_token}", timeout=30)
        assert r3.status_code == 200
        pytest.INVITATION["token"] = new_token
        pytest.INVITATION["_iid"] = iid

    def test_revoke_then_accept_410(self, owner_auth, acme_org_id):
        inv = pytest.INVITATION
        iid = inv["_iid"]
        r = requests.post(f"{API}/orgs/{acme_org_id}/invitations/{iid}/revoke",
                          headers=h(owner_auth), timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "revoked"
        # Accept must return 410 invitation_revoked. But accept requires auth & matching email.
        # We don't have a user with the invited email; still, revoked check should run BEFORE
        # email mismatch check per invitations.py.
        r2 = requests.post(f"{API}/invitations/{inv['token']}/accept",
                           headers=h(_login("owner@ubos.test", "OwnerPass!123")), timeout=30)
        assert r2.status_code == 410
        detail = r2.json().get("detail")
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "invitation_revoked"

    def test_rbac_editor_cannot_invite(self, editor_auth, acme_org_id):
        r = requests.post(
            f"{API}/orgs/{acme_org_id}/invitations",
            json={"emails": ["foo@bar.test"], "role_name": "editor"},
            headers=h(editor_auth), timeout=30,
        )
        assert r.status_code == 403

    def test_rbac_viewer_cannot_list(self, viewer_auth, acme_org_id):
        r = requests.get(f"{API}/orgs/{acme_org_id}/invitations",
                         headers=h(viewer_auth), timeout=30)
        assert r.status_code == 403

    def test_batch_multiple_emails_under_limit(self, owner_auth, acme_org_id):
        emails = [f"batch+{uuid.uuid4().hex[:6]}-{i}@ubos.test" for i in range(3)]
        r = requests.post(
            f"{API}/orgs/{acme_org_id}/invitations",
            json={"emails": emails, "role_name": "viewer"},
            headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 201
        results = r.json()["invitations"]
        assert len(results) == 3
        for inv in results:
            assert inv.get("token"), inv


# ─────────────────────── view shares (public) ───────────────────────
class TestViewShares:
    @pytest.fixture(scope="class")
    def view_ctx(self, owner_auth):
        """Create a test entity type, field (with sensitive), view, records."""
        s = requests.Session()
        s.headers.update(h(owner_auth))
        # entity type
        slug = uuid.uuid4().hex[:6]
        et_name = f"TestET_{slug}"
        et = s.post(f"{API}/entity-types", json={
            "key": f"testet_{slug}",
            "name_singular": et_name, "name_plural": et_name + "s",
        }, timeout=30)
        assert et.status_code in (200, 201), et.text
        et_id = et.json()["id"]
        # public field
        f1 = s.post(f"{API}/entity-types/{et_id}/fields", json={
            "key": "notes", "label": "Notes", "type": "text",
        }, timeout=30)
        assert f1.status_code in (200, 201), f1.text
        # sensitive field
        f2 = s.post(f"{API}/entity-types/{et_id}/fields", json={
            "key": "ssn", "label": "SSN", "type": "text", "sensitive": True,
        }, timeout=30)
        assert f2.status_code in (200, 201), f2.text
        # a record
        r1 = s.post(f"{API}/entity-types/{et_id}/records", json={
            "title": "Rec1",
            "fields": {"notes": "hello world", "ssn": "SECRET-123"},
        }, timeout=30)
        assert r1.status_code in (200, 201), r1.text
        rec_id = r1.json()["id"]
        # a view (with visible_fields including both)
        v = s.post(f"{API}/entity-types/{et_id}/views", json={
            "name": "TestView", "layout": "table",
            "visible_fields": ["notes", "ssn"],
        }, timeout=30)
        assert v.status_code in (200, 201), v.text
        view_id = v.json()["id"]
        return {"et_id": et_id, "view_id": view_id, "record_id": rec_id}

    def test_create_public_share(self, owner_auth, view_ctx):
        r = requests.post(
            f"{API}/views/{view_ctx['view_id']}/shares",
            json={"visibility": "public"}, headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 201, r.text
        j = r.json()
        assert j["token"] and j["visibility"] == "public" and j["kind"] == "view"
        assert j["public_url"].endswith(f"/v/{j['token']}")
        pytest.VIEW_SHARE = j

    def test_public_view_returns_data(self, view_ctx):
        share = pytest.VIEW_SHARE
        r = requests.get(f"{API}/public/views/{share['token']}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["view"]["name"] == "TestView"
        assert j["view"]["layout"] == "table"
        cols = [c["field_key"] for c in j["view"]["visible_columns"]]
        assert "notes" in cols
        assert "ssn" not in cols, "sensitive field must be stripped"
        assert len(j["records"]) >= 1
        rec = next(r for r in j["records"] if r["id"] == view_ctx["record_id"])
        assert rec["fields"].get("notes") == "hello world"
        assert "ssn" not in rec["fields"], "sensitive field must not appear in payload"
        assert j["share"]["visibility"] == "public"
        assert j["pagination"]["total"] >= 1

    def test_public_view_record_endpoint(self, view_ctx):
        share = pytest.VIEW_SHARE
        r = requests.get(
            f"{API}/public/views/{share['token']}/records/{view_ctx['record_id']}",
            timeout=30,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["record"]["id"] == view_ctx["record_id"]
        assert "ssn" not in j["record"]["fields"]
        assert j["record"]["fields"].get("notes") == "hello world"

    def test_password_share_gate(self, owner_auth, view_ctx):
        r = requests.post(
            f"{API}/views/{view_ctx['view_id']}/shares",
            json={"visibility": "password", "password": "strongpw123"},
            headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 201, r.text
        share = r.json()
        assert share["has_password"] is True
        # Public GET without password → 401
        r2 = requests.get(f"{API}/public/views/{share['token']}", timeout=30)
        assert r2.status_code == 401
        detail = r2.json().get("detail")
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "password_required"
        # Wrong password
        r3 = requests.post(f"{API}/public/views/{share['token']}/unlock",
                           json={"password": "wrongone!"}, timeout=30)
        assert r3.status_code == 401
        d3 = r3.json().get("detail")
        assert (d3.get("code") if isinstance(d3, dict) else None) == "invalid_password"
        # Correct password
        sess = requests.Session()
        r4 = sess.post(f"{API}/public/views/{share['token']}/unlock",
                       json={"password": "strongpw123"}, timeout=30)
        assert r4.status_code == 200, r4.text
        assert r4.json().get("unlocked") is True
        r5 = sess.get(f"{API}/public/views/{share['token']}", timeout=30)
        assert r5.status_code == 200, r5.text

    def test_soft_deleted_view_returns_404_view_deleted(self, owner_auth, view_ctx):
        # Create a fresh view + share, then delete the view
        v = requests.post(
            f"{API}/entity-types/{view_ctx['et_id']}/views",
            json={"name": "ToDelete", "layout": "table"},
            headers=h(owner_auth), timeout=30,
        )
        assert v.status_code in (200, 201)
        vid = v.json()["id"]
        s = requests.post(f"{API}/views/{vid}/shares",
                         json={"visibility": "public"}, headers=h(owner_auth), timeout=30)
        assert s.status_code == 201, s.text
        token = s.json()["token"]
        # Soft delete view
        d = requests.delete(f"{API}/views/{vid}", headers=h(owner_auth), timeout=30)
        assert d.status_code in (200, 204), d.text
        r = requests.get(f"{API}/public/views/{token}", timeout=30)
        assert r.status_code == 404
        detail = r.json().get("detail")
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "view_deleted", r.text


# ─────────────────────── internal collaborators ───────────────────────
class TestCollaborators:
    @pytest.fixture(scope="class")
    def state(self, owner_auth, editor_auth):
        # Create a private view owned by owner
        s = requests.Session(); s.headers.update(h(owner_auth))
        # Find any existing entity type
        ets = s.get(f"{API}/entity-types", timeout=30).json()
        assert len(ets) > 0
        et_id = ets[0]["id"]
        v = s.post(f"{API}/entity-types/{et_id}/views", json={
            "name": f"CollabView_{uuid.uuid4().hex[:4]}", "layout": "table",
        }, timeout=30)
        assert v.status_code in (200, 201), v.text
        vid = v.json()["id"]
        editor_uid = editor_auth["user"]["id"]
        return {"et_id": et_id, "view_id": vid, "editor_uid": editor_uid}

    def test_editor_cannot_see_view_before(self, editor_auth, state):
        r = requests.get(f"{API}/entity-types/{state['et_id']}/views",
                         headers=h(editor_auth), timeout=30)
        assert r.status_code == 200
        ids = [v["id"] for v in r.json()]
        assert state["view_id"] not in ids

    def test_add_collaborator_view_perm(self, owner_auth, state):
        r = requests.post(
            f"{API}/views/{state['view_id']}/collaborators",
            json={"user_id": state["editor_uid"], "permission": "view"},
            headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 201, r.text

    def test_editor_sees_view_after(self, editor_auth, state):
        r = requests.get(f"{API}/entity-types/{state['et_id']}/views",
                         headers=h(editor_auth), timeout=30)
        assert r.status_code == 200
        ids = [v["id"] for v in r.json()]
        assert state["view_id"] in ids

    def test_view_collab_cannot_patch(self, editor_auth, state):
        r = requests.patch(f"{API}/views/{state['view_id']}",
                           json={"name": "new-name"},
                           headers=h(editor_auth), timeout=30)
        assert r.status_code == 403, r.text

    def test_edit_perm_allows_patch(self, owner_auth, editor_auth, state):
        # Update to edit
        u = requests.patch(
            f"{API}/views/{state['view_id']}/collaborators/{state['editor_uid']}",
            json={"permission": "edit"}, headers=h(owner_auth), timeout=30,
        )
        assert u.status_code == 200, u.text
        r = requests.patch(f"{API}/views/{state['view_id']}",
                           json={"name": "renamed-by-editor"},
                           headers=h(editor_auth), timeout=30)
        assert r.status_code == 200, r.text

    def test_list_collaborators_hydrated(self, owner_auth, state):
        r = requests.get(f"{API}/views/{state['view_id']}/collaborators",
                         headers=h(owner_auth), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert any(c.get("user", {}).get("email") == "editor@ubos.test" for c in j)

    def test_remove_collaborator(self, owner_auth, editor_auth, state):
        r = requests.delete(
            f"{API}/views/{state['view_id']}/collaborators/{state['editor_uid']}",
            headers=h(owner_auth), timeout=30,
        )
        assert r.status_code == 204
        r2 = requests.get(f"{API}/entity-types/{state['et_id']}/views",
                          headers=h(editor_auth), timeout=30)
        ids = [v["id"] for v in r2.json()]
        assert state["view_id"] not in ids


# ─────────────────────── nudges + dismiss + forgot-password ───────────────────────
class TestNudgesAndAuth:
    def test_nudge_no_recent_import(self, owner_auth):
        # First clear dismissal so we can test purely on import history
        r = requests.get(f"{API}/nudges/invite-after-import",
                         headers=h(owner_auth), timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        # Result may be show:true if there's an import; either way structure is right
        assert "show" in j

    def test_dismiss_prompt_hides(self, owner_auth):
        r = requests.post(f"{API}/users/me/dismissed-prompts",
                          json={"prompt_key": "invite_after_import"},
                          headers=h(owner_auth), timeout=30)
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{API}/nudges/invite-after-import",
                          headers=h(owner_auth), timeout=30)
        assert r2.status_code == 200
        assert r2.json()["show"] is False

    def test_forgot_password_dev_shape(self):
        r = requests.post(f"{API}/auth/forgot-password",
                         json={"email": "owner@ubos.test"}, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("email_provider") == "dev"
        assert j.get("dev_reset_url")

    def test_openapi_new_paths(self):
        r = requests.get(f"{API}/openapi.json", timeout=30)
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        expected = [
            "/api/orgs/{org_id}/invitations",
            "/api/invitations/{token}",
            "/api/views/{vid}/shares",
            "/api/public/views/{token}",
            "/api/views/{vid}/collaborators",
        ]
        for p in expected:
            assert p in paths, f"missing OpenAPI path {p}"
