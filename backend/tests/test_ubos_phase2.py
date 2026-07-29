"""UBOS Phase 2 backend tests — templates, categories, tags, relationships,
records-with-category/tag, RBAC.

Uses seed users; assumes Acme Furniture workspace was wiped by the main agent
before this run (per handoff note). Tests are self-cleaning where possible.
"""
import os
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


def _login(s, email, password):
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def s():
    return requests.Session()


@pytest.fixture(scope="session")
def owner_tok(s):
    return _login(s, *OWNER)["access_token"]


@pytest.fixture(scope="session")
def editor_tok(s):
    return _login(s, *EDITOR)["access_token"]


@pytest.fixture(scope="session")
def viewer_tok(s):
    return _login(s, *VIEWER)["access_token"]


# ============================================================================
# Templates
# ============================================================================
class TestTemplates:
    def test_list_returns_5_builtins(self, s, owner_tok):
        # NOTE: the catalog has grown well past the original 5 seeded
        # templates (bakery/furniture/jewellery store etc.). Assert the
        # core keys are present and every entry has the required shape.
        r = s.get(f"{API}/templates", headers=_hdr(owner_tok), timeout=15)
        assert r.status_code == 200
        items = r.json()
        keys = {t["key"] for t in items}
        # The 5 originals must still be there — anything else is welcome.
        expected_core = {"assets", "catalog", "crm_lite", "demo_basic", "inventory_lite"}
        assert expected_core.issubset(keys), f"missing core templates: {expected_core - keys}"
        for t in items:
            assert "entity_type_count" in t
            assert "relationship_count" in t
            assert "tag_count" in t

    def test_get_catalog_preview_full(self, s, owner_tok):
        r = s.get(f"{API}/templates/catalog", headers=_hdr(owner_tok), timeout=15)
        assert r.status_code == 200
        spec = r.json()
        assert spec["key"] == "catalog"
        assert len(spec["entity_types"]) == 1
        et = spec["entity_types"][0]
        assert et["key"] == "products"
        assert et["field_count"] == 6
        # Nested categories preserved
        assert len(et["categories"]) == 1
        assert et["categories"][0]["name"] == "Furniture"
        assert len(et["categories"][0]["children"]) == 3

    def test_dry_run_no_writes(self, s, fresh_org):
        # Uses a fresh isolated org so we can assert the "no products yet"
        # invariant. Acme has products pre-applied by seed.
        hdr = fresh_org.hj()
        r = s.post(f"{API}/templates/catalog/apply",
                   json={"dry_run": True, "conflict_policy": "skip"},
                   headers=hdr, timeout=15)
        assert r.status_code == 200
        plan = r.json()
        assert plan["dry_run"] is True
        assert plan["entity_types"][0]["key"] == "products"
        assert plan["entity_types"][0]["fields"] == 6
        assert plan["entity_types"][0]["categories"] == 4  # Furniture + 3 children
        assert plan["tags"] == 2
        # Verify no products entity was created
        et_list = s.get(f"{API}/entity-types", headers=hdr).json()
        assert not any(e["key"] == "products" for e in et_list)

    def test_apply_skip_creates_entities(self, s, fresh_org):
        hdr = fresh_org.hj()
        # First apply — nothing to conflict with since we're in a fresh org.
        r = s.post(f"{API}/templates/catalog/apply",
                   json={"dry_run": False, "conflict_policy": "skip"},
                   headers=hdr, timeout=30)
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["dry_run"] is False
        ins = res["inserted"]
        assert ins.get("entity_types") == 1
        assert ins.get("field_definitions") == 6
        assert ins.get("categories") == 4
        assert ins.get("tags") == 2

    def test_apply_second_time_skip_noop(self, s, owner_tok):
        r = s.post(f"{API}/templates/catalog/apply",
                   json={"dry_run": False, "conflict_policy": "skip"},
                   headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200
        # nothing new inserted
        assert r.json().get("inserted", {}) == {}

    def test_apply_error_conflicts(self, s, owner_tok):
        r = s.post(f"{API}/templates/catalog/apply",
                   json={"dry_run": False, "conflict_policy": "error"},
                   headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 409, r.text

    def test_apply_rename_creates_products_2(self, s, owner_tok):
        r = s.post(f"{API}/templates/catalog/apply",
                   json={"dry_run": False, "conflict_policy": "rename"},
                   headers=_hdr(owner_tok), timeout=30)
        assert r.status_code == 200
        # find the renamed one
        et_list = s.get(f"{API}/entity-types", headers=_hdr(owner_tok)).json()
        renamed_keys = [e["key"] for e in et_list if e["key"].startswith("products_")]
        assert any(k == "products_2" for k in renamed_keys), renamed_keys
        # cleanup the renamed one so subsequent tests are unaffected
        for e in et_list:
            if e["key"].startswith("products_"):
                s.delete(f"{API}/entity-types/{e['id']}", headers=_hdr(owner_tok))


# ============================================================================
# Categories tree, move, rename, cascade delete, depth cap
# ============================================================================
@pytest.fixture(scope="module")
def products_et_id(s, owner_tok):
    """Return the id of the products entity_type. Assumes catalog was applied."""
    et_list = s.get(f"{API}/entity-types", headers=_hdr(owner_tok)).json()
    for e in et_list:
        if e["key"] == "products":
            return e["id"]
    pytest.skip("products entity_type not applied")


class TestCategoriesTree:
    def test_nested_tree_from_catalog(self, s, owner_tok, products_et_id):
        r = s.get(f"{API}/entity-types/{products_et_id}/categories",
                  headers=_hdr(owner_tok), timeout=15)
        assert r.status_code == 200
        roots = r.json()
        assert len(roots) == 1
        furn = roots[0]
        assert furn["name"] == "Furniture"
        assert furn["depth"] == 0
        assert len(furn["path"]) == 1
        assert furn["path_names"] == ["Furniture"]
        assert len(furn["children"]) == 3
        for ch in furn["children"]:
            assert ch["depth"] == 1
            assert ch["path_names"][0] == "Furniture"

    def test_flat_returns_sorted(self, s, owner_tok, products_et_id):
        r = s.get(f"{API}/entity-types/{products_et_id}/categories?flat=true",
                  headers=_hdr(owner_tok), timeout=15)
        assert r.status_code == 200
        flat = r.json()
        assert len(flat) == 4
        depths = [d["depth"] for d in flat]
        assert depths == sorted(depths)


class TestCategoryOps:
    def test_create_move_rename_delete(self, s, owner_tok, products_et_id):
        # create a temp root
        r = s.post(f"{API}/entity-types/{products_et_id}/categories",
                   json={"name": f"Zone-{uuid.uuid4().hex[:6]}"},
                   headers=_hdr(owner_tok), timeout=15)
        assert r.status_code == 201, r.text
        zone = r.json()
        assert zone["path"] == [zone["id"]]
        assert zone["depth"] == 0

        # create child under it
        r = s.post(f"{API}/entity-types/{products_et_id}/categories",
                   json={"name": "Alpha", "parent_id": zone["id"]},
                   headers=_hdr(owner_tok), timeout=15)
        assert r.status_code == 201
        alpha = r.json()
        assert alpha["path"] == [zone["id"], alpha["id"]]
        assert alpha["path_names"] == [zone["name"], "Alpha"]

        # rename zone → check descendant path_names recomputed
        new_name = f"Zone2-{uuid.uuid4().hex[:6]}"
        r = s.patch(f"{API}/categories/{zone['id']}",
                    json={"name": new_name}, headers=_hdr(owner_tok))
        assert r.status_code == 200
        # verify alpha's path_names updated
        r = s.get(f"{API}/categories/{alpha['id']}", headers=_hdr(owner_tok))
        assert r.status_code == 200
        assert r.json()["path_names"] == [new_name, "Alpha"]

        # move alpha under Furniture (find furniture id)
        tree = s.get(f"{API}/entity-types/{products_et_id}/categories",
                     headers=_hdr(owner_tok)).json()
        furn = next(x for x in tree if x["name"] == "Furniture")
        r = s.post(f"{API}/categories/{alpha['id']}/move",
                   json={"new_parent_id": furn["id"]}, headers=_hdr(owner_tok))
        assert r.status_code == 200, r.text
        moved = r.json()
        assert moved["parent_id"] == furn["id"]
        assert moved["path"] == [furn["id"], alpha["id"]]

        # circular: try moving furniture under alpha (its own descendant) → 400
        r = s.post(f"{API}/categories/{furn['id']}/move",
                   json={"new_parent_id": alpha["id"]}, headers=_hdr(owner_tok))
        assert r.status_code == 400

        # move under self → 400
        r = s.post(f"{API}/categories/{alpha['id']}/move",
                   json={"new_parent_id": alpha["id"]}, headers=_hdr(owner_tok))
        assert r.status_code == 400

        # cleanup: cascade delete zone
        r = s.delete(f"{API}/categories/{zone['id']}?cascade=true", headers=_hdr(owner_tok))
        assert r.status_code == 204
        # cleanup alpha which is now under Furniture
        s.delete(f"{API}/categories/{alpha['id']}?cascade=true", headers=_hdr(owner_tok))

    def test_delete_without_cascade_reparents(self, s, owner_tok, products_et_id):
        # parent + child
        r = s.post(f"{API}/entity-types/{products_et_id}/categories",
                   json={"name": f"P-{uuid.uuid4().hex[:6]}"},
                   headers=_hdr(owner_tok))
        parent = r.json()
        r = s.post(f"{API}/entity-types/{products_et_id}/categories",
                   json={"name": "child", "parent_id": parent["id"]},
                   headers=_hdr(owner_tok))
        child = r.json()

        # delete parent without cascade — child should reparent to null (root)
        r = s.delete(f"{API}/categories/{parent['id']}", headers=_hdr(owner_tok))
        assert r.status_code == 204
        # verify child in tree at root
        r = s.get(f"{API}/categories/{child['id']}", headers=_hdr(owner_tok))
        assert r.status_code == 200
        assert r.json()["parent_id"] is None

        # cleanup
        s.delete(f"{API}/categories/{child['id']}?cascade=true", headers=_hdr(owner_tok))

    def test_depth_cap_10(self, s, owner_tok, products_et_id):
        """Try to build depth 11 → 400."""
        parent_id = None
        created_ids = []
        # depth 0..9 → 10 levels total should succeed
        for i in range(10):
            r = s.post(f"{API}/entity-types/{products_et_id}/categories",
                       json={"name": f"L{i}-{uuid.uuid4().hex[:4]}",
                             "parent_id": parent_id},
                       headers=_hdr(owner_tok))
            assert r.status_code == 201, f"failed at depth {i}: {r.text}"
            parent_id = r.json()["id"]
            created_ids.append(parent_id)
        # 11th level → 400
        r = s.post(f"{API}/entity-types/{products_et_id}/categories",
                   json={"name": "L10", "parent_id": parent_id},
                   headers=_hdr(owner_tok))
        assert r.status_code == 400, r.text
        # cleanup: cascade-delete the root
        s.delete(f"{API}/categories/{created_ids[0]}?cascade=true",
                 headers=_hdr(owner_tok))


# ============================================================================
# Tags
# ============================================================================
class TestTags:
    def test_list_returns_seeded(self, s, owner_tok, products_et_id):
        r = s.get(f"{API}/tags?entity_type_id={products_et_id}",
                  headers=_hdr(owner_tok))
        assert r.status_code == 200
        names = [t["name"] for t in r.json()]
        assert "new-arrival" in names or "clearance" in names

    def test_create_idempotent(self, s, owner_tok):
        name = f"idem-{uuid.uuid4().hex[:6]}"
        r1 = s.post(f"{API}/tags", json={"name": name}, headers=_hdr(owner_tok))
        assert r1.status_code == 201
        r2 = s.post(f"{API}/tags", json={"name": name}, headers=_hdr(owner_tok))
        assert r2.status_code == 201
        assert r1.json()["id"] == r2.json()["id"]

    def test_editor_can_create_but_not_patch(self, s, editor_tok):
        # editor: create → 201
        name = f"editor-{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/tags", json={"name": name}, headers=_hdr(editor_tok))
        assert r.status_code == 201
        tid = r.json()["id"]
        # patch → 403
        r = s.patch(f"{API}/tags/{tid}", json={"color": "#000000"},
                    headers=_hdr(editor_tok))
        assert r.status_code == 403


# ============================================================================
# Records — category_ids + tag_ids + descendant filter
# ============================================================================
class TestRecordsWithCatsTags:
    def test_full_flow(self, s, owner_tok, products_et_id):
        # get furniture + chairs ids
        tree = s.get(f"{API}/entity-types/{products_et_id}/categories",
                     headers=_hdr(owner_tok)).json()
        furn = next(x for x in tree if x["name"] == "Furniture")
        chairs = next(c for c in furn["children"] if c["name"] == "Chairs")
        # get tags
        tags = s.get(f"{API}/tags?entity_type_id={products_et_id}",
                     headers=_hdr(owner_tok)).json()
        new_arrival = next(t for t in tags if t["name"] == "new-arrival")

        # create record under chairs with new-arrival tag
        rec_payload = {
            "fields": {"sku": f"SKU-{uuid.uuid4().hex[:6]}", "price": 100, "in_stock": True},
            "category_ids": [chairs["id"]],
            "tag_ids": [new_arrival["id"]],
        }
        r = s.post(f"{API}/entity-types/{products_et_id}/records",
                   json=rec_payload, headers=_hdr(owner_tok))
        assert r.status_code == 201, r.text
        rec = r.json()
        assert chairs["id"] in rec["category_ids"]
        assert new_arrival["id"] in rec["tag_ids"]

        # counters incremented
        c = s.get(f"{API}/categories/{chairs['id']}", headers=_hdr(owner_tok)).json()
        assert c["record_count"] >= 1
        t = s.get(f"{API}/tags?entity_type_id={products_et_id}",
                  headers=_hdr(owner_tok)).json()
        na = next(x for x in t if x["name"] == "new-arrival")
        assert na["usage_count"] >= 1

        # filter by chairs → returns
        r = s.get(f"{API}/entity-types/{products_et_id}/records?category_id={chairs['id']}",
                  headers=_hdr(owner_tok))
        assert r.status_code == 200
        assert any(x["id"] == rec["id"] for x in r.json()["items"])

        # filter by furniture (parent) → descendant match returns same record
        r = s.get(f"{API}/entity-types/{products_et_id}/records?category_id={furn['id']}",
                  headers=_hdr(owner_tok))
        assert r.status_code == 200
        assert any(x["id"] == rec["id"] for x in r.json()["items"]), \
            "Descendant filter should return records in child categories"

        # tag filter
        r = s.get(f"{API}/entity-types/{products_et_id}/records?tag_ids={new_arrival['id']}",
                  headers=_hdr(owner_tok))
        assert r.status_code == 200
        assert any(x["id"] == rec["id"] for x in r.json()["items"])

        # unknown ids silently dropped on create
        bad_payload = {
            "fields": {"sku": f"SKU-{uuid.uuid4().hex[:6]}", "price": 50},
            "category_ids": ["non-existent-id-xxx"],
            "tag_ids": ["non-existent-tag-yyy"],
        }
        r = s.post(f"{API}/entity-types/{products_et_id}/records",
                   json=bad_payload, headers=_hdr(owner_tok))
        assert r.status_code == 201
        assert r.json()["category_ids"] == []
        assert r.json()["tag_ids"] == []
        # cleanup
        s.delete(f"{API}/records/{r.json()['id']}", headers=_hdr(owner_tok))

        # update record: remove tag, verify decrement
        prev_count = na["usage_count"]
        r = s.patch(f"{API}/records/{rec['id']}",
                    json={"tag_ids": []}, headers=_hdr(owner_tok))
        assert r.status_code == 200
        t = s.get(f"{API}/tags?entity_type_id={products_et_id}",
                  headers=_hdr(owner_tok)).json()
        na2 = next(x for x in t if x["name"] == "new-arrival")
        assert na2["usage_count"] == prev_count - 1

        # delete record: category count decrements
        prev_cat = s.get(f"{API}/categories/{chairs['id']}",
                         headers=_hdr(owner_tok)).json()["record_count"]
        r = s.delete(f"{API}/records/{rec['id']}", headers=_hdr(owner_tok))
        assert r.status_code == 204
        c2 = s.get(f"{API}/categories/{chairs['id']}",
                   headers=_hdr(owner_tok)).json()
        assert c2["record_count"] == prev_cat - 1


# ============================================================================
# Relationships
# ============================================================================
class TestRelationships:
    def test_crud_and_dup(self, s, owner_tok):
        # create two entity types
        et1_key = f"tet1_{uuid.uuid4().hex[:6]}"
        et2_key = f"tet2_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/entity-types",
                   json={"key": et1_key, "name_singular": "A", "name_plural": "As"},
                   headers=_hdr(owner_tok))
        assert r.status_code == 201, r.text
        et1 = r.json()
        r = s.post(f"{API}/entity-types",
                   json={"key": et2_key, "name_singular": "B", "name_plural": "Bs"},
                   headers=_hdr(owner_tok))
        assert r.status_code == 201
        et2 = r.json()

        # create relationship
        rel_payload = {
            "to_entity_type_id": et2["id"], "key": "linked",
            "from_label": "Linked B", "to_label": "Belongs to A",
            "cardinality": "one_to_many",
        }
        r = s.post(f"{API}/entity-types/{et1['id']}/relationships",
                   json=rel_payload, headers=_hdr(owner_tok))
        assert r.status_code == 201, r.text
        rel = r.json()

        # duplicate key on same from → 409
        r = s.post(f"{API}/entity-types/{et1['id']}/relationships",
                   json=rel_payload, headers=_hdr(owner_tok))
        assert r.status_code == 409

        # list
        r = s.get(f"{API}/entity-types/{et1['id']}/relationships",
                  headers=_hdr(owner_tok))
        assert r.status_code == 200
        assert any(x["id"] == rel["id"] for x in r.json())

        # patch
        r = s.patch(f"{API}/relationships/definitions/{rel['id']}",
                    json={"from_label": "New Label"}, headers=_hdr(owner_tok))
        assert r.status_code == 200
        assert r.json()["from_label"] == "New Label"

        # cascade on delete of from entity type
        r = s.delete(f"{API}/entity-types/{et1['id']}", headers=_hdr(owner_tok))
        assert r.status_code == 204
        # relationship should now be soft-deleted (list from et2 side won't include; from et1 gone)
        # cleanup et2
        s.delete(f"{API}/entity-types/{et2['id']}", headers=_hdr(owner_tok))


# ============================================================================
# RBAC — viewer blocked on manage endpoints
# ============================================================================
class TestRBAC:
    def test_viewer_can_read(self, s, viewer_tok):
        assert s.get(f"{API}/templates", headers=_hdr(viewer_tok)).status_code == 200
        assert s.get(f"{API}/tags", headers=_hdr(viewer_tok)).status_code == 200

    def test_viewer_blocked_on_manage(self, s, viewer_tok, products_et_id):
        # apply template
        r = s.post(f"{API}/templates/catalog/apply",
                   json={"dry_run": False, "conflict_policy": "skip"},
                   headers=_hdr(viewer_tok))
        assert r.status_code == 403

        # create category
        r = s.post(f"{API}/entity-types/{products_et_id}/categories",
                   json={"name": "nope"}, headers=_hdr(viewer_tok))
        assert r.status_code == 403

        # create tag (records.create → viewer denied)
        r = s.post(f"{API}/tags", json={"name": "viewer-tag"},
                   headers=_hdr(viewer_tok))
        assert r.status_code == 403
