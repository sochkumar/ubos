"""UBOS Phase 4 Sub-pass A tests — shares, public payload, QR/barcode, labels, sensitive fields."""
from __future__ import annotations

import io
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://org-platform-13.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

OWNER = ("owner@ubos.test", "OwnerPass!123")
EDITOR = ("editor@ubos.test", "EditorPass!123")


# ────────── fixtures ──────────
@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(f"{API}/auth/login", json={"email": OWNER[0], "password": OWNER[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def editor_token():
    r = requests.post(f"{API}/auth/login", json={"email": EDITOR[0], "password": EDITOR[1]})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def entity_type(owner_token):
    """Create a fresh entity type + sensitive field + non-sensitive field."""
    slug = f"testp4a{uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/entity-types", headers=_h(owner_token),
                      json={"key": slug, "name_singular": f"TEST_p4a_{slug}",
                            "name_plural": f"TEST_p4a_{slug}s", "slug": slug, "icon": "package"})
    assert r.status_code in (200, 201), r.text
    et_id = r.json()["id"]

    # Non-sensitive field
    r1 = requests.post(f"{API}/entity-types/{et_id}/fields", headers=_h(owner_token),
                       json={"key": "sku", "label": "SKU", "type": "text", "order": 1})
    assert r1.status_code in (200, 201), r1.text

    # Sensitive field (top-level flag)
    r2 = requests.post(f"{API}/entity-types/{et_id}/fields", headers=_h(owner_token),
                       json={"key": "ssn", "label": "SSN", "type": "text", "order": 2, "sensitive": True})
    assert r2.status_code in (200, 201), r2.text
    fd = r2.json()
    assert fd.get("sensitive") is True, f"expected sensitive:true, got {fd}"

    # Second sensitive via legacy config.sensitive
    r3 = requests.post(f"{API}/entity-types/{et_id}/fields", headers=_h(owner_token),
                       json={"key": "internal_note", "label": "Note", "type": "text", "order": 3,
                             "config": {"sensitive": True}})
    assert r3.status_code in (200, 201), r3.text

    # Third non-sensitive field for visible_fields intersection testing
    r4 = requests.post(f"{API}/entity-types/{et_id}/fields", headers=_h(owner_token),
                       json={"key": "price", "label": "Price", "type": "text", "order": 4})
    assert r4.status_code in (200, 201), r4.text
    return et_id


@pytest.fixture(scope="session")
def record_id(owner_token, entity_type):
    r = requests.post(f"{API}/entity-types/{entity_type}/records", headers=_h(owner_token),
                      json={"title": "TEST_p4a Widget", "fields": {
                          "sku": "SKU-001", "ssn": "SECRET-999", "internal_note": "hush",
                          "price": "42.50"}})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ────────── sensitive field ──────────
class TestSensitiveField:
    def test_field_list_shows_sensitive_flag(self, owner_token, entity_type):
        r = requests.get(f"{API}/entity-types/{entity_type}/fields", headers=_h(owner_token))
        assert r.status_code == 200
        fields = r.json()
        by_key = {f["key"]: f for f in fields}
        assert by_key["ssn"].get("sensitive") is True
        assert by_key["sku"].get("sensitive") in (False, None)

    def test_authed_record_still_shows_sensitive(self, owner_token, entity_type, record_id):
        r = requests.get(f"{API}/records/{record_id}", headers=_h(owner_token))
        assert r.status_code == 200
        rec = r.json()
        assert rec["fields"].get("ssn") == "SECRET-999", "authed member must still see sensitive value"

    def test_patch_field_sensitive(self, owner_token, entity_type):
        r = requests.post(f"{API}/entity-types/{entity_type}/fields", headers=_h(owner_token),
                          json={"key": "tmp_flag", "label": "Tmp", "type": "text", "order": 9})
        fid = r.json()["id"]
        p = requests.patch(f"{API}/fields/{fid}", headers=_h(owner_token), json={"sensitive": True})
        assert p.status_code == 200, p.text
        assert p.json().get("sensitive") is True


# ────────── share CRUD ──────────
class TestShareCRUD:
    def test_create_list_share(self, owner_token, record_id):
        body = {"visibility": "public", "include_media": True, "include_relationships": False}
        r = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token), json=body)
        assert r.status_code == 201, r.text
        s = r.json()
        assert s["token"]
        assert s["public_url"].endswith(f"/s/{s['token']}")
        assert s["visibility"] == "public"

        lr = requests.get(f"{API}/records/{record_id}/shares", headers=_h(owner_token))
        assert lr.status_code == 200
        assert any(x.get("id") == s.get("id") for x in lr.json())

    def test_two_shares_same_record(self, owner_token, record_id):
        r1 = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                           json={"visibility": "public"})
        r2 = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                           json={"visibility": "public"})
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["token"] != r2.json()["token"]

    def test_revoke_and_delete(self, owner_token, record_id):
        r = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                          json={"visibility": "public"}).json()
        sid = r.get("id") or r.get("_id")
        rv = requests.post(f"{API}/shares/{sid}/revoke", headers=_h(owner_token))
        assert rv.status_code == 200
        assert rv.json().get("revoked_at")
        # Public read → 410
        pub = requests.get(f"{API}/public/records/{r['token']}")
        assert pub.status_code == 410
        assert pub.json().get("detail", {}).get("code") == "share_expired_or_revoked"
        # Delete
        d = requests.delete(f"{API}/shares/{sid}", headers=_h(owner_token))
        assert d.status_code == 204

    def test_editor_cannot_revoke_owner_share(self, owner_token, editor_token, record_id):
        # NOTE: seeded owner + editor users are in SEPARATE orgs, so this
        # test validates cross-org isolation (404) rather than same-org 403.
        r = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                          json={"visibility": "public"}).json()
        sid = r.get("id") or r.get("_id")
        rv = requests.post(f"{API}/shares/{sid}/revoke", headers=_h(editor_token))
        assert rv.status_code in (403, 404), rv.text


