"""One-shot cleanup helper: fully wipe Acme Furniture's phase 2 data.
Run: python -m backend.tests._reset_acme
"""
import asyncio, os, sys
sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import dotenv_values

env = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or env["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME") or env["DB_NAME"]


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    org = await db.orgs.find_one({"name": "Acme Furniture"})
    if not org:
        print("no Acme org")
        return
    oid = org["_id"]
    for coll in ("entity_types", "field_definitions", "records", "categories",
                 "tags", "relationship_definitions"):
        r = await db[coll].delete_many({"org_id": oid})
        print(f"{coll}: deleted {r.deleted_count}")
    print("done")

asyncio.run(main())
