"""UBOS Phase 5 Sub-pass A Hotfix tests:
   BUG 1 — in-batch unique-value detection (plan + execute + cross-batch + flush)
   BUG 2 — org-member bearer bypass on password-protected public GET / media / qr / barcode
   WARN  — dropdown auto_create_categories friendly error
"""
from __future__ import annotations
import io
import os
import time
import uuid
import pytest
import requests


def _get_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not v:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
    return v.rstrip("/")


BASE_URL = _get_backend_url()
API = f"{BASE_URL}/api"
PRODUCTS_ET = "c3ac360b-cba4-44bd-bf00-7658025b3dad"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def owner():
    return _login("owner@ubos.test", "OwnerPass!123")


@pytest.fixture(scope="session")
def editor():
    return _login("editor@ubos.test", "EditorPass!123")


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def _hj(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _preview_and_plan(tok, csv_bytes, mapping, options):
    files = {"file": (f"t_{uuid.uuid4().hex[:6]}.csv", csv_bytes, "text/csv")}
    r = requests.post(f"{API}/entity-types/{PRODUCTS_ET}/records/import/preview",
                      headers=_h(tok), files=files, timeout=30)
    assert r.status_code == 200, r.text
    imp_tok = r.json()["import_token"]
    body = {"import_token": imp_tok, "mapping": mapping, "options": options}
    r = requests.post(f"{API}/entity-types/{PRODUCTS_ET}/records/import/plan",
                      headers=_hj(tok), json=body, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def _plan_and_execute(tok, csv_bytes, mapping, options, timeout_s=60):
    files = {"file": (f"t_{uuid.uuid4().hex[:6]}.csv", csv_bytes, "text/csv")}
    r = requests.post(f"{API}/entity-types/{PRODUCTS_ET}/records/import/preview",
                      headers=_h(tok), files=files, timeout=30)
    assert r.status_code == 200, r.text
    imp_tok = r.json()["import_token"]
    body = {"import_token": imp_tok, "mapping": mapping, "options": options}
    r = requests.post(f"{API}/entity-types/{PRODUCTS_ET}/records/import/plan",
                      headers=_hj(tok), json=body, timeout=60)
    assert r.status_code == 200, r.text
    plan_id = r.json()["plan_id"]

    r = requests.post(f"{API}/entity-types/{PRODUCTS_ET}/records/import/execute",
                      headers=_hj(tok), json={"plan_id": plan_id}, timeout=30)
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    final = None
    for _ in range(timeout_s):
        r = requests.get(f"{API}/imports/{job_id}/progress", headers=_h(tok), timeout=15)
        assert r.status_code == 200
        p = r.json()
        if p["status"] in ("completed", "failed"):
            final = p
            break
        time.sleep(1)
    assert final is not None, f"import did not finish in {timeout_s}s"
    return final, job_id


# ═════════════════════════ BUG 1 — PLAN in-batch unique ═════════════════════════
class TestPlanInBatchUnique:
    def _csv_with_dup_sku(self):
        dup_sku = f"DUPSKU_{uuid.uuid4().hex[:6]}"
        return dup_sku, (
            "SKU,Title,Price,Category,In stock\n"
            f"{dup_sku},Row1,10,chair,true\n"
            "TEST_OK1,Row2,20,table,false\n"
            f"{dup_sku},Row3,30,sofa,true\n"
        ).encode()

    def test_error_policy_flags_in_batch_duplicate(self, owner):
        tok = owner["access_token"]
        _, csv_b = self._csv_with_dup_sku()
        mapping = {"SKU": "sku", "Title": "title", "Price": "price",
                   "Category": "category", "In stock": "in_stock"}
        d = _preview_and_plan(tok, csv_b, mapping,
                              {"match_by": "sku", "conflict_policy": "error"})
        assert d["total_rows"] == 3
        assert d["would_error"] >= 1, d
        # look for the friendly per-row message
        found_msg = False
        for ferr in d.get("first_errors") or []:
            for e in ferr.get("errors") or []:
                if "duplicate unique value" in (e.get("msg") or "") and "at row" in e["msg"]:
                    found_msg = True
                    break
        assert found_msg, f"expected 'duplicate unique value ... at row N (already at row M ...)' msg. Got: {d.get('first_errors')}"

    def test_skip_policy_collapses_in_batch_duplicate(self, owner):
        tok = owner["access_token"]
        _, csv_b = self._csv_with_dup_sku()
        mapping = {"SKU": "sku", "Title": "title", "Price": "price",
                   "Category": "category", "In stock": "in_stock"}
        d = _preview_and_plan(tok, csv_b, mapping,
                              {"match_by": "sku", "conflict_policy": "skip"})
        # 3 rows total, 1 duplicate → 2 insert (or match update) + 1 skip
        assert d["would_skip"] >= 1, d
        assert d["would_error"] == 0, d

    def test_update_policy_with_sku_match_collapses(self, owner):
        tok = owner["access_token"]
        _, csv_b = self._csv_with_dup_sku()
        mapping = {"SKU": "sku", "Title": "title", "Price": "price",
                   "Category": "category", "In stock": "in_stock"}
        d = _preview_and_plan(tok, csv_b, mapping,
                              {"match_by": "sku", "conflict_policy": "update"})
        # No pre-existing SKU → row1 insert, row3 skipped (collapsed dup)
        assert d["would_error"] == 0, d
        assert d["would_skip"] >= 1, d

    def test_update_policy_with_different_match_by_still_errors(self, owner):
        tok = owner["access_token"]
        _, csv_b = self._csv_with_dup_sku()
        # match_by = record_number (nonsense here) — duplicate SKU still must error
        mapping = {"SKU": "sku", "Title": "title", "Price": "price",
                   "Category": "category", "In stock": "in_stock"}
        d = _preview_and_plan(tok, csv_b, mapping,
                              {"match_by": "record_number", "conflict_policy": "update"})
        assert d["would_error"] >= 1, d


# ═════════════════════════ BUG 1 — EXECUTE in-batch unique ═════════════════════════
class TestExecuteInBatchUnique:
    def _make_csv(self, dup_sku):
        return (
            "SKU,Title,Price,Category,In stock\n"
            f"{dup_sku},Row1,10,chair,true\n"
            f"{dup_sku},Row2_dup,20,table,false\n"
            f"UQ_{uuid.uuid4().hex[:6]},Row3,30,sofa,true\n"
        ).encode()

    def test_execute_error_policy_writes_only_nondup(self, owner):
        tok = owner["access_token"]
        dup_sku = f"EXECERR_{uuid.uuid4().hex[:6]}"
        csv_b = self._make_csv(dup_sku)
        mapping = {"SKU": "sku", "Title": "title", "Price": "price",
                   "Category": "category", "In stock": "in_stock"}
        final, job_id = _plan_and_execute(tok, csv_b, mapping,
                                          {"match_by": "sku", "conflict_policy": "error"})
        assert final["status"] == "completed", final
        assert final["errors"] >= 1, final
        # Only 1 record should exist for that SKU
        r = requests.get(f"{API}/entity-types/{PRODUCTS_ET}/records?q={dup_sku}",
                         headers=_h(tok), timeout=15)
        assert r.status_code == 200
        d = r.json()
        items = d.get("items") if isinstance(d, dict) else d
        matching = [it for it in (items or []) if (it.get("fields") or {}).get("sku") == dup_sku]
        assert len(matching) == 1, f"expected exactly 1 record with sku={dup_sku}, got {len(matching)}"

    def test_execute_skip_policy_one_record_per_sku(self, owner):
        tok = owner["access_token"]
        dup_sku = f"EXECSKIP_{uuid.uuid4().hex[:6]}"
        csv_b = self._make_csv(dup_sku)
        mapping = {"SKU": "sku", "Title": "title", "Price": "price",
                   "Category": "category", "In stock": "in_stock"}
        final, _ = _plan_and_execute(tok, csv_b, mapping,
                                     {"match_by": "sku", "conflict_policy": "skip"})
        assert final["status"] == "completed", final
        assert final["skipped"] >= 1, final
        r = requests.get(f"{API}/entity-types/{PRODUCTS_ET}/records?q={dup_sku}",
                         headers=_h(tok), timeout=15)
        d = r.json()
        items = d.get("items") if isinstance(d, dict) else d
        matching = [it for it in (items or []) if (it.get("fields") or {}).get("sku") == dup_sku]
        assert len(matching) == 1, f"expected exactly 1 record for sku={dup_sku}, got {len(matching)}"

    def test_execute_update_with_sku_match_one_record(self, owner):
        tok = owner["access_token"]
        dup_sku = f"EXECUPD_{uuid.uuid4().hex[:6]}"
        csv_b = self._make_csv(dup_sku)
        mapping = {"SKU": "sku", "Title": "title", "Price": "price",
                   "Category": "category", "In stock": "in_stock"}
        final, _ = _plan_and_execute(tok, csv_b, mapping,
                                     {"match_by": "sku", "conflict_policy": "update"})
        assert final["status"] == "completed", final
        # Duplicate should NOT create 2 records
        r = requests.get(f"{API}/entity-types/{PRODUCTS_ET}/records?q={dup_sku}",
                         headers=_h(tok), timeout=15)
        d = r.json()
        items = d.get("items") if isinstance(d, dict) else d
        matching = [it for it in (items or []) if (it.get("fields") or {}).get("sku") == dup_sku]
        assert len(matching) == 1, f"expected exactly 1 record for sku={dup_sku}, got {len(matching)}"


# ═════════════════════════ BUG 1 — CROSS-BATCH ═════════════════════════
class TestCrossBatchUnique:
    def test_cross_batch_dup_detected(self, owner):
        tok = owner["access_token"]
        dup_sku = f"XBATCH_{uuid.uuid4().hex[:6]}"
        lines = ["SKU,Title,Price,Category,In stock"]
        lines.append(f"{dup_sku},RowA,10,chair,true")
        # 203 filler rows (unique SKUs)
        for i in range(203):
            lines.append(f"XF_{dup_sku}_{i},Row{i},{10 + i},chair,true")
        # row 205 (index 204) duplicates row 1
        lines.append(f"{dup_sku},RowZ_dup,99,table,false")
        csv_b = ("\n".join(lines) + "\n").encode()

        mapping = {"SKU": "sku", "Title": "title", "Price": "price",
                   "Category": "category", "In stock": "in_stock"}
        # PLAN - error policy
        d = _preview_and_plan(tok, csv_b, mapping,
                              {"match_by": "sku", "conflict_policy": "error"})
        assert d["total_rows"] == 205
        assert d["would_error"] >= 1, d
        # EXECUTE - skip policy — ensure only one record for dup_sku
        final, _ = _plan_and_execute(tok, csv_b, mapping,
                                     {"match_by": "sku", "conflict_policy": "skip"},
                                     timeout_s=90)
        assert final["status"] == "completed", final
        r = requests.get(f"{API}/entity-types/{PRODUCTS_ET}/records?q={dup_sku}",
                         headers=_h(tok), timeout=15)
        d = r.json()
        items = d.get("items") if isinstance(d, dict) else d
        matching = [it for it in (items or []) if (it.get("fields") or {}).get("sku") == dup_sku]
        assert len(matching) == 1, f"cross-batch dup not detected: {len(matching)} records"


# ═════════════════════════ BUG 1 — flush() defensive path ═════════════════════════
class TestFlushDefensiveErrorCount:
    """Static analysis — verify the flush() fallback increments errors."""
    def test_flush_increments_errors_on_exception(self):
        path = "/app/backend/routes/export_import.py"
        with open(path) as f:
            src = f.read()
        # look for the flush() fallback block that catches Exception and bumps errors
        assert "errors += 1" in src
        # Ensure inside flush there is a nested `except Exception as exc:` bumping errors
        # (not silent pass)
        # Find flush function region
        i = src.find("async def flush()")
        assert i > -1
        j = src.find("for row_idx, csv_row in enumerate(rows)", i)
        assert j > i
        flush_body = src[i:j]
        assert "errors += 1" in flush_body, "flush() must count insert/update failures"


# ═════════════════════════ WARN — dropdown friendly error ═════════════════════════
class TestDropdownFriendlyError:
    def test_dropdown_unknown_value_returns_friendly_msg(self, owner):
        tok = owner["access_token"]
        csv_data = (
            "SKU,Title,Price,Category,In stock\n"
            f"TEST_DD_{uuid.uuid4().hex[:6]},P,10,not_a_real_option,true\n"
        ).encode()
        mapping = {"SKU": "sku", "Title": "title", "Price": "price",
                   "Category": "category", "In stock": "in_stock"}
        d = _preview_and_plan(tok, csv_data, mapping,
                              {"match_by": "sku", "conflict_policy": "error",
                               "auto_create_categories": True})
        assert d["would_error"] >= 1, d
        # first error message must match the friendly template
        found = False
        for fe in d.get("first_errors") or []:
            for e in fe.get("errors") or []:
                if e.get("field") == "category" and "not in dropdown options for field 'category'" in (e.get("msg") or ""):
                    found = True
                    break
        assert found, f"expected friendly dropdown error. Got: {d.get('first_errors')}"


# ═════════════════════════ BUG 2 — org-member bearer bypass ═════════════════════════
@pytest.fixture(scope="module")
def password_share(owner):
    """Create a fresh password-protected share and return (token, sid, record_id)."""
    tok = owner["access_token"]
    r = requests.get(f"{API}/entity-types/{PRODUCTS_ET}/records?limit=1",
                     headers=_h(tok), timeout=15)
    d = r.json()
    items = d.get("items") if isinstance(d, dict) else d
    rid = items[0]["id"]
    r = requests.post(f"{API}/records/{rid}/shares", headers=_hj(tok),
                      json={"visibility": "password", "password": "secret123"}, timeout=15)
    assert r.status_code == 201, r.text
    d = r.json()
    return d["token"], d["id"], rid


class TestOrgMemberBypass:
    def test_owner_bearer_bypass_get(self, owner, password_share):
        token, _, _ = password_share
        # NO cookie, WITH owner bearer → 200
        r = requests.get(f"{API}/public/records/{token}",
                         headers=_h(owner["access_token"]), timeout=15)
        assert r.status_code == 200, r.text
        assert "record" in r.json()

    def test_editor_same_org_bearer_bypass_get(self, editor, password_share, owner):
        token, _, _ = password_share
        if editor["org_id"] == owner["org_id"]:
            r = requests.get(f"{API}/public/records/{token}",
                             headers=_h(editor["access_token"]), timeout=15)
            assert r.status_code == 200, r.text
        else:
            # Different org — editor is a "foreigner": must NOT bypass password gate
            r = requests.get(f"{API}/public/records/{token}",
                             headers=_h(editor["access_token"]), timeout=15)
            assert r.status_code == 401, f"foreign-org bearer should NOT bypass. Got {r.status_code}: {r.text[:200]}"
            assert "password_required" in r.text

    def test_no_bearer_no_cookie_401(self, password_share):
        token, _, _ = password_share
        r = requests.get(f"{API}/public/records/{token}", timeout=15)
        assert r.status_code == 401
        assert "password_required" in r.text

    def test_media_endpoint_bearer_bypass(self, owner, password_share):
        token, _, _ = password_share
        # Anonymous → 401 (either password_required or media not attached / 404)
        r_anon = requests.get(f"{API}/public/records/{token}/media/deadbeef", timeout=15)
        # Must be 401 (password gate first) — media check runs after
        assert r_anon.status_code == 401, r_anon.text
        # With bearer → should bypass password gate. Media id is bogus so we
        # expect either 404 (media not found) or 200 (very unlikely). NOT 401.
        r_own = requests.get(f"{API}/public/records/{token}/media/deadbeef",
                             headers=_h(owner["access_token"]), timeout=15)
        assert r_own.status_code != 401, f"org owner should bypass password gate. Got {r_own.status_code}: {r_own.text}"

    def test_qr_endpoint_bearer_bypass(self, owner, password_share):
        token, _, _ = password_share
        # Anonymous → 401
        r_anon = requests.get(f"{API}/public/records/{token}/qr.png", timeout=15)
        assert r_anon.status_code == 401
        # Owner bearer → should bypass (spec)
        r_own = requests.get(f"{API}/public/records/{token}/qr.png",
                             headers=_h(owner["access_token"]), timeout=15)
        assert r_own.status_code == 200, f"owner should bypass QR gate. Got {r_own.status_code}: {r_own.text[:200]}"

    def test_barcode_endpoint_bearer_bypass(self, owner, password_share):
        token, _, _ = password_share
        r_anon = requests.get(f"{API}/public/records/{token}/barcode.png", timeout=15)
        assert r_anon.status_code == 401
        r_own = requests.get(f"{API}/public/records/{token}/barcode.png",
                             headers=_h(owner["access_token"]), timeout=15)
        assert r_own.status_code == 200, f"owner should bypass barcode gate. Got {r_own.status_code}: {r_own.text[:200]}"
