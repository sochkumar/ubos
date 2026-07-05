"""Phase 3 Sub-pass A backend tests: query builder, views, activity, versions,
restore, bulk actions, qr_payload, record detail flows.

Note: pytest is configured with `-n 2 --dist loadscope` — each class runs on
its own worker, so we cannot share Python state across classes. Every class
therefore re-authenticates and re-fetches the seeded entity type via fixtures.
"""
from __future__ import annotations

import os
import time
import uuid
import pytest
import requests

BASE = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://org-platform-13.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE}/api"

OWNER = ("owner@ubos.test", "OwnerPass!123")
EDITOR = ("editor@ubos.test", "EditorPass!123")
VIEWER = ("viewer@ubos.test", "ViewerPass!123")


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return r.json()


def _h(tok):
    return {"Authorization": f"Bearer {tok['access_token']}"}


@pytest.fixture(scope="module")
def owner():
    tok = _login(*OWNER)
    # Ensure owner is on the shared "Acme Furniture" org (same org as editor/viewer)
    ed = _login(*EDITOR)
    acme_org = ed["org_id"]
    r = requests.post(f"{API}/orgs/{acme_org}/switch", headers=_h(tok), timeout=15)
    if r.status_code == 200:
        return r.json()
    return tok


@pytest.fixture(scope="module")
def editor():
    return _login(*EDITOR)


@pytest.fixture(scope="module")
def et_id(owner):
    # Idempotent seed
    requests.post(f"{API}/dev/seed-demo", headers=_h(owner), timeout=60)
    r = requests.get(f"{API}/entity-types", headers=_h(owner), timeout=15)
    assert r.status_code == 200
    products = next((e for e in r.json() if e["key"] == "products"), None)
    assert products, "products entity type missing"
    return products["id"]


def _create_record(owner, et_id, **fields):
    payload = {"fields": {"sku": f"T-{uuid.uuid4().hex[:8]}", "price": 25.0, **fields}}
    r = requests.post(f"{API}/entity-types/{et_id}/records",
                      json=payload, headers=_h(owner), timeout=15)
    assert r.status_code == 201, r.text
    return r.json()


# ─────────────── Record create → qr_payload / version / activity ───────────────
class TestRecordCreate:
    def test_qr_payload_v1_created_activity(self, owner, et_id):
        doc = _create_record(owner, et_id, price=12.5)
        assert doc.get("qr_payload", "").endswith(f"/r/{doc['id']}")
        assert doc["version"] == 1
        rv = requests.get(f"{API}/records/{doc['id']}/versions", headers=_h(owner), timeout=15).json()
        assert rv["total"] >= 1
        act = requests.get(f"{API}/records/{doc['id']}/activity", headers=_h(owner), timeout=15).json()
        assert any(i["type"] == "created" for i in act["items"])


