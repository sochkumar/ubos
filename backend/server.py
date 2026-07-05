"""UBOS server — Phase 1 entrypoint.

Wires all routers, initializes DB indexes, seeds the demo users + org on empty DB.
All endpoints are under /api. OpenAPI at /api/openapi.json.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from db import ensure_indexes, get_client, get_db
from routes.auth import router as auth_router
from routes.oauth_google import router as oauth_router
from routes.orgs import router as orgs_router
from routes.data import router as data_router
from routes.categories import router as categories_router
from routes.tags import router as tags_router
from routes.relationships import router as relationships_router
from routes.templates import router as templates_router
from routes.audit import router as audit_router
from routes.dev import router as dev_router
from routes._org_helpers import create_organization, add_membership
from security import hash_password

app = FastAPI(
    title="UBOS API",
    version="0.2.0-phase1",
    description="Universal Business Operating System — Phase 1 (Auth + Orgs + RBAC).",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,  # bearer tokens; no cookies
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ubos")


# ─────────────────────── root api router ───────────────────────
api = APIRouter(prefix="/api")


@api.get("/health", tags=["health"])
async def health():
    try:
        await get_db().command("ping")
        return {"status": "ok", "db": "up", "version": "0.2.0-phase1"}
    except Exception as e:  # pragma: no cover
        return JSONResponse({"status": "degraded", "db": "down", "error": str(e)}, status_code=503)


api.include_router(auth_router)
api.include_router(oauth_router)
api.include_router(orgs_router)
api.include_router(data_router)
api.include_router(categories_router)
api.include_router(tags_router)
api.include_router(relationships_router)
api.include_router(templates_router)
api.include_router(audit_router)
api.include_router(dev_router)

app.include_router(api)


# ─────────────────────── startup ───────────────────────
async def _seed_demo_users_and_org() -> None:
    """Create the 3 test users + 'Acme Furniture' org, idempotently."""
    if os.environ.get("SEED_USERS", "true").lower() != "true":
        return
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    async def upsert_user(email: str, password: str, name: str) -> dict:
        u = await db.users.find_one({"email": email})
        if u:
            return u
        u = {
            "_id": str(uuid.uuid4()),
            "email": email,
            "password_hash": hash_password(password),
            "name": name,
            "avatar_url": None,
            "google_sub": None,
            "default_org_id": None,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        await db.users.insert_one(u)
        log.info("seeded user %s", email)
        return u

    owner = await upsert_user("owner@ubos.test", "OwnerPass!123", "Alex Owner")
    editor = await upsert_user("editor@ubos.test", "EditorPass!123", "Erin Editor")
    viewer = await upsert_user("viewer@ubos.test", "ViewerPass!123", "Val Viewer")

    org = await db.organizations.find_one({"slug": "acme-furniture", "deleted_at": None})
    if not org:
        org = await create_organization(
            db, name="Acme Furniture", slug="acme-furniture",
            creator_user_id=owner["_id"], make_default=True,
        )
        log.info("seeded org %s (%s)", org["name"], org["_id"])

    async def ensure_membership(user_id: str, role_name: str) -> None:
        exists = await db.memberships.find_one({"user_id": user_id, "org_id": org["_id"]})
        if not exists:
            await add_membership(db, user_id=user_id, org_id=org["_id"], role_name=role_name)

    await ensure_membership(editor["_id"], "editor")
    await ensure_membership(viewer["_id"], "viewer")

    # Ensure editor/viewer have Acme as their default org too
    for u in (editor, viewer):
        if not u.get("default_org_id"):
            await db.users.update_one(
                {"_id": u["_id"]}, {"$set": {"default_org_id": org["_id"]}}
            )


async def _wipe_phase0_demo_org() -> None:
    """Phase 1 migration: Phase 0 stored everything under 'demo-org'. Wipe those."""
    db = get_db()
    n = await db.entity_types.count_documents({"org_id": "demo-org"})
    if n:
        await db.entity_types.delete_many({"org_id": "demo-org"})
        await db.field_definitions.delete_many({"org_id": "demo-org"})
        await db.records.delete_many({"org_id": "demo-org"})
        log.info("phase-1 migration: removed %d demo-org entity_types + their fields/records", n)


@app.on_event("startup")
async def _startup():
    await ensure_indexes()
    await _wipe_phase0_demo_org()
    await _seed_demo_users_and_org()
    log.info("UBOS Phase 1 backend ready — Google=%s",
             "enabled" if os.environ.get("GOOGLE_CLIENT_ID", "REPLACE_ME") not in ("", "REPLACE_ME") else "disabled")


@app.on_event("shutdown")
async def _shutdown():
    get_client().close()
