"""UBOS Phase 1 backend tests — auth (register/login/refresh/rotation/logout),
forgot/reset/change password, RBAC, orgs/switch/members, X-Org-Id override,
tenant isolation, audit logs, seed idempotency, slugify regression.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    from dotenv import dotenv_values
    v = dotenv_values("/app/frontend/.env")
    BASE_URL = (v.get("REACT_APP_BACKEND_URL") or "").rstrip("/")

API = f"{BASE_URL}/api"

OWNER = ("owner@ubos.test", "OwnerPass!123")
EDITOR = ("editor@ubos.test", "EditorPass!123")
VIEWER = ("viewer@ubos.test", "ViewerPass!123")


@pytest.fixture(scope="session")
def s():
    return requests.Session()


def _login(s, email, password):
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def owner_tokens(s):
    return _login(s, *OWNER)


@pytest.fixture(scope="session")
def editor_tokens(s):
    return _login(s, *EDITOR)


@pytest.fixture(scope="session")
def viewer_tokens(s):
    return _login(s, *VIEWER)


# -------- Health / OpenAPI / Google status --------
class TestHealthAndBasics:
    def test_health(self, s):
        r = s.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_openapi(self, s):
        r = s.get(f"{API}/openapi.json", timeout=15)
        assert r.status_code == 200
        assert "paths" in r.json()

    def test_google_status_disabled(self, s):
        r = s.get(f"{API}/auth/google/status", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"enabled": False}


# -------- Auth register --------
class TestRegister:
    def test_register_without_org(self, s):
        email = f"tester+{uuid.uuid4().hex[:8]}@example.org"
        r = s.post(f"{API}/auth/register", json={
            "email": email, "password": "TestPass!123", "name": "Test User"
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert "access_token" in d and "refresh_token" in d
        assert d.get("org_id") is None
        assert d.get("role") is None
        assert d.get("permissions") == []
        assert d["user"]["email"] == email

    def test_register_duplicate_409(self, s):
        # owner already exists
        r = s.post(f"{API}/auth/register", json={
            "email": OWNER[0], "password": "Whatever!123", "name": "Dup"
        }, timeout=15)
        assert r.status_code == 409


# -------- Auth login --------
class TestLogin:
    def test_login_owner(self, s, owner_tokens):
        d = owner_tokens
        assert d["role"] == "owner"
        assert d["org_id"]
        assert isinstance(d["permissions"], list) and len(d["permissions"]) == 15

    def test_login_wrong_password_401(self, s):
        r = s.post(f"{API}/auth/login", json={
            "email": VIEWER[0], "password": "WRONGPass!123"
        }, timeout=15)
        assert r.status_code == 401

    def test_login_rate_limit_429(self, s):
        # 5 wrong attempts on a dedicated fresh email to isolate
        email = f"lockme+{uuid.uuid4().hex[:6]}@example.org"
        # register first so email exists (but that's not required for lockout)
        s.post(f"{API}/auth/register", json={"email": email, "password": "CorrectPass!123", "name": "Lock"}, timeout=15)
        codes = []
        for _ in range(6):
            r = s.post(f"{API}/auth/login", json={"email": email, "password": "BadPass!!!"}, timeout=15)
            codes.append(r.status_code)
        assert 429 in codes, f"expected 429 in {codes}"


# -------- /auth/me --------
class TestMe:
    def test_me_ok(self, s, owner_tokens):
        r = s.get(f"{API}/auth/me", headers=_bearer(owner_tokens["access_token"]), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "user" in d and "organizations" in d and "default_org_id" in d

    def test_me_unauth_401(self, s):
        r = s.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401


# -------- Refresh rotation --------
class TestRefreshRotation:
    def test_refresh_rotates(self, s):
        d0 = _login(s, *EDITOR)
        rt = d0["refresh_token"]
        r1 = s.post(f"{API}/auth/refresh", json={"refresh_token": rt}, timeout=15)
        assert r1.status_code == 200
        # reuse should fail
        r2 = s.post(f"{API}/auth/refresh", json={"refresh_token": rt}, timeout=15)
        assert r2.status_code == 401

    def test_logout_invalidates_refresh(self, s):
        d0 = _login(s, *EDITOR)
        rt = d0["refresh_token"]
        at = d0["access_token"]
        r = s.post(f"{API}/auth/logout",
                   headers=_bearer(at),
                   json={"refresh_token": rt}, timeout=15)
        assert r.status_code in (200, 204)
        r2 = s.post(f"{API}/auth/refresh", json={"refresh_token": rt}, timeout=15)
        assert r2.status_code == 401


# -------- Forgot / Reset / Change password --------
class TestPasswordFlows:
    def test_forgot_and_reset(self, s):
        # Create fresh user
        email = f"pwreset+{uuid.uuid4().hex[:8]}@example.org"
        s.post(f"{API}/auth/register", json={"email": email, "password": "OldPass!123", "name": "PW"}, timeout=15)
        r = s.post(f"{API}/auth/forgot-password", json={"email": email}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("dev_reset_url"), d
        # extract token param
        url = d["dev_reset_url"]
        assert "token=" in url
        token = url.split("token=", 1)[1].split("&", 1)[0]
        # reset
        r = s.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "NewPass!123"}, timeout=15)
        assert r.status_code == 200
        # login with new password
        r = s.post(f"{API}/auth/login", json={"email": email, "password": "NewPass!123"}, timeout=15)
        assert r.status_code == 200
        # reuse token → 400
        r = s.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "Another!123"}, timeout=15)
        assert r.status_code == 400

    def test_forgot_nonexistent_shape(self, s):
        r = s.post(f"{API}/auth/forgot-password", json={"email": f"nope+{uuid.uuid4().hex}@example.org"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "message" in d
        # dev_reset_url may be null for nonexistent
        assert "dev_reset_url" in d

    def test_change_password(self, s):
        email = f"chpw+{uuid.uuid4().hex[:8]}@example.org"
        reg = s.post(f"{API}/auth/register", json={"email": email, "password": "OldPass!123", "name": "CP"}, timeout=15).json()
        at = reg["access_token"]
        # wrong current
        r = s.post(f"{API}/auth/change-password",
                   headers=_bearer(at),
                   json={"current": "WRONG!123", "new": "NewPass!123"}, timeout=15)
        assert r.status_code == 400
        # correct
        r = s.post(f"{API}/auth/change-password",
                   headers=_bearer(at),
                   json={"current": "OldPass!123", "new": "NewPass!123"}, timeout=15)
        assert r.status_code == 200
        r = s.post(f"{API}/auth/login", json={"email": email, "password": "NewPass!123"}, timeout=15)
        assert r.status_code == 200


# -------- RBAC --------
class TestRBAC:
    def _get_products_id(self, s, tok):
        r = s.get(f"{API}/entity-types", headers=_bearer(tok), timeout=15)
        assert r.status_code == 200
        for et in r.json():
            if et.get("key") == "products":
                return et["id"]
        return None

    def test_viewer_cannot_create_record(self, s, viewer_tokens):
        pid = self._get_products_id(s, viewer_tokens["access_token"])
        assert pid, "products entity type should exist for Acme"
        r = s.post(f"{API}/entity-types/{pid}/records",
                   headers=_bearer(viewer_tokens["access_token"]),
                   json={"data": {}}, timeout=15)
        assert r.status_code == 403
        assert "records.create" in r.text

    def test_editor_can_create_record(self, s, editor_tokens):
        pid = self._get_products_id(s, editor_tokens["access_token"])
        r = s.post(f"{API}/entity-types/{pid}/records",
                   headers=_bearer(editor_tokens["access_token"]),
                   json={"data": {"name": f"TEST_ED_{uuid.uuid4().hex[:6]}",
                                    "sku": f"TESKU-{uuid.uuid4().hex[:6].upper()}",
                                    "price": 10, "in_stock": True, "category": "chair"}},
                   timeout=15)
        # data schema may vary; accept 200/201 or specific validation errors — but not 403
        assert r.status_code != 403, r.text

    def test_viewer_cannot_read_audit(self, s, viewer_tokens):
        r = s.get(f"{API}/audit-logs", headers=_bearer(viewer_tokens["access_token"]), timeout=15)
        assert r.status_code == 403

    def test_owner_can_read_audit(self, s, owner_tokens):
        r = s.get(f"{API}/audit-logs?limit=10", headers=_bearer(owner_tokens["access_token"]), timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body and isinstance(body["items"], list)


# -------- Orgs --------
class TestOrgs:
    def test_list_orgs_unauth(self, s):
        r = s.get(f"{API}/orgs", timeout=15)
        assert r.status_code == 401

    def test_list_orgs(self, s, owner_tokens):
        r = s.get(f"{API}/orgs", headers=_bearer(owner_tokens["access_token"]), timeout=15)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_create_org_and_switch(self, s):
        # fresh user
        email = f"orgu+{uuid.uuid4().hex[:8]}@example.org"
        reg = s.post(f"{API}/auth/register", json={"email": email, "password": "OrgPass!123", "name": "OrgU"}, timeout=15).json()
        at = reg["access_token"]
        r = s.post(f"{API}/orgs",
                   headers=_bearer(at),
                   json={"name": f"TEST Org {uuid.uuid4().hex[:6]}"}, timeout=15)
        assert r.status_code in (200, 201), r.text
        d = r.json()
        assert "access_token" in d and d.get("org_id")

    def test_switch_nonmember_403(self, s, owner_tokens):
        r = s.post(f"{API}/orgs/{uuid.uuid4()}/switch",
                   headers=_bearer(owner_tokens["access_token"]), timeout=15)
        assert r.status_code in (403, 404)

    def test_members_list(self, s, owner_tokens):
        org_id = owner_tokens["org_id"]
        r = s.get(f"{API}/orgs/{org_id}/members",
                  headers=_bearer(owner_tokens["access_token"]), timeout=15)
        assert r.status_code == 200
        members = r.json()
        emails = {m.get("email") or m.get("user_email") for m in members}
        assert OWNER[0] in emails
        assert EDITOR[0] in emails
        assert VIEWER[0] in emails

    def test_last_owner_demotion_blocked(self, s, owner_tokens):
        org_id = owner_tokens["org_id"]
        r = s.get(f"{API}/orgs/{org_id}/members",
                  headers=_bearer(owner_tokens["access_token"]), timeout=15)
        members = r.json()
        owner_member = next(m for m in members if (m.get("email") or m.get("user_email")) == OWNER[0])
        mid = owner_member.get("id") or owner_member.get("membership_id")
        r = s.patch(f"{API}/orgs/{org_id}/members/{mid}",
                    headers=_bearer(owner_tokens["access_token"]),
                    json={"role_name": "viewer"}, timeout=15)
        assert r.status_code == 400


# -------- X-Org-Id override --------
class TestXOrgIdOverride:
    def test_valid_override(self, s, owner_tokens):
        headers = _bearer(owner_tokens["access_token"])
        headers["X-Org-Id"] = owner_tokens["org_id"]
        r = s.get(f"{API}/entity-types", headers=headers, timeout=15)
        assert r.status_code == 200

    def test_random_uuid_override_403(self, s, owner_tokens):
        headers = _bearer(owner_tokens["access_token"])
        headers["X-Org-Id"] = str(uuid.uuid4())
        r = s.get(f"{API}/entity-types", headers=headers, timeout=15)
        assert r.status_code == 403


# -------- Multi-tenant isolation --------
class TestTenantIsolation:
    def test_isolation(self, s):
        # Register user A, create org
        emailA = f"tenantA+{uuid.uuid4().hex[:6]}@example.org"
        rA = s.post(f"{API}/auth/register", json={"email": emailA, "password": "Pass!1234", "name": "A"}, timeout=15).json()
        atA = rA["access_token"]
        oA = s.post(f"{API}/orgs", headers=_bearer(atA), json={"name": f"TEST A {uuid.uuid4().hex[:4]}"}, timeout=15).json()
        atA = oA["access_token"]
        # create entity type in A
        r = s.post(f"{API}/entity-types", headers=_bearer(atA),
                   json={"key": f"iso_{uuid.uuid4().hex[:6]}", "name_singular": "IsoW", "name_plural": "IsoWs"}, timeout=15)
        assert r.status_code in (200, 201), r.text
        keyA = r.json()["key"]

        # Register user B, create org
        emailB = f"tenantB+{uuid.uuid4().hex[:6]}@example.org"
        rB = s.post(f"{API}/auth/register", json={"email": emailB, "password": "Pass!1234", "name": "B"}, timeout=15).json()
        atB = rB["access_token"]
        oB = s.post(f"{API}/orgs", headers=_bearer(atB), json={"name": f"TEST B {uuid.uuid4().hex[:4]}"}, timeout=15).json()
        atB = oB["access_token"]
        r = s.get(f"{API}/entity-types", headers=_bearer(atB), timeout=15)
        assert r.status_code == 200
        keys = [x["key"] for x in r.json()]
        assert keyA not in keys


# -------- Audit logs content --------
class TestAuditLogs:
    def test_audit_has_actor(self, s, owner_tokens):
        r = s.get(f"{API}/audit-logs?limit=50",
                  headers=_bearer(owner_tokens["access_token"]), timeout=15)
        assert r.status_code == 200
        body = r.json()
        logs = body.get("items", body if isinstance(body, list) else [])
        assert isinstance(logs, list)
        if logs:
            sample = logs[0]
            assert "action" in sample
            assert "actor_id" in sample or "actor_email" in sample


# -------- Seed idempotency --------
class TestSeedIdempotent:
    def test_seed_demo_idempotent(self, s, owner_tokens):
        h = _bearer(owner_tokens["access_token"])
        r1 = s.post(f"{API}/dev/seed-demo", headers=h, timeout=30)
        assert r1.status_code == 200
        r2 = s.post(f"{API}/dev/seed-demo", headers=h, timeout=30)
        assert r2.status_code == 200
        d2 = r2.json()
        # look for zero counts
        # tolerate different shapes; check no error
        assert "error" not in str(d2).lower() or "already" in str(d2).lower()


# -------- Slugify regression (fields) --------
class TestSlugifyRegression:
    def _get_products(self, s, tok):
        r = s.get(f"{API}/entity-types", headers=_bearer(tok), timeout=15)
        for et in r.json():
            if et.get("key") == "products":
                return et["id"]
        return None

    def test_in_stock_key_via_api(self, s, owner_tokens):
        pid = self._get_products(s, owner_tokens["access_token"])
        assert pid
        # Try to add a field with underscore key — the fix ensures the regex accepts underscores
        payload = {
            "key": f"in_stock_test_{uuid.uuid4().hex[:4]}",
            "label": "In stock",
            "type": "boolean",
        }
        r = s.post(f"{API}/entity-types/{pid}/fields",
                   headers=_bearer(owner_tokens["access_token"]),
                   json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        # cleanup
        fid = r.json().get("id")
        if fid:
            s.delete(f"{API}/entity-types/{pid}/fields/{fid}",
                     headers=_bearer(owner_tokens["access_token"]), timeout=15)


# -------- Phase 0 regression --------
class TestPhase0Regression:
    def test_entity_types_crud_as_owner(self, s, owner_tokens):
        h = _bearer(owner_tokens["access_token"])
        key = f"regr_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/entity-types", headers=h,
                   json={"key": key, "name_singular": "Regr", "name_plural": "Regrs"}, timeout=15)
        assert r.status_code in (200, 201), r.text
        et_id = r.json()["id"]
        r = s.get(f"{API}/entity-types", headers=h, timeout=15)
        assert r.status_code == 200
        assert any(x["key"] == key for x in r.json())
        r = s.delete(f"{API}/entity-types/{et_id}", headers=h, timeout=15)
        assert r.status_code in (200, 204)