# ────────── public payload / visibility ──────────
class TestPublicPayload:
    def _mk_share(self, token, record_id, **kw):
        body = {"visibility": "public"}
        body.update(kw)
        r = requests.post(f"{API}/records/{record_id}/shares", headers=_h(token), json=body)
        assert r.status_code == 201, r.text
        return r.json()

    def test_public_read_no_auth_ok(self, owner_token, record_id):
        s = self._mk_share(owner_token, record_id)
        r = requests.get(f"{API}/public/records/{s['token']}")
        assert r.status_code == 200
        p = r.json()
        assert p["record"]["title"] == "TEST_p4a Widget"
        # sensitive fields stripped
        assert "ssn" not in p["record"]["fields"]
        assert "internal_note" not in p["record"]["fields"]
        assert p["record"]["fields"].get("sku") == "SKU-001"
        # field_defs also strip sensitive
        keys = {fd["key"] for fd in p["field_defs"]}
        assert "ssn" not in keys and "internal_note" not in keys
        assert "sku" in keys
        # org info
        assert p["org"].get("name")

    def test_try_auth_with_bad_token_still_ok(self, owner_token, record_id):
        s = self._mk_share(owner_token, record_id)
        r = requests.get(f"{API}/public/records/{s['token']}",
                         headers={"Authorization": "Bearer garbage-token-xyz"})
        assert r.status_code == 200, r.text

    def test_visible_fields_none_returns_all_non_sensitive(self, owner_token, record_id):
        s = self._mk_share(owner_token, record_id, visible_fields=None)
        r = requests.get(f"{API}/public/records/{s['token']}").json()
        assert set(r["record"]["fields"].keys()) == {"sku", "price"}

    def test_visible_fields_empty_returns_title_only(self, owner_token, record_id):
        s = self._mk_share(owner_token, record_id, visible_fields=[])
        r = requests.get(f"{API}/public/records/{s['token']}").json()
        assert r["record"]["fields"] == {}
        assert r["field_defs"] == []
        assert r["record"]["title"] and r["record"]["record_number"]

    def test_visible_fields_intersection(self, owner_token, record_id):
        s = self._mk_share(owner_token, record_id, visible_fields=["sku", "ssn", "price"])
        r = requests.get(f"{API}/public/records/{s['token']}").json()
        # ssn is sensitive, so must be excluded
        assert set(r["record"]["fields"].keys()) == {"sku", "price"}

    def test_org_only_401_without_auth(self, owner_token, record_id):
        s = self._mk_share(owner_token, record_id, visibility="org_only")
        r = requests.get(f"{API}/public/records/{s['token']}")
        assert r.status_code == 401

    def test_org_only_200_with_matching_org_auth(self, owner_token, record_id):
        s = self._mk_share(owner_token, record_id, visibility="org_only")
        r = requests.get(f"{API}/public/records/{s['token']}", headers=_h(owner_token))
        assert r.status_code == 200

    def test_private_401_without_auth(self, owner_token, record_id):
        s = self._mk_share(owner_token, record_id, visibility="private")
        r = requests.get(f"{API}/public/records/{s['token']}")
        assert r.status_code == 401

    def test_expired_share_410(self, owner_token, record_id):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        s = self._mk_share(owner_token, record_id, expires_at=past)
        r = requests.get(f"{API}/public/records/{s['token']}")
        assert r.status_code == 410
        assert r.json()["detail"]["code"] == "share_expired_or_revoked"

    def test_unknown_token_404(self):
        r = requests.get(f"{API}/public/records/nope-not-real")
        assert r.status_code == 404


