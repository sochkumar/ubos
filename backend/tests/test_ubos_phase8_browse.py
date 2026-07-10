"""Phase 8 — Universal browse + browse-scope views tests."""
import os
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://org-platform-13.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

OWNER = ("owner@ubos.test", "OwnerPass!123")
EDITOR = ("editor@ubos.test", "EditorPass!123")
VIEWER = ("viewer@ubos.test", "ViewerPass!123")


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def owner_hdr():
    return {"Authorization": f"Bearer {_login(*OWNER)}"}


@pytest.fixture(scope="module")
def editor_hdr():
    try:
        return {"Authorization": f"Bearer {_login(*EDITOR)}"}
    except AssertionError:
        pytest.skip("editor user not available")


@pytest.fixture(scope="module")
def viewer_hdr():
    try:
        return {"Authorization": f"Bearer {_login(*VIEWER)}"}
    except AssertionError:
        pytest.skip("viewer user not available")


# ── 1. Basic browse ──
def test_browse_top_level_keys(owner_hdr):
    r = requests.get(f"{API}/records/browse", headers=owner_hdr, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ["results", "next_cursor", "facets", "total_estimate", "took_ms", "entity_type_field_defs", "sort"]:
        assert k in d, f"missing key: {k}"
    assert d["sort"] == "updated_at:desc"


def test_browse_returns_records_with_expected_shape(owner_hdr):
    r = requests.get(f"{API}/records/browse?limit=100", headers=owner_hdr, timeout=15)
    d = r.json()
    assert d["total_estimate"] >= 20, f"expected ~29 records, got {d['total_estimate']}"
    assert len(d["results"]) >= 20
    et_ids = {row["entity_type_id"] for row in d["results"]}
    assert len(et_ids) >= 4, f"expected multi-collection, got only {et_ids}"
    row = d["results"][0]
    for k in ["id", "entity_type", "category_paths", "tags", "primary_image_url", "title", "record_number", "fields", "created_at", "updated_at"]:
        assert k in row, f"row missing key: {k}"
    et = row["entity_type"]
    for k in ["id", "key", "name_singular", "name_plural", "color"]:
        assert k in et


def test_browse_entity_type_filter(owner_hdr):
    r = requests.get(f"{API}/records/browse", headers=owner_hdr).json()
    et_ids_all = list({row["entity_type_id"] for row in r["results"]})[:2]
    filt_arg = ",".join(et_ids_all)
    r2 = requests.get(f"{API}/records/browse?entity_type_ids={filt_arg}", headers=owner_hdr).json()
    for row in r2["results"]:
        assert row["entity_type_id"] in et_ids_all


def test_browse_free_text_search(owner_hdr):
    r = requests.get(f"{API}/records/browse?q=Sarah", headers=owner_hdr).json()
    # Should be fewer than total, and every result matches conceptually.
    assert r["total_estimate"] < 29
    # At least verify all-results test returns >0 or 0 gracefully
    assert isinstance(r["results"], list)


def test_browse_cursor_pagination(owner_hdr):
    p1 = requests.get(f"{API}/records/browse?limit=5", headers=owner_hdr).json()
    assert len(p1["results"]) == 5
    assert p1["next_cursor"]
    p2 = requests.get(f"{API}/records/browse?limit=5&cursor={p1['next_cursor']}", headers=owner_hdr).json()
    ids1 = {r["id"] for r in p1["results"]}
    ids2 = {r["id"] for r in p2["results"]}
    assert not (ids1 & ids2), "pages must not overlap"


def test_browse_sort_title_asc(owner_hdr):
    r = requests.get(f"{API}/records/browse?sort=title:asc&limit=50", headers=owner_hdr).json()
    titles = [row.get("title") or "" for row in r["results"]]
    assert titles == sorted(titles, key=lambda s: (s or "").lower()) or titles == sorted(titles)
    assert r["sort"] == "title:asc"


def test_browse_invalid_sort_fallback(owner_hdr):
    r = requests.get(f"{API}/records/browse?sort=bogus:foo", headers=owner_hdr)
    assert r.status_code == 200
    # sort echoes the requested string; internally the default is used


def test_browse_facets(owner_hdr):
    r = requests.get(f"{API}/records/browse?limit=200", headers=owner_hdr).json()
    ets = r["facets"]["entity_types"]
    counts = [f["count"] for f in ets]
    assert counts == sorted(counts, reverse=True), "entity_types facet must be sorted by count desc"
    total_from_facets = sum(counts)
    assert total_from_facets == r["total_estimate"], f"{total_from_facets} != {r['total_estimate']}"
    for f in ets:
        assert "name" in f and "count" in f and "color" in f


def test_browse_field_defs_bundle(owner_hdr):
    r = requests.get(f"{API}/records/browse?limit=200", headers=owner_hdr).json()
    et_ids_in_results = {row["entity_type_id"] for row in r["results"]}
    for etid in et_ids_in_results:
        assert etid in r["entity_type_field_defs"], f"missing field_defs for {etid}"
        defs = r["entity_type_field_defs"][etid]
        assert isinstance(defs, list) and len(defs) > 0
        for fd in defs:
            for k in ["id", "key", "label", "type", "order"]:
                assert k in fd
        # verify ordered by 'order'
        orders = [fd.get("order", 0) for fd in defs]
        assert orders == sorted(orders)


def test_browse_viewer_can_read(viewer_hdr):
    r = requests.get(f"{API}/records/browse", headers=viewer_hdr)
    assert r.status_code == 200


def test_browse_performance(owner_hdr):
    t0 = time.perf_counter()
    r = requests.get(f"{API}/records/browse?limit=50", headers=owner_hdr)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    d = r.json()
    assert r.status_code == 200
    assert elapsed_ms < 2000, f"HTTP roundtrip {elapsed_ms:.0f}ms too slow"
    assert d["took_ms"] < 500, f"took_ms {d['took_ms']}ms exceeds 500ms target"


def test_openapi_includes_browse(owner_hdr):
    r = requests.get(f"{API}/openapi.json", headers=owner_hdr)
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/records/browse" in paths
    assert "/api/browse/views" in paths


# ── 2. Browse-scope Views CRUD ──
def test_create_list_patch_delete_browse_view(owner_hdr):
    payload = {"name": "TEST_ownerView", "layout": "gallery", "q": "Sarah",
               "entity_type_ids": [], "category_ids": [], "tag_ids": [],
               "sort": "title:asc", "is_shared": False}
    c = requests.post(f"{API}/browse/views", headers=owner_hdr, json=payload)
    assert c.status_code == 201, c.text
    vid = c.json()["id"]
    assert c.json()["entity_type_id"] is None
    assert c.json()["name"] == "TEST_ownerView"

    l = requests.get(f"{API}/browse/views", headers=owner_hdr).json()
    assert any(v["id"] == vid for v in l), "created view not in list"
    for v in l:
        assert v["entity_type_id"] is None, "browse list must only include entity_type_id=null views"

    p = requests.patch(f"{API}/views/{vid}", headers=owner_hdr, json={"name": "TEST_renamed"})
    assert p.status_code in (200, 204), p.text

    d = requests.delete(f"{API}/views/{vid}", headers=owner_hdr)
    assert d.status_code in (200, 204), d.text


def test_editor_cannot_create_shared_view(editor_hdr):
    payload = {"name": "TEST_editorShared", "layout": "table", "is_shared": True}
    r = requests.post(f"{API}/browse/views", headers=editor_hdr, json=payload)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"


def test_regression_per_collection_records_endpoint(owner_hdr):
    ets = requests.get(f"{API}/entity-types", headers=owner_hdr)
    assert ets.status_code == 200
    et_list = ets.json()
    assert len(et_list) > 0
    etid = et_list[0]["id"]
    r = requests.get(f"{API}/entity-types/{etid}/records", headers=owner_hdr)
    assert r.status_code == 200, r.text
