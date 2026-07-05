"""Verify jti fix: consecutive login/refresh return distinct access tokens."""
import os
import base64
import json
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else None
# fallback to frontend .env
if not BASE:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE = ln.split("=", 1)[1].strip().rstrip("/")

CREDS = {"email": "owner@ubos.test", "password": "OwnerPass!123"}


def _decode_payload(tok):
    parts = tok.split(".")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    return json.loads(base64.urlsafe_b64decode(payload.encode()))


def test_consecutive_logins_return_distinct_access_tokens():
    r1 = requests.post(f"{BASE}/api/auth/login", json=CREDS)
    r2 = requests.post(f"{BASE}/api/auth/login", json=CREDS)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    t1 = r1.json()["access_token"]
    t2 = r2.json()["access_token"]
    assert t1 != t2, "access tokens should differ (jti)"
    p1 = _decode_payload(t1)
    p2 = _decode_payload(t2)
    assert "jti" in p1 and "jti" in p2
    assert p1["jti"] != p2["jti"]
    assert 10 <= len(p1["jti"]) <= 32


def test_consecutive_refresh_returns_distinct_access_tokens():
    login = requests.post(f"{BASE}/api/auth/login", json=CREDS).json()
    rt = login["refresh_token"]
    a1 = requests.post(f"{BASE}/api/auth/refresh", json={"refresh_token": rt})
    assert a1.status_code == 200, a1.text
    rt2 = a1.json()["refresh_token"]
    a2 = requests.post(f"{BASE}/api/auth/refresh", json={"refresh_token": rt2})
    assert a2.status_code == 200, a2.text
    assert a1.json()["access_token"] != a2.json()["access_token"]
    p1 = _decode_payload(a1.json()["access_token"])
    p2 = _decode_payload(a2.json()["access_token"])
    assert p1.get("jti") != p2.get("jti")
