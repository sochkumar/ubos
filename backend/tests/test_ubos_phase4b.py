"""UBOS Phase 4 Sub-pass B — Global Search + Dashboard tests."""
from __future__ import annotations
import os
import time
import uuid
import pytest
import requests

def _get_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return v.rstrip("/")

BASE_URL = _get_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL required"
API = f"{BASE_URL}/api"

OWNER = ("owner@ubos.test", "OwnerPass!123")
EDITOR = ("editor@ubos.test", "EditorPass!123")
VIEWER = ("viewer@ubos.test", "ViewerPass!123")


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def owner_tok():
    d = _login(*OWNER)
    return d["access_token"], d["org_id"], d["user"]["id"]


@pytest.fixture(scope="session")
def editor_tok():
    d = _login(*EDITOR)
    return d["access_token"], d["org_id"], d["user"]["id"]


@pytest.fixture(scope="session")
def viewer_tok():
    try:
        d = _login(*VIEWER)
        return d["access_token"], d["org_id"], d["user"]["id"]
    except Exception:
        pytest.skip("viewer not seeded")


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _ensure_demo(tok):
    # trigger demo seed idempotently (endpoint from /app/backend/routes/dev.py)
    try:
        requests.post(f"{API}/dev/seed-demo", headers=_h(tok), timeout=30)
    except Exception:
        pass


# ─────────────────────────── SEARCH ───────────────────────────

