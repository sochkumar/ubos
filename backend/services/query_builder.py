"""Safe filter → Mongo query translator. Whitelisted ops per field type."""
from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

# Ops allowed per field type. Types not listed fall back to 'text' behaviour.
OPS_BY_TYPE = {
    "text": {"eq","ne","contains","in","not_in","is_empty","is_not_empty"},
    "longtext": {"eq","ne","contains","is_empty","is_not_empty"},
    "richtext": {"contains","is_empty","is_not_empty"},
    "number": {"eq","ne","gt","lt","gte","lte","between","in","not_in","is_empty","is_not_empty"},
    "currency": {"eq","ne","gt","lt","gte","lte","between","is_empty","is_not_empty"},
    "date": {"eq","ne","gt","lt","gte","lte","between","is_empty","is_not_empty"},
    "datetime": {"eq","ne","gt","lt","gte","lte","between","is_empty","is_not_empty"},
    "boolean": {"eq","ne"},
    "dropdown": {"eq","ne","in","not_in","is_empty","is_not_empty"},
    "multi_select": {"in","not_in","is_empty","is_not_empty"},
    "email": {"eq","ne","contains","is_empty","is_not_empty"},
    "phone": {"eq","ne","contains","is_empty","is_not_empty"},
    "url": {"eq","ne","contains","is_empty","is_not_empty"},
}


def _mongo_field(field_key: str) -> str:
    # All dynamic fields live under `fields.<key>`; system fields addressed by exact keys.
    system = {"title","description","record_number","created_at","updated_at","version"}
    if field_key in system:
        return field_key
    return f"fields.{field_key}"


def _op_to_mongo(op: str, value: Any) -> dict | Any:
    if op == "eq": return value
    if op == "ne": return {"$ne": value}
    if op == "contains":
        if not isinstance(value, str):
            raise HTTPException(422, "'contains' requires a string value")
        return {"$regex": re.escape(value), "$options": "i"}
    if op == "gt": return {"$gt": value}
    if op == "lt": return {"$lt": value}
    if op == "gte": return {"$gte": value}
    if op == "lte": return {"$lte": value}
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise HTTPException(422, "'between' requires a 2-element [lo, hi] list")
        return {"$gte": value[0], "$lte": value[1]}
    if op == "in":
        if not isinstance(value, list):
            raise HTTPException(422, "'in' requires a list")
        return {"$in": value}
    if op == "not_in":
        if not isinstance(value, list):
            raise HTTPException(422, "'not_in' requires a list")
        return {"$nin": value}
    if op == "is_empty":
        return {"$in": [None, "", []]}
    if op == "is_not_empty":
        return {"$nin": [None, "", []]}
    raise HTTPException(422, f"unsupported op '{op}'")


def build_filter_query(
    conditions: list[dict],
    field_defs_by_key: dict[str, dict],
) -> dict:
    """Return a Mongo query fragment. Merged with tenant_filter at the callsite."""
    if not conditions:
        return {}
    parts: list[dict] = []
    for c in conditions:
        key = c.get("field")
        op = c.get("op")
        value = c.get("value")
        if not key or not op:
            raise HTTPException(422, "each filter needs field + op")
        fdef = field_defs_by_key.get(key)
        ftype = fdef["type"] if fdef else "text"
        allowed = OPS_BY_TYPE.get(ftype, OPS_BY_TYPE["text"])
        if op not in allowed:
            raise HTTPException(422, f"op '{op}' not valid for type '{ftype}'")
        parts.append({_mongo_field(key): _op_to_mongo(op, value)})
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}


def build_sort_spec(sort: list[dict]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for s in sort or []:
        f = s.get("field")
        if not f:
            continue
        d = 1 if s.get("dir", "asc") == "asc" else -1
        out.append((_mongo_field(f), d))
    return out or [("created_at", -1)]
