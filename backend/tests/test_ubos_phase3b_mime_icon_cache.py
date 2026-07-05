"""Sub-pass B micro-patch tests: mime-icon Cache-Control / ETag / 304
revalidation, at BOTH origin (localhost:8001) and via public ingress.

The Cloudflare/ingress layer of preview.emergentagent.com is known to
rewrite `Cache-Control` to `no-store,no-cache,must-revalidate`. This is
environment behaviour outside the app's control — tests for
Cache-Control target ONLY the origin. Through the ingress we validate
ETag + Last-Modified pass-through + 304 revalidation which is what
delivers the real browser-cache win.
"""
from __future__ import annotations

import os
import requests
import pytest

ORIGIN = "http://localhost:8001"
INGRESS = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://org-platform-13.preview.emergentagent.com",
).rstrip("/")

FAMILIES = ["pdf", "doc", "xls", "ppt", "txt", "video", "audio", "image", "generic"]


def _get(base, path, headers=None):
    return requests.get(f"{base}{path}", headers=headers or {},
                        timeout=15, allow_redirects=False)


# ─────────────────────── ORIGIN tests ─────────────────────────────────
class TestMimeIconAtOrigin:
    """Direct hit on localhost:8001 — no CDN in the path."""

    def test_pdf_headers_and_body(self):
        r = _get(ORIGIN, "/api/media/mime-icon/pdf")
        assert r.status_code == 200, r.text[:200]
        # Cache-Control from origin
        cc = r.headers.get("Cache-Control", "")
        assert "public" in cc and "max-age=86400" in cc and "immutable" in cc, cc
        # CDN-Cache-Control mirrors it
        cdn = r.headers.get("CDN-Cache-Control", "")
        assert "public" in cdn and "max-age=86400" in cdn and "immutable" in cdn, cdn
        # ETag present, quoted, md5-hex
        etag = r.headers.get("ETag", "")
        assert etag.startswith('"') and etag.endswith('"'), etag
        assert len(etag) == 34, etag  # "..." with 32 hex chars
        # Last-Modified fixed epoch
        assert r.headers.get("Last-Modified") == "Sat, 01 Jan 2000 00:00:00 GMT"
        # Vary
        assert "Accept-Encoding" in r.headers.get("Vary", "")
        # Content-Type
        assert r.headers.get("Content-Type", "").startswith("image/svg+xml")
        # SVG body
        body = r.text.lstrip()
        assert body.startswith("<") and "svg" in body.lower(), body[:80]

    def test_if_none_match_returns_304(self):
        r1 = _get(ORIGIN, "/api/media/mime-icon/pdf")
        etag = r1.headers["ETag"]
        r2 = _get(ORIGIN, "/api/media/mime-icon/pdf",
                  headers={"If-None-Match": etag})
        assert r2.status_code == 304, (r2.status_code, r2.text[:120])
        # 304 body must be empty
        assert (r2.content or b"") == b"", r2.content[:80]
        # Same ETag echoed back
        assert r2.headers.get("ETag") == etag
        # Cache-Control still present
        cc = r2.headers.get("Cache-Control", "")
        assert "public" in cc and "max-age=86400" in cc
        cdn = r2.headers.get("CDN-Cache-Control", "")
        assert "public" in cdn and "max-age=86400" in cdn

    def test_mismatched_if_none_match_returns_200(self):
        r = _get(ORIGIN, "/api/media/mime-icon/pdf",
                 headers={"If-None-Match": '"bogus"'})
        assert r.status_code == 200
        assert r.headers.get("Content-Type", "").startswith("image/svg+xml")
        body = r.text.lstrip()
        assert body.startswith("<") and "svg" in body.lower()

    def test_all_families_distinct_etags_same_cache_control(self):
        etags = {}
        for fam in FAMILIES:
            r = _get(ORIGIN, f"/api/media/mime-icon/{fam}")
            assert r.status_code == 200, f"{fam}: {r.status_code}"
            assert r.headers.get("Content-Type", "").startswith("image/svg+xml")
            cc = r.headers.get("Cache-Control", "")
            assert "public" in cc and "max-age=86400" in cc and "immutable" in cc, \
                f"{fam} cc={cc}"
            body = r.text.lstrip()
            assert body.startswith("<") and "svg" in body.lower(), \
                f"{fam} body={body[:80]}"
            etags[fam] = r.headers["ETag"]
        # All 9 ETags distinct
        assert len(set(etags.values())) == len(FAMILIES), etags

    def test_unknown_family_ok(self):
        r = _get(ORIGIN, "/api/media/mime-icon/wibble")
        assert r.status_code == 200
        assert r.headers.get("Content-Type", "").startswith("image/svg+xml")
        cc = r.headers.get("Cache-Control", "")
        assert "public" in cc and "max-age=86400" in cc and "immutable" in cc
        assert r.headers.get("ETag", "").startswith('"')
        body = r.text.lstrip()
        assert body.startswith("<") and "svg" in body.lower()


# ─────────────────────── INGRESS tests ────────────────────────────────
class TestMimeIconThroughIngress:
    """Through public URL — Cache-Control may be rewritten by Cloudflare;
    we only enforce that ETag/Last-Modified pass through and that the
    304 revalidation still works end-to-end."""

    def test_etag_and_last_modified_pass_through(self):
        r = _get(INGRESS, "/api/media/mime-icon/pdf")
        assert r.status_code == 200, r.text[:200]
        et = r.headers.get("ETag", "")
        # Cloudflare may downgrade strong ETag to weak (W/"...") when it
        # re-gzips the body. Both forms are acceptable.
        assert (et.startswith('"') or et.startswith('W/"')), et
        assert r.headers.get("Last-Modified"), r.headers

    def test_if_none_match_304_through_ingress(self):
        r1 = _get(INGRESS, "/api/media/mime-icon/pdf")
        etag = r1.headers["ETag"]
        r2 = _get(INGRESS, "/api/media/mime-icon/pdf",
                  headers={"If-None-Match": etag})
        assert r2.status_code == 304, (r2.status_code, r2.headers, r2.text[:120])
        # zero bytes on the wire
        assert (r2.content or b"") == b"", r2.content[:80]
