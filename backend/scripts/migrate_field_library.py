"""Phase-1 migration: build the org-level reusable field library.

Idempotent + additive (safe to re-run, destroys nothing):
  1. Group existing per-catalogue `field_definitions` by (org_id, key).
  2. Create one `field_library` entry per key (if absent).
  3. Link every field_definition to its library entry via `library_id`.

Existing record data (keyed by field `key`) is untouched. Old field_definitions
remain in place — this only adds a `field_library` collection and a `library_id`
column, so the change is fully reversible.

Run:  cd backend && ./venv/bin/python -m scripts.migrate_field_library
"""
from __future__ import annotations

import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    db = MongoClient(MONGO_URL)[DB_NAME]
    fds = list(db.field_definitions.find({"deleted_at": None}))
    print(f"Scanning {len(fds)} active field_definitions in {DB_NAME}…")

    # group by (org_id, key)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for fd in fds:
        groups[(fd["org_id"], fd["key"])].append(fd)

    libs_created = 0
    libs_reused = 0
    linked = 0
    conflicts = 0

    for (org_id, key), group in groups.items():
        # conflict detection: same key, differing base type across catalogues
        types = {g.get("type") for g in group}
        if len(types) > 1:
            conflicts += 1
            print(f"  ⚠ conflict org={org_id[:8]} key={key!r}: types={types} — using most common")

        # canonical source = the definition with the richest config/help_text
        canonical = sorted(
            group,
            key=lambda g: (len(g.get("config") or {}), bool(g.get("help_text"))),
            reverse=True,
        )[0]

        lib = db.field_library.find_one({"org_id": org_id, "key": key, "deleted_at": None})
        if lib:
            lib_id = lib["_id"]
            libs_reused += 1
        else:
            lib_id = str(uuid.uuid4())
            db.field_library.insert_one({
                "_id": lib_id,
                "org_id": org_id,
                "key": key,
                "label": canonical.get("label") or key,
                "type": canonical.get("type") or "text",
                "config": canonical.get("config") or {},
                "unit": canonical.get("unit"),
                "help_text": canonical.get("help_text"),
                "created_at": now(),
                "updated_at": now(),
                "deleted_at": None,
            })
            libs_created += 1

        res = db.field_definitions.update_many(
            {
                "org_id": org_id, "key": key, "deleted_at": None,
                "$or": [{"library_id": None}, {"library_id": {"$exists": False}}],
            },
            {"$set": {"library_id": lib_id, "updated_at": now()}},
        )
        linked += res.modified_count

    print("\n── Migration summary ──")
    print(f"  library fields created : {libs_created}")
    print(f"  library fields reused  : {libs_reused}")
    print(f"  field_definitions linked: {linked}")
    print(f"  key conflicts (logged) : {conflicts}")
    total_lib = db.field_library.count_documents({"deleted_at": None})
    unlinked = db.field_definitions.count_documents(
        {"deleted_at": None, "$or": [{"library_id": None}, {"library_id": {"$exists": False}}]}
    )
    print(f"  total library fields   : {total_lib}")
    print(f"  remaining unlinked defs: {unlinked}")


if __name__ == "__main__":
    main()
