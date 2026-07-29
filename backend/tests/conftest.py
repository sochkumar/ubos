"""Shared test fixtures for the UBOS backend suite.

The suite runs under `pytest -n 2 --dist loadfile`, so each test file is
pinned to one worker. Fixtures declared here are module-scoped where they
provision a fresh isolated org (test hygiene) and session-scoped where they
tap into the pre-seeded Acme workspace.

Directive 2 (2026-02): legacy tests that used the pre-Phase-5 `X-Org-Id`
header have been rewritten to obtain a JWT via /api/auth/register + POST
/api/orgs, giving each test module its own tenant sandbox.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ─────────────── transient-fault resilient HTTP transport ───────────────
# Under `-n 2 --dist loadfile` the two test workers burst hundreds of
# requests per second at the k8s ingress. The ingress occasionally 502s or
# drops a fresh TCP handshake on start-up, so we install a global retry
# policy for the `requests` module. Applies once per Python process on
# collection — pure defensive, does NOT change any test assertion semantics.
def _install_global_retries() -> None:
    retry = Retry(
        total=2, connect=2, read=1, status=1, backoff_factor=0.15,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["GET", "POST", "PATCH", "DELETE", "PUT"]),
        raise_on_status=False,
        # CRITICAL: do NOT honor server's Retry-After header. Auth 429 responses
        # ship `Retry-After: 899` (15 minutes) to slow brute force; if urllib3
        # respects it, the test process sleeps for up to 30 minutes before the
        # 429 status even surfaces to the assertion. Rate-limit tests must see
        # the 429 immediately.
        respect_retry_after_header=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=40)
    orig_session_init = requests.Session.__init__

    def _patched_init(self, *args, **kwargs):
        orig_session_init(self, *args, **kwargs)
        self.mount("http://", adapter)
        self.mount("https://", adapter)

    requests.Session.__init__ = _patched_init  # type: ignore[assignment]


_install_global_retries()


def _get_backend_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    return v.rstrip("/")


BASE_URL = _get_backend_url()
API = f"{BASE_URL}/api"


# ─────────────────────────── shared auth helpers ───────────────────────────
def login(email: str, password: str) -> dict:
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login {email} -> {r.status_code}: {r.text}"
    return r.json()


def register(email: str, password: str, name: str = "Test User") -> dict:
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": password, "name": name},
                      timeout=20)
    assert r.status_code == 201, f"register {email} -> {r.status_code}: {r.text}"
    return r.json()


def make_org(access_token: str, name: str, slug: str) -> dict:
    r = requests.post(
        f"{API}/orgs",
        json={"name": name, "slug": slug},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    assert r.status_code == 201, f"create org {slug} -> {r.status_code}: {r.text}"
    return r.json()


def h_bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def h_json(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _reset_public_rate_limits_now() -> None:
    """Best-effort clear of the server's in-memory rate-limit buckets.

    Call this at the start of tests that need a clean `pub_read` / unlock
    bucket. It logs in as the seeded owner (which has `org.update`) and
    invokes the RBAC-guarded `/api/dev/reset-rate-limits` endpoint.
    """
    try:
        owner = requests.post(f"{API}/auth/login",
                              json={"email": "owner@ubos.test",
                                    "password": "OwnerPass!123"}, timeout=15)
        if owner.status_code == 200:
            tok = owner.json()["access_token"]
            requests.post(f"{API}/dev/reset-rate-limits",
                          headers={"Authorization": f"Bearer {tok}"}, timeout=10)
    except Exception:  # noqa: BLE001 — reset is best-effort
        pass


@pytest.fixture
def reset_rate_limits():
    """Function-scoped fixture: reset in-memory rate-limit buckets before AND
    after the test. Opt-in only — modules that need isolation from other
    workers' `pub_read:{ip}` bucket depend on it explicitly instead of the
    fixture being auto-applied and stomping on parallel tests."""
    _reset_public_rate_limits_now()
    yield
    _reset_public_rate_limits_now()


@pytest.fixture(scope="session", autouse=True)
def _restore_seeded_users_active_org():
    """Pin the seeded users to their canonical org before the suite runs.

    Legacy tests (e.g. `test_ubos_phase3b_patch.TestFreshOrgQuota`) create
    extra orgs owned by the shared seed users and never clean them up. Over
    time this pollutes the login flow — when `active_org_id=None`, the
    server picks the *first* org from membership order, which may end up
    being a leftover empty test org instead of the intended Acme workspace.

    This fixture:
    1. Removes leftover `TEST_QuotaOrg_*` memberships from seeded users.
    2. Forces `active_org_id` back to the Acme org.
    Runs once per session and only touches deterministic test-created state.
    """
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")

    async def _restore():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        try:
            acme = await db.organizations.find_one({"slug": "acme-furniture"})
            if not acme:
                return
            acme_id = acme["_id"]
            for email in ("owner@ubos.test", "editor@ubos.test", "viewer@ubos.test"):
                user = await db.users.find_one({"email": email})
                if not user:
                    continue
                uid = user["_id"]
                async for org in db.organizations.find(
                    {"$or": [{"name": {"$regex": "^TEST_QuotaOrg_"}},
                             {"slug": {"$regex": "^test-quotaorg-"}}]}
                ):
                    await db.memberships.delete_many(
                        {"user_id": uid, "org_id": org["_id"]}
                    )
                await db.users.update_one(
                    {"_id": uid},
                    {"$set": {"active_org_id": acme_id,
                              "default_org_id": acme_id}}
                )
        finally:
            client.close()

    asyncio.run(_restore())
    yield


@pytest.fixture(scope="session")
def acme_owner() -> dict:
    """Login response for the seeded owner user in Acme Furniture."""
    return login("owner@ubos.test", "OwnerPass!123")


@pytest.fixture(scope="session")
def acme_editor() -> dict:
    return login("editor@ubos.test", "EditorPass!123")


@pytest.fixture(scope="session")
def acme_viewer() -> dict:
    return login("viewer@ubos.test", "ViewerPass!123")


# ─────────────────────────── fresh-org fixture ───────────────────────────
class FreshOrg:
    """Bundle of everything a test needs to talk to a brand-new org sandbox."""

    __slots__ = ("token", "org_id", "user_id", "email", "slug")

    def __init__(self, token: str, org_id: str, user_id: str, email: str, slug: str):
        self.token = token
        self.org_id = org_id
        self.user_id = user_id
        self.email = email
        self.slug = slug

    def h(self) -> dict:
        return h_bearer(self.token)

    def hj(self) -> dict:
        return h_json(self.token)


def _provision_fresh_org(label: str) -> FreshOrg:
    """Register a unique user, create an org for it, return the FreshOrg bundle.

    Called by module-scoped fixtures so each test file gets a clean sandbox.
    """
    suffix = uuid.uuid4().hex[:10]
    email = f"qa+{label}-{suffix}@ubos.test"
    password = "TestPass!123"
    reg = register(email, password, name=f"QA {label}")
    org = make_org(
        reg["access_token"],
        name=f"QA {label} {suffix}",
        slug=f"qa-{label}-{suffix}",
    )
    # `POST /orgs` returns `{org: {...}, access_token: ..., refresh_token: ...}`
    return FreshOrg(
        token=org["access_token"],
        org_id=org["org"]["id"],
        user_id=reg["user"]["id"],
        email=email,
        slug=org["org"]["slug"],
    )


@pytest.fixture(scope="module")
def fresh_org(request) -> FreshOrg:
    """Provision an isolated org for the test module. Auto-derives a label
    from the module filename (e.g. `test_ubos_phase0.py` -> `phase0`)."""
    mod = os.path.splitext(os.path.basename(request.node.fspath))[0]
    label = mod.replace("test_ubos_", "").replace("test_", "").replace("_", "-")[:24]
    return _provision_fresh_org(label)


@pytest.fixture(scope="module")
def fresh_org_alt(request) -> FreshOrg:
    """A second isolated org, useful for tenant-isolation tests."""
    mod = os.path.splitext(os.path.basename(request.node.fspath))[0]
    label = "alt-" + mod.replace("test_ubos_", "").replace("test_", "").replace("_", "-")[:20]
    return _provision_fresh_org(label)
