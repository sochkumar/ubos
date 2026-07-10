"""Standalone seed script — idempotent, safe to re-run (Phase 6-B).

Usage from repo root:
    cd /app/backend && python -m scripts.seed              # default
    cd /app/backend && python -m scripts.seed --reset      # purge non-canonical then seed
    cd /app/backend && python -m scripts.seed --minimal    # users + Acme only

Also called from FastAPI `lifespan` when the users collection is empty.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Allow running as `python scripts/seed.py` from /app/backend
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from db import ensure_indexes, get_db  # noqa: E402
from routes._org_helpers import add_membership, create_organization  # noqa: E402
from security import hash_password  # noqa: E402
from services.template_applier import apply_template  # noqa: E402

log = logging.getLogger("ubos.seed")

CANONICAL_USERS = [
    {"email": "owner@ubos.test", "password": "OwnerPass!123", "name": "Owner Test", "role": "owner"},
    {"email": "editor@ubos.test", "password": "EditorPass!123", "name": "Editor Test", "role": "editor"},
    {"email": "viewer@ubos.test", "password": "ViewerPass!123", "name": "Viewer Test", "role": "viewer"},
]
# Standalone demo user — NO org, NO memberships. On first login they land on
# the onboarding wizard exactly like a fresh sign-up, then create their own
# org and pick a starter pack. Used for demos + product walkthroughs.
DEMO_USER = {
    "email": "demo@ubos.test", "password": "DemoPass!123", "name": "Demo Owner",
}
ORG_NAME = "Acme Furniture"
ORG_SLUG = "acme-furniture"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _reset_non_canonical(db):
    """Purge everything not tied to the canonical org + users. Same policy the
    housekeeping script uses at the end of test runs."""
    canonical_emails = {u["email"] for u in CANONICAL_USERS} | {DEMO_USER["email"]}
    users = await db.users.find({"email": {"$nin": list(canonical_emails)}}).to_list(2000)
    delete_user_ids = [u["_id"] for u in users]
    acme = await db.organizations.find_one({"slug": ORG_SLUG})
    delete_org_ids = [
        o["_id"] for o in await db.organizations.find({}, {"_id": 1}).to_list(2000)
        if not acme or o["_id"] != acme["_id"]
    ]
    for coll in ("records", "entity_types", "field_definitions", "categories",
                 "tags", "views", "media", "share_links", "invitations",
                 "import_jobs", "audit_logs", "roles", "memberships",
                 "record_history", "record_relationships", "custom_dashboards",
                 "label_presets"):
        try:
            await db[coll].delete_many({"org_id": {"$in": delete_org_ids}})
        except Exception:  # noqa: BLE001
            pass
    if delete_org_ids:
        await db.organizations.delete_many({"_id": {"$in": delete_org_ids}})
    if delete_user_ids:
        for coll in ("refresh_tokens", "password_reset_tokens", "sessions",
                     "memberships"):
            try:
                await db[coll].delete_many({"user_id": {"$in": delete_user_ids}})
            except Exception:  # noqa: BLE001
                pass
        await db.users.delete_many({"_id": {"$in": delete_user_ids}})
    log.info("reset: purged %d users, %d orgs", len(delete_user_ids), len(delete_org_ids))


async def _upsert_user(db, u: dict) -> dict:
    existing = await db.users.find_one({"email": u["email"]})
    if existing:
        return existing
    doc = {
        "_id": str(uuid.uuid4()),
        "email": u["email"],
        "name": u["name"],
        "password_hash": hash_password(u["password"]),
        "is_active": True,
        "email_verified": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.users.insert_one(doc)
    log.info("created user %s", u["email"])
    return doc


async def _ensure_org(db, owner_user: dict) -> dict:
    org = await db.organizations.find_one({"slug": ORG_SLUG})
    if org:
        return org
    org_id = await create_organization(
        db, name=ORG_NAME, slug=ORG_SLUG, owner_user_id=owner_user["_id"],
    )
    log.info("created org %s (%s)", ORG_NAME, org_id)
    org = await db.organizations.find_one({"_id": org_id})
    return org


async def run_seed(*, reset: bool = False, minimal: bool = False) -> dict:
    db = get_db()
    await ensure_indexes()

    if reset:
        await _reset_non_canonical(db)

    users = {}
    for u in CANONICAL_USERS:
        doc = await _upsert_user(db, u)
        users[u["email"]] = doc

    # Standalone demo user — created but intentionally left with no membership
    # so they land on the onboarding wizard exactly like a new sign-up.
    demo = await _upsert_user(db, DEMO_USER)
    users[DEMO_USER["email"]] = demo

    owner = users["owner@ubos.test"]
    org = await _ensure_org(db, owner)

    # Make sure all 3 users are members with their canonical roles
    for u in CANONICAL_USERS:
        user_doc = users[u["email"]]
        existing = await db.memberships.find_one({
            "user_id": user_doc["_id"], "org_id": org["_id"], "status": "active",
        })
        if not existing:
            await add_membership(db, user_id=user_doc["_id"],
                                 org_id=org["_id"], role_name=u["role"])
        # Ensure default_org_id points at Acme
        if not user_doc.get("default_org_id"):
            await db.users.update_one(
                {"_id": user_doc["_id"]},
                {"$set": {"default_org_id": org["_id"], "updated_at": _now()}},
            )

    if minimal:
        return {"users": len(users), "org": org["_id"], "template": None}

    # Apply the demo template (idempotent, skips existing)
    tpl_result = None
    try:
        tpl_result = await apply_template(
            db, org_id=org["_id"], key="demo_basic", conflict_policy="skip",
        )
        log.info("applied demo_basic template: %s", tpl_result)
    except Exception as e:  # noqa: BLE001
        log.warning("template apply failed: %s", e)

    return {"users": len(users), "org": org["_id"], "template": tpl_result}


def _cli():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="UBOS seed script")
    ap.add_argument("--reset", action="store_true",
                    help="purge non-canonical data before seeding")
    ap.add_argument("--minimal", action="store_true",
                    help="only seed canonical users + Acme org (no template)")
    args = ap.parse_args()
    result = asyncio.run(run_seed(reset=args.reset, minimal=args.minimal))
    print("seed result:", result)


if __name__ == "__main__":
    _cli()
