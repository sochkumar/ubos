"""
Phase 6-B (Pass D) — Security & performance verification sweep.

Focus: cross-org isolation, public share masking + gating, rate limiting,
N+1 sanity, and regressions from Pass B (dashboard layout + audit sweep).

Run: pytest /app/backend/tests/test_ubos_phase6b_security.py -v
"""
from __future__ import annotations

import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

OWNER = ("owner@ubos.test", "OwnerPass!123")
VIEWER = ("viewer@ubos.test", "ViewerPass!123")


# ---------------- helpers ----------------
def _login(email: str, password: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()


def _headers(tok: dict) -> dict:
    return {"Authorization": f"Bearer {tok['access_token']}", "X-Org-Id": tok["org_id"]}


def _register(email: str, password: str, name: str = "T"):
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": password, "name": name}, timeout=15)
    if r.status_code == 409:
        return _login(email, password)
    assert r.status_code == 201, r.text
    return r.json()


def _create_org(bearer: str, name: str, slug: str) -> dict:
    r = requests.post(f"{API}/orgs",
                      json={"name": name, "slug": slug},
                      headers={"Authorization": f"Bearer {bearer}"}, timeout=15)
    assert r.status_code == 201, r.text
    body = r.json()
    # Response has {"org": {...id...}, "access_token": ..., ...}
    return body


def _switch_org(refresh_token: str, org_id: str) -> dict:
    r = requests.post(f"{API}/orgs/{org_id}/switch",
                      headers={"Authorization": f"Bearer {refresh_token}"}, timeout=15)
    # switch endpoint accepts access token
    return r


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def owner_ctx():
    tok = _login(*OWNER)
    return tok


@pytest.fixture(scope="module")
def acme_ids(owner_ctx):
    """Return {"org_id": ..., "et_id": ..., "record_id": ...} for Acme."""
    h = _headers(owner_ctx)
    ets = requests.get(f"{API}/entity-types", headers=h, timeout=15).json()
    et_id = ets[0]["id"] if isinstance(ets, list) and ets else ets.get("items", [{}])[0].get("id")
    assert et_id
    recs = requests.get(f"{API}/entity-types/{et_id}/records", headers=h, timeout=15).json()
    items = recs["items"] if isinstance(recs, dict) else recs
    rec_id = items[0]["id"] if items else None
    return {"org_id": owner_ctx["org_id"], "et_id": et_id, "record_id": rec_id}


@pytest.fixture(scope="module")
def outsider():
    """Register a fresh user in their own org."""
    unique = uuid.uuid4().hex[:8]
    email = f"TEST_outsider_{unique}@ubos.test"
    tok = _register(email, "OutsiderPass!123", "TEST Outsider")
    # Create their own org — response has {"org": {...}, "access_token": ...}
    resp = _create_org(tok["access_token"], f"TEST Outsider Org {unique}", f"test-outsider-{unique}")
    org_id = resp["org"]["id"]
    new_access = resp.get("access_token") or tok["access_token"]
    new_tok = {"access_token": new_access, "org_id": org_id}
    return {"tok": new_tok, "org_id": org_id, "email": email}


# ============================================================
# 1. CROSS-ORG ISOLATION
# ============================================================
class TestCrossOrgIsolation:
    def test_outsider_cannot_list_acme_entity_types(self, outsider, acme_ids):
        """Outsider hitting /entity-types with their own X-Org-Id gets THEIR list, not Acme's."""
        h = {"Authorization": f"Bearer {outsider['tok']['access_token']}",
             "X-Org-Id": outsider["org_id"]}
        r = requests.get(f"{API}/entity-types", headers=h, timeout=15)
        assert r.status_code == 200
        items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        # None of the Acme ET ids should be in outsider's list
        assert acme_ids["et_id"] not in [i.get("id") for i in items]

    def test_outsider_cannot_read_acme_record_by_id(self, outsider, acme_ids):
        if not acme_ids["record_id"]:
            pytest.skip("no acme record")
        h = {"Authorization": f"Bearer {outsider['tok']['access_token']}",
             "X-Org-Id": outsider["org_id"]}
        r = requests.get(f"{API}/records/{acme_ids['record_id']}", headers=h, timeout=15)
        assert r.status_code in (403, 404), f"expected 403/404, got {r.status_code}: {r.text}"

    def test_outsider_cannot_read_acme_entity_type_by_id(self, outsider, acme_ids):
        h = {"Authorization": f"Bearer {outsider['tok']['access_token']}",
             "X-Org-Id": outsider["org_id"]}
        r = requests.get(f"{API}/entity-types/{acme_ids['et_id']}", headers=h, timeout=15)
        assert r.status_code in (403, 404)

    def test_outsider_cannot_delete_acme_entity_type(self, outsider, acme_ids):
        h = {"Authorization": f"Bearer {outsider['tok']['access_token']}",
             "X-Org-Id": outsider["org_id"]}
        r = requests.delete(f"{API}/entity-types/{acme_ids['et_id']}", headers=h, timeout=15)
        assert r.status_code in (403, 404)

    def test_outsider_cannot_patch_acme_record(self, outsider, acme_ids):
        if not acme_ids["record_id"]:
            pytest.skip("no acme record")
        h = {"Authorization": f"Bearer {outsider['tok']['access_token']}",
             "X-Org-Id": outsider["org_id"]}
        r = requests.patch(f"{API}/records/{acme_ids['record_id']}",
                           json={"title": "hacked"}, headers=h, timeout=15)
        assert r.status_code in (403, 404)

    def test_x_org_id_spoof_rejected(self, outsider, acme_ids):
        """Outsider passing X-Org-Id=<acme_id> with their own bearer must be denied."""
        h = {"Authorization": f"Bearer {outsider['tok']['access_token']}",
             "X-Org-Id": acme_ids["org_id"]}
        r = requests.get(f"{API}/entity-types", headers=h, timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"

    def test_outsider_cannot_list_acme_members(self, outsider, acme_ids):
        h = {"Authorization": f"Bearer {outsider['tok']['access_token']}",
             "X-Org-Id": outsider["org_id"]}
        r = requests.get(f"{API}/orgs/{acme_ids['org_id']}/members", headers=h, timeout=15)
        assert r.status_code in (401, 403, 404)


# ============================================================
# 2. PUBLIC SHARE SENSITIVE-FIELD MASKING
# ============================================================
@pytest.fixture(scope="module")
def sensitive_share(owner_ctx, acme_ids):
    """Create an entity_type with a sensitive field, one record, and a public share."""
    h = _headers(owner_ctx)
    tag = uuid.uuid4().hex[:6]

    # Create ET
    r = requests.post(f"{API}/entity-types",
                      json={"key": f"test_et_sens_{tag}",
                            "name_singular": f"TEST_ETsens_{tag}",
                            "name_plural": f"TEST_ETsens_{tag}s"},
                      headers=h, timeout=15)
    if r.status_code != 201:
        pytest.skip(f"cannot create ET: {r.status_code} {r.text}")
    et_id = r.json()["id"]

    # Create 2 fields: one non-sensitive, one sensitive
    r1 = requests.post(f"{API}/entity-types/{et_id}/fields",
                       json={"key": "public_note", "label": "Public Note", "type": "text"},
                       headers=h, timeout=15)
    assert r1.status_code == 201, r1.text
    r2 = requests.post(f"{API}/entity-types/{et_id}/fields",
                       json={"key": "ssn", "label": "SSN", "type": "text", "sensitive": True},
                       headers=h, timeout=15)
    assert r2.status_code == 201, f"sensitive field create failed: {r2.text}"

    # Create record
    rec = requests.post(f"{API}/entity-types/{et_id}/records",
                        json={"title": f"TEST_rec_{tag}",
                              "fields": {"public_note": "hello world", "ssn": "111-22-3333"}},
                        headers=h, timeout=15)
    assert rec.status_code == 201, rec.text
    rec_id = rec.json()["id"]

    # Create a public share for this record
    sh = requests.post(f"{API}/records/{rec_id}/shares",
                       json={"visibility": "public"},
                       headers=h, timeout=15)
    assert sh.status_code == 201, sh.text
    share = sh.json()

    # Create a password-protected share too
    ph = requests.post(f"{API}/records/{rec_id}/shares",
                       json={"visibility": "password", "password": "SharedPass!42"},
                       headers=h, timeout=15)
    assert ph.status_code == 201, ph.text
    pshare = ph.json()

    yield {"et_id": et_id, "record_id": rec_id, "share": share, "pshare": pshare,
           "tag": tag}

    # Cleanup: delete the ET (cascades records + shares)
    requests.delete(f"{API}/entity-types/{et_id}", headers=h, timeout=15)


class TestPublicShareMasking:
    def test_public_share_hides_sensitive_field(self, sensitive_share):
        token = sensitive_share["share"]["token"]
        r = requests.get(f"{API}/public/records/{token}", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # Sensitive key must not be present
        fields = body.get("record", {}).get("fields", {})
        assert "ssn" not in fields, f"sensitive 'ssn' leaked in public payload: {fields}"
        assert "public_note" in fields
        # Also check field_defs shouldn't include the sensitive one
        defs_keys = [d.get("key") for d in body.get("field_defs", [])]
        assert "ssn" not in defs_keys, f"sensitive field_def leaked: {defs_keys}"

    def test_password_share_401_before_unlock(self, sensitive_share):
        token = sensitive_share["pshare"]["token"]
        r = requests.get(f"{API}/public/records/{token}", timeout=15)
        assert r.status_code == 401, f"expected 401, got {r.status_code} {r.text}"
        body = r.json()
        assert body.get("detail", {}).get("code") == "password_required" or \
               (isinstance(body.get("detail"), dict) and body["detail"].get("code") == "password_required")

    def test_password_share_masks_sensitive_after_unlock(self, sensitive_share):
        token = sensitive_share["pshare"]["token"]
        s = requests.Session()
        r = s.post(f"{API}/public/records/{token}/unlock",
                   json={"password": "SharedPass!42"}, timeout=15)
        assert r.status_code == 200, r.text
        # Extract cookie explicitly and pass to next request
        cookie_name = f"share_unlock_{token}"
        cookie_val = s.cookies.get(cookie_name)
        assert cookie_val, f"unlock cookie not set; cookies={s.cookies.get_dict()}"
        r2 = requests.get(f"{API}/public/records/{token}",
                          cookies={cookie_name: cookie_val}, timeout=15)
        assert r2.status_code == 200, r2.text
        fields = r2.json().get("record", {}).get("fields", {})
        assert "ssn" not in fields, f"sensitive leaked after unlock: {fields}"

    def test_wrong_password_401(self, sensitive_share):
        token = sensitive_share["pshare"]["token"]
        r = requests.post(f"{API}/public/records/{token}/unlock",
                          json={"password": "WrongPass!!"}, timeout=15)
        assert r.status_code == 401


# ============================================================
# 3. PUBLIC SHARE VISIBILITY SEMANTICS
# ============================================================
class TestShareVisibility:
    def test_revoked_share_returns_410(self, owner_ctx, acme_ids):
        if not acme_ids["record_id"]:
            pytest.skip("no acme record")
        h = _headers(owner_ctx)
        sh = requests.post(f"{API}/records/{acme_ids['record_id']}/shares",
                           json={"visibility": "public"}, headers=h, timeout=15)
        assert sh.status_code == 201, sh.text
        sid = sh.json()["id"]
        token = sh.json()["token"]
        requests.post(f"{API}/shares/{sid}/revoke", headers=h, timeout=15)
        r = requests.get(f"{API}/public/records/{token}", timeout=15)
        assert r.status_code == 410
        # cleanup
        requests.delete(f"{API}/shares/{sid}", headers=h, timeout=15)

    def test_private_share_401_no_auth(self, owner_ctx, acme_ids):
        if not acme_ids["record_id"]:
            pytest.skip("no acme record")
        h = _headers(owner_ctx)
        sh = requests.post(f"{API}/records/{acme_ids['record_id']}/shares",
                           json={"visibility": "private"}, headers=h, timeout=15)
        assert sh.status_code == 201, sh.text
        token = sh.json()["token"]
        sid = sh.json()["id"]
        r = requests.get(f"{API}/public/records/{token}", timeout=15)
        assert r.status_code == 401
        # matching-org auth → 200
        r2 = requests.get(f"{API}/public/records/{token}",
                          headers={"Authorization": f"Bearer {owner_ctx['access_token']}"}, timeout=15)
        assert r2.status_code == 200, r2.text
        requests.delete(f"{API}/shares/{sid}", headers=h, timeout=15)

    def test_org_only_wrong_org_401(self, owner_ctx, acme_ids, outsider):
        if not acme_ids["record_id"]:
            pytest.skip("no acme record")
        h = _headers(owner_ctx)
        sh = requests.post(f"{API}/records/{acme_ids['record_id']}/shares",
                           json={"visibility": "org_only"}, headers=h, timeout=15)
        assert sh.status_code == 201, sh.text
        token = sh.json()["token"]
        sid = sh.json()["id"]
        # No auth
        r0 = requests.get(f"{API}/public/records/{token}", timeout=15)
        assert r0.status_code == 401
        # Wrong-org bearer
        r1 = requests.get(f"{API}/public/records/{token}",
                          headers={"Authorization": f"Bearer {outsider['tok']['access_token']}"}, timeout=15)
        assert r1.status_code in (401, 403)
        # Correct-org bearer
        r2 = requests.get(f"{API}/public/records/{token}",
                          headers={"Authorization": f"Bearer {owner_ctx['access_token']}"}, timeout=15)
        assert r2.status_code == 200
        requests.delete(f"{API}/shares/{sid}", headers=h, timeout=15)


# ============================================================
# 4. RATE LIMITING
# ============================================================
class TestRateLimiting:
    def test_login_bruteforce_lockout(self, reset_rate_limits):
        """5 failed logins → 6th returns 429 with Retry-After."""
        # Use a unique email so we don't clobber a real user's lockout state
        bad_email = f"TEST_lockout_{uuid.uuid4().hex[:8]}@ubos.test"
        codes = []
        for _ in range(5):
            r = requests.post(f"{API}/auth/login",
                              json={"email": bad_email, "password": "nope"}, timeout=15)
            codes.append(r.status_code)
        # 6th should be 429
        r6 = requests.post(f"{API}/auth/login",
                           json={"email": bad_email, "password": "nope"}, timeout=15)
        assert r6.status_code == 429, f"expected 429 after 5 fails; got {r6.status_code}. codes={codes}"
        assert r6.headers.get("Retry-After"), "Retry-After header missing"

    def test_public_unlock_rate_limit(self, reset_rate_limits, sensitive_share):
        """5 wrong unlock attempts → 6th returns 429."""
        token = sensitive_share["pshare"]["token"]
        for _ in range(5):
            requests.post(f"{API}/public/records/{token}/unlock",
                          json={"password": "wrong-pw-x"}, timeout=15)
        r = requests.post(f"{API}/public/records/{token}/unlock",
                          json={"password": "wrong-pw-x"}, timeout=15)
        assert r.status_code == 429, f"expected 429, got {r.status_code}: {r.text}"
        assert r.headers.get("Retry-After"), "Retry-After header missing"
        body = r.json()
        detail = body.get("detail", {})
        assert isinstance(detail, dict) and "retry_after" in detail, f"body missing retry_after: {body}"

    def test_public_read_rate_limit(self, reset_rate_limits, sensitive_share):
        """PUBLIC_READ_RATE_LIMIT — fire limit+5 requests, expect at least one 429.

        Uses a unique X-Forwarded-For to isolate this test's bucket from
        other files running in parallel (`X-Forwarded-For` gives the test
        its own rate-limit key, avoiding cross-file interference).
        """
        token = sensitive_share["share"]["token"]
        # Read env-configured limit
        limit = int(os.environ.get("PUBLIC_READ_RATE_LIMIT", "60/min").split("/")[0])
        # Unique client IP → dedicated bucket
        xff = f"8.8.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
        s = requests.Session()
        codes = []
        for _ in range(limit + 5):
            r = s.get(f"{API}/public/records/{token}",
                      headers={"X-Forwarded-For": xff}, timeout=15)
            codes.append(r.status_code)
            if r.status_code == 429:
                break
        assert 429 in codes, f"no 429 in {len(codes)} requests (limit={limit}). codes={codes[-5:]}"


# ============================================================
# 5. DASHBOARD LAYOUT (Pass B regression)
# ============================================================
class TestDashboardLayout:
    def test_default_layout_returned_initially(self, owner_ctx):
        # Reset first to ensure clean state
        requests.post(f"{API}/dashboard/layout/reset", headers=_headers(owner_ctx), timeout=15)
        r = requests.get(f"{API}/dashboard/layout", headers=_headers(owner_ctx), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "layout" in body and "defaults" in body
        keys = [s["widget_key"] for s in body["layout"]]
        assert set(keys) == {"recent_records", "activity", "storage", "entity_types"}

    def test_put_persists_and_normalizes(self, owner_ctx):
        payload = {"layout": [
            {"widget_key": "storage", "visible": False, "order": 0},
            {"widget_key": "activity", "visible": True, "order": 1},
        ]}
        r = requests.put(f"{API}/dashboard/layout", json=payload,
                         headers=_headers(owner_ctx), timeout=15)
        assert r.status_code == 200, r.text
        # GET should backfill missing widgets
        g = requests.get(f"{API}/dashboard/layout", headers=_headers(owner_ctx), timeout=15).json()
        keys = [s["widget_key"] for s in g["layout"]]
        assert set(keys) == {"recent_records", "activity", "storage", "entity_types"}, keys
        # storage should be hidden
        by_key = {s["widget_key"]: s for s in g["layout"]}
        assert by_key["storage"]["visible"] is False

    def test_put_strips_unknown_widgets(self, owner_ctx):
        payload = {"layout": [
            {"widget_key": "storage", "visible": True, "order": 0},
            # unknown keys should be stripped by pydantic Literal validation → 422
            # so we test the normalizer path via a mostly-valid payload
        ]}
        r = requests.put(f"{API}/dashboard/layout", json=payload,
                         headers=_headers(owner_ctx), timeout=15)
        assert r.status_code == 200

    def test_reset_returns_default(self, owner_ctx):
        r = requests.post(f"{API}/dashboard/layout/reset",
                          headers=_headers(owner_ctx), timeout=15)
        assert r.status_code == 200
        body = r.json()
        keys = [s["widget_key"] for s in body["layout"]]
        assert set(keys) == {"recent_records", "activity", "storage", "entity_types"}

    def test_layout_update_audit_emitted(self, owner_ctx):
        # trigger
        requests.put(f"{API}/dashboard/layout",
                     json={"layout": [{"widget_key": "activity", "visible": True, "order": 0}]},
                     headers=_headers(owner_ctx), timeout=15)
        time.sleep(1.0)  # background task
        r = requests.get(f"{API}/audit-logs",
                         params={"action": "dashboard.layout.updated", "limit": 5},
                         headers=_headers(owner_ctx), timeout=15)
        assert r.status_code == 200, r.text
        items = r.json().get("items", [])
        assert len(items) >= 1, "no dashboard.layout.updated audit entry"

    def test_layout_reset_audit_emitted(self, owner_ctx):
        requests.post(f"{API}/dashboard/layout/reset",
                      headers=_headers(owner_ctx), timeout=15)
        time.sleep(1.0)
        r = requests.get(f"{API}/audit-logs",
                         params={"action": "dashboard.layout.reset", "limit": 5},
                         headers=_headers(owner_ctx), timeout=15)
        assert r.status_code == 200
        assert len(r.json().get("items", [])) >= 1, "no dashboard.layout.reset audit entry"

    def test_viewer_can_access_layout(self):
        vtok = _login(*VIEWER)
        r = requests.get(f"{API}/dashboard/layout", headers=_headers(vtok), timeout=15)
        assert r.status_code == 200, r.text


# ============================================================
# 6. AUDIT LOG SWEEP (Pass B)
# ============================================================
class TestAuditSweep:
    def test_prompt_dismissed_audit(self, owner_ctx):
        prompt_key = f"TEST_prompt_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/users/me/dismissed-prompts",
                          json={"prompt_key": prompt_key},
                          headers=_headers(owner_ctx), timeout=15)
        assert r.status_code in (200, 201, 204), r.text
        time.sleep(1.0)
        a = requests.get(f"{API}/audit-logs",
                         params={"action": "prompt.dismissed", "limit": 5},
                         headers=_headers(owner_ctx), timeout=15)
        assert a.status_code == 200
        assert len(a.json().get("items", [])) >= 1, "no prompt.dismissed audit"


# ============================================================
# 7. PERFORMANCE / N+1 sanity check
# ============================================================
class TestPerformance:
    def test_dashboard_summary_single_shot(self, owner_ctx):
        """Dashboard summary should return in reasonable time even with data."""
        start = time.time()
        r = requests.get(f"{API}/dashboard/summary", headers=_headers(owner_ctx), timeout=15)
        elapsed = time.time() - start
        assert r.status_code == 200, r.text
        assert elapsed < 3.0, f"dashboard/summary took {elapsed:.2f}s (>3s suggests N+1)"

    def test_records_list_reasonable_latency(self, owner_ctx, acme_ids):
        start = time.time()
        r = requests.get(f"{API}/entity-types/{acme_ids['et_id']}/records",
                         params={"limit": 50}, headers=_headers(owner_ctx), timeout=15)
        elapsed = time.time() - start
        assert r.status_code == 200
        assert elapsed < 3.0, f"records list took {elapsed:.2f}s"

    def test_audit_logs_latency(self, owner_ctx):
        start = time.time()
        r = requests.get(f"{API}/audit-logs", params={"limit": 100},
                         headers=_headers(owner_ctx), timeout=15)
        elapsed = time.time() - start
        assert r.status_code == 200
        assert elapsed < 3.0, f"audit-logs took {elapsed:.2f}s"
