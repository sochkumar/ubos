"""UBOS Phase 0 backend tests — entity types, fields, records, validation, tenant isolation.

Directive 2 rewrite (2026-02): the original Phase 0 tests predated JWT auth
and used the `X-Org-Id` header. Auth has been JWT-only since Phase 5. This
rewrite drives the same behavior through the current auth surface and
provisions a fresh isolated org per test module (see `conftest.fresh_org`).

The old `TestSeedDemo` class was removed because `/api/dev/seed-demo` now
delegates to the `demo_basic` template applier with a different response
shape — that logic is covered by the Phase 2 template tests.
"""
from __future__ import annotations

import uuid

import pytest
import requests

from conftest import API, _provision_fresh_org


@pytest.fixture(scope="session")
def s():
    return requests.Session()


# ═══════════════════════════ Health / OpenAPI ═══════════════════════════
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

    def test_entity_types_requires_auth(self, s):
        """Without a bearer token the entity-types listing must be rejected."""
        r = s.get(f"{API}/entity-types", timeout=15)
        assert r.status_code == 401


# ═══════════════════════════ Entity types ═══════════════════════════
class TestEntityTypes:
    def test_invalid_key_422(self, s, fresh_org):
        r = s.post(f"{API}/entity-types", headers=fresh_org.hj(), json={
            "key": "BadKey", "name_singular": "X", "name_plural": "Xs",
        })
        assert r.status_code == 422

    def test_create_list_duplicate(self, s, fresh_org):
        key = f"widgets_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/entity-types", headers=fresh_org.hj(), json={
            "key": key, "name_singular": "Widget", "name_plural": "Widgets",
        })
        assert r.status_code == 201, r.text
        et = r.json()
        assert et["key"] == key
        assert et["record_counter"] == 0

        r = s.get(f"{API}/entity-types", headers=fresh_org.h())
        assert r.status_code == 200
        assert any(x["key"] == key for x in r.json())

        r = s.post(f"{API}/entity-types", headers=fresh_org.hj(), json={
            "key": key, "name_singular": "W", "name_plural": "Ws",
        })
        assert r.status_code == 409

    def test_patch_and_delete_cascade(self, s, fresh_org):
        key = f"cascade_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/entity-types", headers=fresh_org.hj(), json={
            "key": key, "name_singular": "C", "name_plural": "Cs",
        })
        et_id = r.json()["id"]

        r = s.patch(f"{API}/entity-types/{et_id}", headers=fresh_org.hj(),
                    json={"description": "updated"})
        assert r.status_code == 200
        assert r.json()["description"] == "updated"

        rf = s.post(f"{API}/entity-types/{et_id}/fields", headers=fresh_org.hj(),
                    json={"key": "name", "label": "Name", "type": "text", "required": True})
        assert rf.status_code == 201

        rr = s.post(f"{API}/entity-types/{et_id}/records", headers=fresh_org.hj(),
                    json={"fields": {"name": "hello"}})
        assert rr.status_code == 201

        r = s.delete(f"{API}/entity-types/{et_id}", headers=fresh_org.h())
        assert r.status_code == 204

        r = s.get(f"{API}/entity-types/{et_id}", headers=fresh_org.h())
        assert r.status_code == 404
        r = s.get(f"{API}/entity-types/{et_id}/fields", headers=fresh_org.h())
        assert r.status_code == 404
        r = s.get(f"{API}/entity-types/{et_id}/records", headers=fresh_org.h())
        assert r.status_code == 404