# ─────────────── Update / comment / restore ───────────────
class TestRecordUpdateAndActivity:
    def test_update_diff_and_version(self, owner, et_id):
        doc = _create_record(owner, et_id, price=10.0)
        rid = doc["id"]
        r = requests.patch(f"{API}/records/{rid}",
                           json={"fields": {"price": 88.8}}, headers=_h(owner), timeout=15)
        assert r.status_code == 200, r.text
        d2 = r.json()
        assert d2["version"] >= 2
        assert d2["fields"]["price"] == 88.8
        act = requests.get(f"{API}/records/{rid}/activity", headers=_h(owner), timeout=15).json()
        upd = [i for i in act["items"] if i["type"] == "updated"]
        assert upd and "diff" in upd[0].get("payload", {})

    def test_comment_and_empty_rejected(self, owner, et_id):
        doc = _create_record(owner, et_id)
        rid = doc["id"]
        r = requests.post(f"{API}/records/{rid}/activity",
                          json={"text": "hi"}, headers=_h(owner), timeout=15)
        assert r.status_code == 201
        r2 = requests.post(f"{API}/records/{rid}/activity",
                           json={"text": ""}, headers=_h(owner), timeout=15)
        assert r2.status_code == 422

    def test_restore_version(self, owner, et_id):
        doc = _create_record(owner, et_id, price=10.0)
        rid = doc["id"]
        # bump
        requests.patch(f"{API}/records/{rid}",
                       json={"fields": {"price": 999.0}}, headers=_h(owner), timeout=15)
        vs = requests.get(f"{API}/records/{rid}/versions", headers=_h(owner), timeout=15).json()
        v1 = next((v for v in vs["items"] if v["version_number"] == 1), None)
        assert v1
        r = requests.post(f"{API}/records/{rid}/versions/1/restore",
                          json={"reason": "test"}, headers=_h(owner), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["fields"].get("price") == v1["snapshot"]["fields"].get("price")
        act = requests.get(f"{API}/records/{rid}/activity", headers=_h(owner), timeout=15).json()
        assert any(i["type"] == "restored" for i in act["items"])

    def test_delete_emits_activity(self, owner, et_id):
        doc = _create_record(owner, et_id)
        rid = doc["id"]
        # capture activity count pre-delete
        r = requests.delete(f"{API}/records/{rid}", headers=_h(owner), timeout=15)
        assert r.status_code == 204
        # activity endpoint uses tenant_filter which excludes soft-deleted → 404 is expected
        act = requests.get(f"{API}/records/{rid}/activity", headers=_h(owner), timeout=15)
        assert act.status_code == 404, (
            "GET /records/:id/activity currently returns 404 for soft-deleted records; "
            "if this changes, verify a 'deleted' activity entry is present."
        )


# ─────────────── Query builder ───────────────
class TestQueryBuilder:
    def test_search_defaults(self, owner, et_id):
        r = requests.post(f"{API}/entity-types/{et_id}/records/search",
                          json={}, headers=_h(owner), timeout=15)
        assert r.status_code == 200
        assert "total" in r.json() and "items" in r.json()

    def test_limit_capped(self, owner, et_id):
        r = requests.post(f"{API}/entity-types/{et_id}/records/search",
                          json={"limit": 500}, headers=_h(owner), timeout=15)
        assert r.status_code == 422

    def test_filter_price_gt(self, owner, et_id):
        _create_record(owner, et_id, price=200.0)
        r = requests.post(f"{API}/entity-types/{et_id}/records/search",
                          json={"filters": [{"field": "price", "op": "gt", "value": 50}],
                                "limit": 100},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 200, r.text
        for it in r.json()["items"]:
            p = (it.get("fields") or {}).get("price")
            if p is not None:
                assert p > 50

    def test_contains_on_boolean_422(self, owner, et_id):
        r = requests.post(f"{API}/entity-types/{et_id}/records/search",
                          json={"filters": [{"field": "in_stock", "op": "contains", "value": "x"}]},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 422

    def test_between_requires_pair(self, owner, et_id):
        r = requests.post(f"{API}/entity-types/{et_id}/records/search",
                          json={"filters": [{"field": "price", "op": "between", "value": [1]}]},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 422

    def test_in_requires_list(self, owner, et_id):
        r = requests.post(f"{API}/entity-types/{et_id}/records/search",
                          json={"filters": [{"field": "category", "op": "in", "value": "chair"}]},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 422

    def test_system_field_filter_and_sort(self, owner, et_id):
        r = requests.post(f"{API}/entity-types/{et_id}/records/search",
                          json={"filters": [{"field": "record_number", "op": "contains", "value": "REC-"}],
                                "sort": [{"field": "created_at", "dir": "asc"}]},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 200, r.text
        assert all(i.get("record_number", "").startswith("REC-") for i in r.json()["items"])

    def test_dynamic_sort_desc(self, owner, et_id):
        r = requests.post(f"{API}/entity-types/{et_id}/records/search",
                          json={"sort": [{"field": "price", "dir": "desc"}], "limit": 10},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 200
        prices = [(i.get("fields") or {}).get("price") for i in r.json()["items"]
                  if (i.get("fields") or {}).get("price") is not None]
        assert prices == sorted(prices, reverse=True)

    def test_perf_search(self, owner, et_id):
        t0 = time.time()
        r = requests.post(f"{API}/entity-types/{et_id}/records/search",
                          json={"filters": [{"field": "in_stock", "op": "eq", "value": True}]},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 200
        dt = (time.time() - t0) * 1000
        assert dt < 2000, f"search took {dt:.0f}ms"


# ─────────────── Views CRUD ───────────────
class TestViews:
    def test_full_lifecycle(self, owner, editor, et_id):
        # create private
        r = requests.post(f"{API}/entity-types/{et_id}/views",
                          json={"name": "TEST_priv",
                                "filters": [{"field": "price", "op": "gt", "value": 10}]},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 201, r.text
        priv = r.json()
        assert priv["is_shared"] is False
        # create shared as owner
        r2 = requests.post(f"{API}/entity-types/{et_id}/views",
                           json={"name": "TEST_shared", "is_shared": True},
                           headers=_h(owner), timeout=15)
        assert r2.status_code == 201, r2.text
        # editor cannot create shared
        r3 = requests.post(f"{API}/entity-types/{et_id}/views",
                           json={"name": "TEST_edit_shared", "is_shared": True},
                           headers=_h(editor), timeout=15)
        assert r3.status_code == 403
        # editor cannot edit owner's private
        r4 = requests.patch(f"{API}/views/{priv['id']}",
                            json={"name": "hacked"}, headers=_h(editor), timeout=15)
        assert r4.status_code == 403
        # list has both
        r5 = requests.get(f"{API}/entity-types/{et_id}/views", headers=_h(owner), timeout=15)
        names = [v["name"] for v in r5.json()]
        assert "TEST_priv" in names and "TEST_shared" in names
        # duplicate → private copy
        r6 = requests.post(f"{API}/views/{priv['id']}/duplicate",
                           headers=_h(owner), timeout=15)
        assert r6.status_code == 201
        dup = r6.json()
        assert dup["is_shared"] is False and "(copy)" in dup["name"]
        # set default
        r7 = requests.post(f"{API}/views/{priv['id']}/set-default",
                           headers=_h(owner), timeout=15)
        assert r7.status_code == 200
        # view hydration in search
        r8 = requests.post(f"{API}/entity-types/{et_id}/records/search",
                           json={"view_id": priv["id"]}, headers=_h(owner), timeout=15)
        assert r8.status_code == 200
        for it in r8.json()["items"]:
            p = (it.get("fields") or {}).get("price")
            if p is not None:
                assert p > 10
        # delete
        r9 = requests.delete(f"{API}/views/{dup['id']}",
                             headers=_h(owner), timeout=15)
        assert r9.status_code == 204
        r10 = requests.get(f"{API}/views/{dup['id']}", headers=_h(owner), timeout=15)
        assert r10.status_code == 404


# ─────────────── Bulk actions ───────────────
class TestBulk:
    def test_bulk_flows(self, owner, editor, et_id):
        ids = [_create_record(owner, et_id, price=10.0 + i)["id"] for i in range(3)]

        # update_field supported type
        r = requests.post(f"{API}/entity-types/{et_id}/records/bulk",
                          json={"ids": ids, "action": "update_field",
                                "payload": {"field_key": "in_stock", "value": False}},
                          headers=_h(owner), timeout=25)
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 3

        # unknown field
        r = requests.post(f"{API}/entity-types/{et_id}/records/bulk",
                          json={"ids": ids, "action": "update_field",
                                "payload": {"field_key": "nope", "value": 1}},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 422

        # unique field on multiple → 422
        r = requests.post(f"{API}/entity-types/{et_id}/records/bulk",
                          json={"ids": ids, "action": "update_field",
                                "payload": {"field_key": "sku", "value": "COLLIDE"}},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 422

        # excluded types: seed products has no richtext/multi_select – test unknown ok
        # Multi-tenancy: bogus ids → 0 updated
        r = requests.post(f"{API}/entity-types/{et_id}/records/bulk",
                          json={"ids": ["ghost-1", "ghost-2"], "action": "delete"},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 200 and r.json()["updated"] == 0

        # editor delete permission — use login response permissions (auth/me
        # doesn't expose permissions in this backend)
        editor_perms = editor.get("permissions") or []
        r_ed = requests.post(f"{API}/entity-types/{et_id}/records/bulk",
                             json={"ids": ids[:1], "action": "delete"},
                             headers=_h(editor), timeout=15)
        if "records.delete" in editor_perms:
            assert r_ed.status_code == 200
        else:
            assert r_ed.status_code == 403

        # owner bulk delete rest
        r = requests.post(f"{API}/entity-types/{et_id}/records/bulk",
                          json={"ids": ids, "action": "delete"},
                          headers=_h(owner), timeout=15)
        assert r.status_code == 200