# ────────── QR / Barcode ──────────
class TestQRBarcode:
    def test_authed_qr_png(self, owner_token, record_id):
        r = requests.get(f"{API}/records/{record_id}/qr.png", headers=_h(owner_token))
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")
        assert len(r.content) > 400
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_authed_barcode_png(self, owner_token, record_id):
        r = requests.get(f"{API}/records/{record_id}/barcode.png", headers=_h(owner_token))
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("image/png")
        assert len(r.content) > 400

    def test_public_qr_only_for_public_share(self, owner_token, record_id):
        s = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                          json={"visibility": "public"}).json()
        r = requests.get(f"{API}/public/records/{s['token']}/qr.png")
        assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"

        s2 = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                           json={"visibility": "org_only"}).json()
        r2 = requests.get(f"{API}/public/records/{s2['token']}/qr.png")
        assert r2.status_code == 401

    def test_public_barcode_png(self, owner_token, record_id):
        s = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                          json={"visibility": "public"}).json()
        r = requests.get(f"{API}/public/records/{s['token']}/barcode.png")
        assert r.status_code == 200 and r.content[:8] == b"\x89PNG\r\n\x1a\n"


# ────────── Labels ──────────
class TestLabels:
    def test_presets_endpoint(self, owner_token):
        r = requests.get(f"{API}/labels/presets", headers=_h(owner_token))
        assert r.status_code == 200
        presets = r.json()
        keys = {p["key"] if "key" in p else p.get("id") for p in presets} if isinstance(presets, list) else set(presets.keys())
        for k in ("avery_5160", "avery_5163", "avery_l7160", "avery_l7163"):
            assert k in keys, f"missing preset {k}: got {keys}"

    def test_records_labels_pdf(self, owner_token, record_id):
        r = requests.post(f"{API}/records/labels", headers=_h(owner_token),
                          json={"record_ids": [record_id],
                                "config": {"preset": "avery_5160", "copies_per_record": 3}})
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 10_000
        assert r.content[:4] == b"%PDF"

    def test_records_labels_invalid_preset(self, owner_token, record_id):
        r = requests.post(f"{API}/records/labels", headers=_h(owner_token),
                          json={"record_ids": [record_id], "config": {"preset": "bogus"}})
        assert r.status_code in (400, 422), r.text

    def test_view_scoped_labels(self, owner_token, entity_type, record_id):
        r = requests.post(f"{API}/entity-types/{entity_type}/records/labels",
                          headers=_h(owner_token),
                          json={"filters": [], "config": {"preset": "avery_5160"}})
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"%PDF"
        assert "X-Records-Included" in r.headers


# ────────── Rate limiter ──────────
class TestRateLimit:
    def test_public_read_rate_limit(self, owner_token, record_id):
        s = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                          json={"visibility": "public"}).json()
        url = f"{API}/public/records/{s['token']}"
        # Use unique XFF to isolate this test's bucket
        xff = f"9.9.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
        hits = []
        for _ in range(80):
            r = requests.get(url, headers={"X-Forwarded-For": xff})
            hits.append(r.status_code)
            if r.status_code == 429:
                assert r.json().get("detail", {}).get("code") == "rate_limited"
                break
        assert 429 in hits, f"expected a 429 in {len(hits)} hits, got {set(hits)}"

    def test_rate_limit_buckets_per_ip(self, owner_token, record_id):
        s = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                          json={"visibility": "public"}).json()
        url = f"{API}/public/records/{s['token']}"
        # Different IP → should still be 200 even after other IP got 429
        xff = f"7.7.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
        r = requests.get(url, headers={"X-Forwarded-For": xff})
        assert r.status_code == 200


# ────────── Relationships summary ──────────
class TestRelationshipsSummary:
    def test_include_relationships_returns_summaries(self, owner_token, record_id):
        s = requests.post(f"{API}/records/{record_id}/shares", headers=_h(owner_token),
                          json={"visibility": "public", "include_relationships": True}).json()
        r = requests.get(f"{API}/public/records/{s['token']}")
        assert r.status_code == 200
        rels = r.json().get("relationships", [])
        # Should be a list; each group has label/direction/items (may be empty)
        assert isinstance(rels, list)
        for g in rels:
            assert set(["label", "direction", "items"]).issubset(g.keys())
            for it in g["items"]:
                # Only summary keys — no full 'fields' payload
                assert "fields" not in it
                assert set(it.keys()).issubset({"title", "record_number", "entity_type_name"})