# ═══════════════════════════ Fields ═══════════════════════════
@pytest.fixture(scope="module")
def products_et(fresh_org):
    """Create a per-module Products entity type with the canonical field set."""
    s = requests.Session()
    key = f"products_{uuid.uuid4().hex[:6]}"
    r = s.post(f"{API}/entity-types", headers=fresh_org.hj(), json={
        "key": key, "name_singular": "Product", "name_plural": "Products",
    })
    assert r.status_code == 201, r.text
    et = r.json()
    specs = [
        {"key": "sku", "label": "SKU", "type": "text", "required": True, "unique": True},
        {"key": "price", "label": "Price", "type": "currency", "required": True,
         "config": {"min": 0}},
        {"key": "in_stock", "label": "In stock", "type": "boolean"},
        {"key": "category", "label": "Category", "type": "dropdown",
         "config": {"options": ["chair", "table", "sofa"]}},
        {"key": "launch_date", "label": "Launch date", "type": "date"},
        {"key": "notes", "label": "Notes", "type": "longtext"},
    ]
    for spec in specs:
        rf = s.post(f"{API}/entity-types/{et['id']}/fields",
                    headers=fresh_org.hj(), json=spec)
        assert rf.status_code == 201, rf.text
    yield et
    s.delete(f"{API}/entity-types/{et['id']}", headers=fresh_org.h())


class TestFields:
    def test_create_and_list_ordered(self, s, fresh_org):
        key = f"fields_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/entity-types", headers=fresh_org.hj(), json={
            "key": key, "name_singular": "F", "name_plural": "Fs"})
        et_id = r.json()["id"]
        try:
            specs = [
                {"key": "sku", "label": "SKU", "type": "text", "required": True, "unique": True},
                {"key": "price", "label": "Price", "type": "currency", "required": True,
                 "config": {"min": 0}},
                {"key": "in_stock", "label": "In stock", "type": "boolean"},
                {"key": "category", "label": "Category", "type": "dropdown",
                 "config": {"options": ["chair", "table", "sofa"]}},
                {"key": "launch_date", "label": "Launch date", "type": "date"},
                {"key": "notes", "label": "Notes", "type": "longtext"},
            ]
            ids = []
            for spec in specs:
                r = s.post(f"{API}/entity-types/{et_id}/fields",
                           headers=fresh_org.hj(), json=spec)
                assert r.status_code == 201, r.text
                ids.append(r.json()["id"])

            r = s.get(f"{API}/entity-types/{et_id}/fields", headers=fresh_org.h())
            assert r.status_code == 200
            assert [f["key"] for f in r.json()] == [
                "sku", "price", "in_stock", "category", "launch_date", "notes",
            ]

            r = s.post(f"{API}/entity-types/{et_id}/fields", headers=fresh_org.hj(),
                       json={"key": "sku", "label": "X", "type": "text"})
            assert r.status_code == 409

            r = s.post(f"{API}/entity-types/{et_id}/fields", headers=fresh_org.hj(),
                       json={"key": "bogus", "label": "X", "type": "bogus_type"})
            assert r.status_code == 422

            r = s.patch(f"{API}/fields/{ids[0]}", headers=fresh_org.hj(),
                        json={"label": "SKU!"})
            assert r.status_code == 200
            assert r.json()["label"] == "SKU!"

            new_order = list(reversed(ids))
            r = s.post(f"{API}/entity-types/{et_id}/fields/reorder",
                       headers=fresh_org.hj(), json={"order": new_order})
            assert r.status_code == 200
            r = s.get(f"{API}/entity-types/{et_id}/fields", headers=fresh_org.h())
            assert [f["id"] for f in r.json()] == new_order
        finally:
            s.delete(f"{API}/entity-types/{et_id}", headers=fresh_org.h())