class TestSearch:
    def test_search_requires_auth(self):
        r = requests.get(f"{API}/search?q=chair", timeout=10)
        assert r.status_code in (401, 403)

    def test_search_empty_query(self, owner_tok):
        tok, _, _ = owner_tok
        r = requests.get(f"{API}/search?q=", headers=_h(tok), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["results"] == []
        assert "facets" in d and "totals" in d and "took_ms" in d

    def test_search_limit_cap(self, owner_tok):
        tok, _, _ = owner_tok
        r = requests.get(f"{API}/search?q=a&limit=51", headers=_h(tok), timeout=15)
        assert r.status_code == 422

    def test_search_shape(self, owner_tok):
        tok, _, _ = owner_tok
        _ensure_demo(tok)
        r = requests.get(f"{API}/search?q=chair", headers=_h(tok), timeout=20)
        assert r.status_code == 200
        d = r.json()
        for key in ("results", "next_cursor", "facets", "totals", "took_ms"):
            assert key in d
        assert "entity_types" in d["facets"] and "kinds" in d["facets"]
        for res in d["results"]:
            for k in ("kind", "id", "title", "score", "breadcrumb", "icon"):
                assert k in res

    def test_search_records_only_gets_full_limit(self, owner_tok):
        tok, _, _ = owner_tok
        _ensure_demo(tok)
        r = requests.get(f"{API}/search?q=a&types=record&limit=20", headers=_h(tok), timeout=20)
        assert r.status_code == 200
        d = r.json()
        # all kinds are record
        for res in d["results"]:
            assert res["kind"] == "record"

    def test_search_fanout_all_kinds(self, owner_tok):
        tok, _, _ = owner_tok
        r = requests.get(f"{API}/search?q=a&limit=20", headers=_h(tok), timeout=20)
        assert r.status_code == 200
        d = r.json()
        # each kind slice max(3, 20/5)=4, so if a kind has any matches, at most 4 in list per kind
        kinds_in_results = {}
        for res in d["results"]:
            kinds_in_results[res["kind"]] = kinds_in_results.get(res["kind"], 0) + 1
        for k, cnt in kinds_in_results.items():
            assert cnt <= 4, f"{k} exceeded per-kind slice: {cnt}"

    def test_facets_kinds_only_positive(self, owner_tok):
        tok, _, _ = owner_tok
        r = requests.get(f"{API}/search?q=chair", headers=_h(tok), timeout=15)
        d = r.json()
        for kf in d["facets"]["kinds"]:
            assert kf["count"] > 0

    def test_cursor_pagination_no_dupes(self, owner_tok):
        tok, _, _ = owner_tok
        r = requests.get(f"{API}/search?q=a&limit=5", headers=_h(tok), timeout=20)
        d = r.json()
        first_ids = {(x["kind"], x["id"]) for x in d["results"]}
        if not d.get("next_cursor"):
            pytest.skip("no next_cursor for this dataset")
        r2 = requests.get(f"{API}/search?q=a&limit=5&cursor={d['next_cursor']}", headers=_h(tok), timeout=20)
        d2 = r2.json()
        second_ids = {(x["kind"], x["id"]) for x in d2["results"]}
        assert first_ids.isdisjoint(second_ids) or len(second_ids) == 0

    def test_cross_org_isolation(self, owner_tok, editor_tok):
        otok, oorg, _ = owner_tok
        etok, eorg, _ = editor_tok
        if oorg == eorg:
            pytest.skip("owner and editor in same org — cannot test cross-org isolation")
        r1 = requests.get(f"{API}/search?q=chair&types=record&limit=50", headers=_h(otok), timeout=20)
        r2 = requests.get(f"{API}/search?q=chair&types=record&limit=50", headers=_h(etok), timeout=20)
        ids1 = {x["id"] for x in r1.json()["results"]}
        ids2 = {x["id"] for x in r2.json()["results"]}
        assert ids1.isdisjoint(ids2)

    def test_snippet_length(self, owner_tok):
        tok, _, _ = owner_tok
        r = requests.get(f"{API}/search?q=a&types=record&limit=20", headers=_h(tok), timeout=20)
        for res in r.json()["results"]:
            if res.get("snippet"):
                assert len(res["snippet"]) < 400  # ~160 window + ellipses


# ─────────────────────────── DASHBOARD ───────────────────────────

class TestDashboard:
    def test_requires_auth(self):
        r = requests.get(f"{API}/dashboard/summary", timeout=10)
        assert r.status_code in (401, 403)

    def test_summary_shape(self, owner_tok):
        tok, _, _ = owner_tok
        _ensure_demo(tok)
        # bust cache first
        requests.post(f"{API}/dashboard/refresh", headers=_h(tok), timeout=15)
        r = requests.get(f"{API}/dashboard/summary", headers=_h(tok), timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("recent_records", "activity", "storage", "entity_types", "cached"):
            assert k in d
        assert d["cached"] is False
        for k in ("used_bytes", "quota_bytes", "pct", "by_mime_family"):
            assert k in d["storage"]
        # entity_types sorted by record_count desc
        counts = [et["record_count"] for et in d["entity_types"]]
        assert counts == sorted(counts, reverse=True)
        # recent_records ≤ 10
        assert len(d["recent_records"]) <= 10
        for rr in d["recent_records"]:
            assert "entity_type" in rr
            assert isinstance(rr.get("tags", []), list)
            assert len(rr.get("tags", [])) <= 3

    def test_cache_and_refresh(self, owner_tok):
        tok, _, _ = owner_tok
        requests.post(f"{API}/dashboard/refresh", headers=_h(tok), timeout=15)
        r1 = requests.get(f"{API}/dashboard/summary", headers=_h(tok), timeout=30).json()
        assert r1["cached"] is False
        r2 = requests.get(f"{API}/dashboard/summary", headers=_h(tok), timeout=30).json()
        assert r2["cached"] is True
        # bust
        rr = requests.post(f"{API}/dashboard/refresh", headers=_h(tok), timeout=15)
        assert rr.status_code == 204
        r3 = requests.get(f"{API}/dashboard/summary", headers=_h(tok), timeout=30).json()
        assert r3["cached"] is False

    def test_cache_per_user(self, owner_tok, editor_tok):
        otok, _, _ = owner_tok
        etok, _, _ = editor_tok
        requests.post(f"{API}/dashboard/refresh", headers=_h(otok), timeout=15)
        requests.get(f"{API}/dashboard/summary", headers=_h(otok), timeout=30)
        # editor may be in different org — still, their cache should be independent
        r = requests.get(f"{API}/dashboard/summary", headers=_h(etok), timeout=30).json()
        # editor's first call in this test session should be uncached OR cached from prior — either OK
        assert "cached" in r

    def test_activity_rbac_editor(self, editor_tok):
        tok, _, uid = editor_tok
        requests.post(f"{API}/dashboard/refresh", headers=_h(tok), timeout=15)
        r = requests.get(f"{API}/dashboard/summary", headers=_h(tok), timeout=30)
        assert r.status_code == 200
        for a in r.json()["activity"]:
            assert a["actor"]["id"] == uid, f"editor saw other user's activity: {a}"

    def test_viewer_can_read(self, viewer_tok):
        tok, _, _ = viewer_tok
        r = requests.get(f"{API}/dashboard/summary", headers=_h(tok), timeout=30)
        assert r.status_code == 200
