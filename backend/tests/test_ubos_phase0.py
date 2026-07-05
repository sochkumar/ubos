"""UBOS Phase 0 backend tests — entity types, fields, records, validation, tenant isolation, seed idempotency."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend env
    from dotenv import dotenv_values
    v = dotenv_values("/app/frontend/.env")
    BASE_URL = (v.get("REACT_APP_BACKEND_URL") or "").rstrip("/")

API = f"{BASE_URL}/api"


def _h(org="demo-org"):
    return {"Content-Type": "application/json", "X-Org-Id": org}


@pytest.fixture(scope="session")
def s():
    return requests.Session()


# ---- Health / OpenAPI ----
class TestHealth:
    def test_health(self, s):
        r = s.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["db"] == "up"

    def test_openapi(self, s):
        r = s.get(f"{API}/openapi.json", timeout=15)
        assert r.status_code == 200
        assert "paths" in r.json()

    def test_no_org_header_defaults(self, s):
        r = s.get(f"{API}/entity-types", timeout=15)
        assert r.status_code == 200


# ---- Entity Types ----
@pytest.fixture(scope="session")
def cleanup_keys():
    # Track test entity-type keys so we can soft-delete them at end
    return set()


class TestEntityTypes:
    def test_invalid_key_422(self, s):
        r = s.post(f"{API}/entity-types", headers=_h(), json={
            "key": "BadKey", "name_singular": "X", "name_plural": "Xs"
        })
        assert r.status_code == 422

    def test_create_list_duplicate(self, s, cleanup_keys):
        key = "test_widgets"
        cleanup_keys.add(key)
        # ensure clean start: try delete if exists
        lst = s.get(f"{API}/entity-types", headers=_h()).json()
        for et in lst:
            if et["key"] == key:
                s.delete(f"{API}/entity-types/{et['id']}", headers=_h())

        r = s.post(f"{API}/entity-types", headers=_h(), json={
            "key": key, "name_singular": "Widget", "name_plural": "Widgets",
        })
        assert r.status_code == 201, r.text
        et = r.json()
        assert et["key"] == key
        assert et["record_counter"] == 0

        # list
        r = s.get(f"{API}/entity-types", headers=_h())
        assert r.status_code == 200
        assert any(x["key"] == key for x in r.json())

        # duplicate
        r = s.post(f"{API}/entity-types", headers=_h(), json={
            "key": key, "name_singular": "W", "name_plural": "Ws",
        })
        assert r.status_code == 409

    def test_patch_and_delete_cascade(self, s, cleanup_keys):
        key = "test_cascade"
        cleanup_keys.add(key)
        r = s.post(f"{API}/entity-types", headers=_h(), json={
            "key": key, "name_singular": "C", "name_plural": "Cs",
        })
        et_id = r.json()["id"]

        # patch
        r = s.patch(f"{API}/entity-types/{et_id}", headers=_h(),
                    json={"description": "updated"})
        assert r.status_code == 200
        assert r.json()["description"] == "updated"

        # add a field
        rf = s.post(f"{API}/entity-types/{et_id}/fields", headers=_h(),
                    json={"key": "name", "label": "Name", "type": "text", "required": True})
        assert rf.status_code == 201
        fid = rf.json()["id"]

        # add a record
        rr = s.post(f"{API}/entity-types/{et_id}/records", headers=_h(),
                    json={"fields": {"name": "hello"}})
        assert rr.status_code == 201

        # delete cascade
        r = s.delete(f"{API}/entity-types/{et_id}", headers=_h())
        assert r.status_code == 204

        # entity-type not visible
        r = s.get(f"{API}/entity-types/{et_id}", headers=_h())
        assert r.status_code == 404

        # fields not listed under it (endpoint should 404 because ET soft-deleted)
        r = s.get(f"{API}/entity-types/{et_id}/fields", headers=_h())
        assert r.status_code == 404

        # records list also 404
        r = s.get(f"{API}/entity-types/{et_id}/records", headers=_h())
        assert r.status_code == 404


# ---- Fields ----
@pytest.fixture(scope="module")
def products_et():
    s = requests.Session()
    key = "test_products"
    # clean any existing
    for et in s.get(f"{API}/entity-types", headers=_h()).json():
        if et["key"] == key:
            s.delete(f"{API}/entity-types/{et['id']}", headers=_h())
    r = s.post(f"{API}/entity-types", headers=_h(), json={
        "key": key, "name_singular": "Product", "name_plural": "Products",
    })
    et = r.json()
    # seed fields
    specs = [
        {"key": "sku", "label": "SKU", "type": "text", "required": True, "unique": True},
        {"key": "price", "label": "Price", "type": "currency", "required": True, "config": {"min": 0}},
        {"key": "in_stock", "label": "In stock", "type": "boolean"},
        {"key": "category", "label": "Category", "type": "dropdown",
         "config": {"options": ["chair", "table", "sofa"]}},
        {"key": "launch_date", "label": "Launch date", "type": "date"},
        {"key": "notes", "label": "Notes", "type": "longtext"},
    ]
    for spec in specs:
        s.post(f"{API}/entity-types/{et['id']}/fields", headers=_h(), json=spec)
    yield et
    s.delete(f"{API}/entity-types/{et['id']}", headers=_h())


class TestFields:
    def test_create_and_list_ordered(self, s):
        # Use a fresh ET so we control field creation
        key = "test_fields_et"
        for et in s.get(f"{API}/entity-types", headers=_h()).json():
            if et["key"] == key:
                s.delete(f"{API}/entity-types/{et['id']}", headers=_h())
        r = s.post(f"{API}/entity-types", headers=_h(), json={
            "key": key, "name_singular": "F", "name_plural": "Fs"})
        et_id = r.json()["id"]
        try:
            specs = [
                {"key": "sku", "label": "SKU", "type": "text", "required": True, "unique": True},
                {"key": "price", "label": "Price", "type": "currency", "required": True, "config": {"min": 0}},
                {"key": "in_stock", "label": "In stock", "type": "boolean"},
                {"key": "category", "label": "Category", "type": "dropdown",
                 "config": {"options": ["chair", "table", "sofa"]}},
                {"key": "launch_date", "label": "Launch date", "type": "date"},
                {"key": "notes", "label": "Notes", "type": "longtext"},
            ]
            ids = []
            for spec in specs:
                r = s.post(f"{API}/entity-types/{et_id}/fields", headers=_h(), json=spec)
                assert r.status_code == 201, r.text
                ids.append(r.json()["id"])

            r = s.get(f"{API}/entity-types/{et_id}/fields", headers=_h())
            assert r.status_code == 200
            fields = r.json()
            assert [f["key"] for f in fields] == ["sku", "price", "in_stock", "category", "launch_date", "notes"]

            # duplicate
            r = s.post(f"{API}/entity-types/{et_id}/fields", headers=_h(),
                       json={"key": "sku", "label": "X", "type": "text"})
            assert r.status_code == 409

            # unknown type
            r = s.post(f"{API}/entity-types/{et_id}/fields", headers=_h(),
                       json={"key": "bogus", "label": "X", "type": "bogus_type"})
            assert r.status_code == 422

            # patch a field
            r = s.patch(f"{API}/fields/{ids[0]}", headers=_h(), json={"label": "SKU!"})
            assert r.status_code == 200
            assert r.json()["label"] == "SKU!"

            # reorder: reverse order
            new_order = list(reversed(ids))
            r = s.post(f"{API}/entity-types/{et_id}/fields/reorder", headers=_h(),
                       json={"order": new_order})
            assert r.status_code == 200
            r = s.get(f"{API}/entity-types/{et_id}/fields", headers=_h())
            assert [f["id"] for f in r.json()] == new_order
        finally:
            s.delete(f"{API}/entity-types/{et_id}", headers=_h())


# ---- Records + Validation ----
class TestRecords:
    def test_missing_required(self, s, products_et):
        et_id = products_et["id"]
        r = s.post(f"{API}/entity-types/{et_id}/records", headers=_h(),
                   json={"fields": {"price": 10}})
        assert r.status_code == 422
        d = r.json()["detail"]
        assert d["errors"]["fields.sku"] == "is required"

    def test_negative_price(self, s, products_et):
        et_id = products_et["id"]
        r = s.post(f"{API}/entity-types/{et_id}/records", headers=_h(),
                   json={"fields": {"sku": "TMP-N1", "price": -5}})
        assert r.status_code == 422
        assert "at least 0" in r.json()["detail"]["errors"]["fields.price"]

    def test_dropdown_invalid(self, s, products_et):
        et_id = products_et["id"]
        r = s.post(f"{API}/entity-types/{et_id}/records", headers=_h(),
                   json={"fields": {"sku": "TMP-D1", "price": 5, "category": "not-real"}})
        assert r.status_code == 422
        assert "fields.category" in r.json()["detail"]["errors"]

    def test_create_valid_and_duplicate(self, s, products_et):
        et_id = products_et["id"]
        r = s.post(f"{API}/entity-types/{et_id}/records", headers=_h(),
                   json={"fields": {"sku": "A-001", "price": 9.99, "category": "chair",
                                    "in_stock": True, "launch_date": "2025-01-01",
                                    "notes": "hello"}})
        assert r.status_code == 201, r.text
        rec = r.json()
        assert rec["record_number"].startswith("REC-")
        first_num = int(rec["record_number"].split("-")[1])

        # duplicate SKU
        r2 = s.post(f"{API}/entity-types/{et_id}/records", headers=_h(),
                    json={"fields": {"sku": "A-001", "price": 1, "category": "chair"}})
        assert r2.status_code == 422
        assert "unique" in r2.json()["detail"]["errors"]["fields.sku"]

        # another valid — counter increments
        r3 = s.post(f"{API}/entity-types/{et_id}/records", headers=_h(),
                    json={"fields": {"sku": "A-002", "price": 1, "category": "table"}})
        assert r3.status_code == 201
        assert int(r3.json()["record_number"].split("-")[1]) == first_num + 1

        # list
        rl = s.get(f"{API}/entity-types/{et_id}/records", headers=_h())
        assert rl.status_code == 200
        d = rl.json()
        assert d["total"] >= 2

        # PATCH
        rec_id = rec["id"]
        rp = s.patch(f"{API}/records/{rec_id}", headers=_h(),
                     json={"fields": {"price": 19.99}})
        assert rp.status_code == 200
        assert rp.json()["fields"]["price"] == 19.99
        assert rp.json()["fields"]["sku"] == "A-001"

        # DELETE
        rd = s.delete(f"{API}/records/{rec_id}", headers=_h())
        assert rd.status_code == 204
        rg = s.get(f"{API}/records/{rec_id}", headers=_h())
        assert rg.status_code == 404
        # not visible in list
        rl2 = s.get(f"{API}/entity-types/{et_id}/records", headers=_h())
        ids = [x["id"] for x in rl2.json()["items"]]
        assert rec_id not in ids


# ---- Tenant Isolation ----
class TestTenantIsolation:
    def test_orgs_isolated(self, s):
        key = "test_iso"
        # cleanup both orgs
        for org in ("org-a", "org-b"):
            for et in s.get(f"{API}/entity-types", headers=_h(org)).json():
                if et["key"] == key:
                    s.delete(f"{API}/entity-types/{et['id']}", headers=_h(org))

        ra = s.post(f"{API}/entity-types", headers=_h("org-a"),
                    json={"key": key, "name_singular": "I", "name_plural": "Is"})
        assert ra.status_code == 201
        et_a = ra.json()["id"]

        # visible in org-a, not org-b
        la = s.get(f"{API}/entity-types", headers=_h("org-a")).json()
        lb = s.get(f"{API}/entity-types", headers=_h("org-b")).json()
        assert any(x["id"] == et_a for x in la)
        assert not any(x["id"] == et_a for x in lb)

        # direct GET by ID in org-b should 404
        r = s.get(f"{API}/entity-types/{et_a}", headers=_h("org-b"))
        assert r.status_code == 404

        s.delete(f"{API}/entity-types/{et_a}", headers=_h("org-a"))


# ---- Seed idempotency & per-ET counter ----
class TestSeedDemo:
    def test_seed_idempotent_and_counters(self, s):
        # cleanup demo entity types
        for k in ("products", "machines"):
            for et in s.get(f"{API}/entity-types", headers=_h()).json():
                if et["key"] == k:
                    s.delete(f"{API}/entity-types/{et['id']}", headers=_h())

        r1 = s.post(f"{API}/dev/seed-demo", headers=_h())
        assert r1.status_code == 200
        r2 = s.post(f"{API}/dev/seed-demo", headers=_h())
        assert r2.status_code == 200
        # After second call, no ET should be "created"
        for et in r2.json()["entity_types"]:
            assert et["created"] is False
        # no additional records created
        assert r2.json()["created_records"] == 0

        # counters independent + start at 1
        ets = {e["key"]: e for e in s.get(f"{API}/entity-types", headers=_h()).json()}
        prod = ets["products"]
        mach = ets["machines"]
        prod_recs = s.get(f"{API}/entity-types/{prod['id']}/records", headers=_h()).json()["items"]
        mach_recs = s.get(f"{API}/entity-types/{mach['id']}/records", headers=_h()).json()["items"]
        # sorted by created_at desc -> take min
        prod_nums = sorted(int(r["record_number"].split("-")[1]) for r in prod_recs)
        mach_nums = sorted(int(r["record_number"].split("-")[1]) for r in mach_recs)
        assert prod_nums[0] == 1
        assert mach_nums[0] == 1