# ═══════════════════════════ Records + validation ═══════════════════════════
class TestRecords:
    def test_missing_required(self, s, fresh_org, products_et):
        et_id = products_et["id"]
        r = s.post(f"{API}/entity-types/{et_id}/records", headers=fresh_org.hj(),
                   json={"fields": {"price": 10}})
        assert r.status_code == 422
        d = r.json()["detail"]
        assert d["errors"]["fields.sku"] == "is required"

    def test_negative_price(self, s, fresh_org, products_et):
        et_id = products_et["id"]
        r = s.post(f"{API}/entity-types/{et_id}/records", headers=fresh_org.hj(),
                   json={"fields": {"sku": "TMP-N1", "price": -5}})
        assert r.status_code == 422
        assert "at least 0" in r.json()["detail"]["errors"]["fields.price"]

    def test_dropdown_invalid(self, s, fresh_org, products_et):
        et_id = products_et["id"]
        r = s.post(f"{API}/entity-types/{et_id}/records", headers=fresh_org.hj(),
                   json={"fields": {"sku": "TMP-D1", "price": 5,
                                    "category": "not-real"}})
        assert r.status_code == 422
        assert "fields.category" in r.json()["detail"]["errors"]

    def test_create_valid_and_duplicate(self, s, fresh_org, products_et):
        et_id = products_et["id"]
        r = s.post(f"{API}/entity-types/{et_id}/records", headers=fresh_org.hj(),
                   json={"fields": {"sku": "A-001", "price": 9.99, "category": "chair",
                                    "in_stock": True, "launch_date": "2025-01-01",
                                    "notes": "hello"}})
        assert r.status_code == 201, r.text
        rec = r.json()
        assert rec["record_number"].startswith("REC-")
        first_num = int(rec["record_number"].split("-")[1])

        # duplicate SKU
        r2 = s.post(f"{API}/entity-types/{et_id}/records", headers=fresh_org.hj(),
                    json={"fields": {"sku": "A-001", "price": 1, "category": "chair"}})
        assert r2.status_code == 422
        assert "unique" in r2.json()["detail"]["errors"]["fields.sku"]

        # another valid — counter increments
        r3 = s.post(f"{API}/entity-types/{et_id}/records", headers=fresh_org.hj(),
                    json={"fields": {"sku": "A-002", "price": 1, "category": "table"}})
        assert r3.status_code == 201
        assert int(r3.json()["record_number"].split("-")[1]) == first_num + 1

        # list
        rl = s.get(f"{API}/entity-types/{et_id}/records", headers=fresh_org.h())
        assert rl.status_code == 200
        assert rl.json()["total"] >= 2

        # PATCH
        rec_id = rec["id"]
        rp = s.patch(f"{API}/records/{rec_id}", headers=fresh_org.hj(),
                     json={"fields": {"price": 19.99}})
        assert rp.status_code == 200
        assert rp.json()["fields"]["price"] == 19.99
        assert rp.json()["fields"]["sku"] == "A-001"

        # DELETE
        rd = s.delete(f"{API}/records/{rec_id}", headers=fresh_org.h())
        assert rd.status_code == 204
        assert s.get(f"{API}/records/{rec_id}", headers=fresh_org.h()).status_code == 404
        rl2 = s.get(f"{API}/entity-types/{et_id}/records", headers=fresh_org.h())
        ids = [x["id"] for x in rl2.json()["items"]]
        assert rec_id not in ids


# ═══════════════════════════ Tenant isolation ═══════════════════════════
class TestTenantIsolation:
    """Two independent orgs must not see each other's entity types or records."""

    def test_orgs_isolated(self, s):
        # Provision two fresh orgs in the same worker; we can't rely on the
        # module fresh_org fixtures because we need two independent sandboxes.
        org_a = _provision_fresh_org("iso-a")
        org_b = _provision_fresh_org("iso-b")

        key = f"iso_{uuid.uuid4().hex[:6]}"
        ra = s.post(f"{API}/entity-types", headers=org_a.hj(),
                    json={"key": key, "name_singular": "I", "name_plural": "Is"})
        assert ra.status_code == 201, ra.text
        et_a_id = ra.json()["id"]

        list_a = s.get(f"{API}/entity-types", headers=org_a.h()).json()
        list_b = s.get(f"{API}/entity-types", headers=org_b.h()).json()
        assert any(x["id"] == et_a_id for x in list_a)
        assert not any(x["id"] == et_a_id for x in list_b)

        # Org B cannot reach Org A's ET by direct GET.
        r = s.get(f"{API}/entity-types/{et_a_id}", headers=org_b.h())
        assert r.status_code == 404

        # Same key should be usable in Org B without collision.
        rb = s.post(f"{API}/entity-types", headers=org_b.hj(),
                    json={"key": key, "name_singular": "I", "name_plural": "Is"})
        assert rb.status_code == 201, rb.text
