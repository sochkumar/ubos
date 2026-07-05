"""FieldValidator — Phase 0 metadata engine.

Validates a record's `fields` dict against a list of field_definitions:
- Required, unique (DB-scoped by org + entity_type), type coercion, config rules
- Returns coerced values and a structured error map keyed by "fields.<key>"
- Also computes `search_text` (denormalised text from human-readable fields)
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from db import tenant_filter

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
PHONE_RE = re.compile(r"^[+\d][\d\s\-().]{4,}$")

# Field types that contribute text to search_text
TEXTUAL_FOR_SEARCH = {
    "text",
    "longtext",
    "richtext",
    "email",
    "phone",
    "url",
    "dropdown",
    "multi_select",
}

# Field types stubbed in Phase 0 — accepted as-is with no validation.
# Sub-pass B activates `image` and `file`; `relation` stays stubbed.
STUB_TYPES = {"relation"}


def _extract_media_ref(v: Any) -> dict | None:
    """Coerce a media reference into a canonical {media_id, ...} dict.
    Accepts: bare id string, {media_id, ...}, {id, ...}. Returns None if empty."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        return {"media_id": v}
    if isinstance(v, dict):
        mid = v.get("media_id") or v.get("id")
        if not isinstance(mid, str) or not mid:
            return None
        d = {"media_id": mid}
        for extra in ("alt", "display_name"):
            if v.get(extra) is not None:
                d[extra] = v[extra]
        return d
    return None


class ValidationErrors(Exception):
    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("Validation failed")


def _coerce_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("must be a number, not a boolean")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as e:
            raise ValueError("must be a valid number") from e
    raise ValueError("must be a valid number")


def _coerce_boolean(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "on"):
            return True
        if v in ("false", "0", "no", "off"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError("must be true or false")


def _coerce_date(value: Any) -> str | None:
    """Return ISO-8601 date string (YYYY-MM-DD)."""
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, str):
        s = value.strip()
        try:
            # accept full ISO datetime or plain date
            if "T" in s or " " in s:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
            return date.fromisoformat(s).isoformat()
        except ValueError as e:
            raise ValueError("must be a valid date (YYYY-MM-DD)") from e
    raise ValueError("must be a valid date")


def _coerce_datetime(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, str):
        s = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError as e:
            raise ValueError("must be a valid ISO datetime") from e
    raise ValueError("must be a valid ISO datetime")


class FieldValidator:
    def __init__(self, db: AsyncIOMotorDatabase, org_id: str, entity_type_id: str):
        self.db = db
        self.org_id = org_id
        self.entity_type_id = entity_type_id

    # ------------------------------------------------------------------ per-field
    def _validate_value(self, fdef: dict, raw: Any) -> Any:
        ftype: str = fdef["type"]
        cfg: dict = fdef.get("config") or {}
        empty = raw is None or raw == "" or (isinstance(raw, list) and len(raw) == 0)

        if empty:
            return None

        if ftype in ("text", "longtext", "richtext"):
            if not isinstance(raw, str):
                raise ValueError("must be a string")
            v = raw
            max_len = cfg.get("max_length")
            if max_len and len(v) > int(max_len):
                raise ValueError(f"must be at most {max_len} characters")
            pattern = cfg.get("pattern")
            if pattern:
                if not re.match(pattern, v):
                    raise ValueError("does not match required pattern")
            return v

        if ftype in ("number", "currency"):
            v = _coerce_number(raw)
            if v is None:
                return None
            if "min" in cfg and v < float(cfg["min"]):
                raise ValueError(f"must be at least {cfg['min']}")
            if "max" in cfg and v > float(cfg["max"]):
                raise ValueError(f"must be at most {cfg['max']}")
            return v

        if ftype == "boolean":
            return _coerce_boolean(raw)

        if ftype == "date":
            return _coerce_date(raw)

        if ftype == "datetime":
            return _coerce_datetime(raw)

        if ftype == "email":
            if not isinstance(raw, str) or not EMAIL_RE.match(raw.strip()):
                raise ValueError("must be a valid email address")
            return raw.strip()

        if ftype == "url":
            if not isinstance(raw, str) or not URL_RE.match(raw.strip()):
                raise ValueError("must be a valid http(s) URL")
            return raw.strip()

        if ftype == "phone":
            if not isinstance(raw, str) or not PHONE_RE.match(raw.strip()):
                raise ValueError("must be a valid phone number")
            return raw.strip()

        if ftype == "dropdown":
            options = [o["value"] if isinstance(o, dict) else o for o in cfg.get("options", [])]
            if options and raw not in options:
                raise ValueError(f"must be one of: {', '.join(map(str, options))}")
            return raw

        if ftype == "multi_select":
            if not isinstance(raw, list):
                raise ValueError("must be a list of values")
            options = [o["value"] if isinstance(o, dict) else o for o in cfg.get("options", [])]
            if options:
                bad = [x for x in raw if x not in options]
                if bad:
                    raise ValueError(f"invalid options: {', '.join(map(str, bad))}")
            return raw

        if ftype == "image":
            multiple = bool((cfg or {}).get("multiple"))
            if multiple:
                if not isinstance(raw, list):
                    raise ValueError("must be a list of images")
                refs = [_extract_media_ref(v) for v in raw]
                refs = [r for r in refs if r is not None]
                max_count = cfg.get("max_count")
                if max_count and len(refs) > int(max_count):
                    raise ValueError(f"at most {max_count} image(s) allowed")
                return refs
            r = _extract_media_ref(raw if not isinstance(raw, list) else (raw[0] if raw else None))
            return r  # may be None if empty

        if ftype == "file":
            multiple = bool((cfg or {}).get("multiple"))
            if multiple:
                if not isinstance(raw, list):
                    raise ValueError("must be a list of files")
                refs = [_extract_media_ref(v) for v in raw]
                refs = [r for r in refs if r is not None]
                max_count = cfg.get("max_count")
                if max_count and len(refs) > int(max_count):
                    raise ValueError(f"at most {max_count} file(s) allowed")
                return refs
            r = _extract_media_ref(raw if not isinstance(raw, list) else (raw[0] if raw else None))
            return r

        if ftype in STUB_TYPES:
            # accepted as-is (Phase 0 stubs still in force for `relation`)
            return raw

        raise ValueError(f"unsupported field type: {ftype}")

    # ------------------------------------------------------------------ main
    async def validate(
        self,
        field_defs: list[dict],
        payload_fields: dict[str, Any],
        exclude_record_id: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Validate a payload dict against the given field defs.

        Returns (coerced_fields, search_text).
        Raises ValidationErrors with a map of field_path → message on failure.
        """
        errors: dict[str, str] = {}
        coerced: dict[str, Any] = {}
        search_parts: list[str] = []

        defs_by_key = {fd["key"]: fd for fd in field_defs}

        # Reject unknown keys — safer than silently dropping them
        for key in payload_fields.keys():
            if key not in defs_by_key:
                errors[f"fields.{key}"] = "unknown field"

        for fd in field_defs:
            key = fd["key"]
            raw = payload_fields.get(key)
            try:
                value = self._validate_value(fd, raw)
            except ValueError as e:
                errors[f"fields.{key}"] = str(e)
                continue

            if fd.get("required") and (value is None or value == ""):
                errors[f"fields.{key}"] = "is required"
                continue

            coerced[key] = value

            if value is not None and fd["type"] in TEXTUAL_FOR_SEARCH:
                if isinstance(value, list):
                    search_parts.extend(str(v) for v in value)
                else:
                    search_parts.append(str(value))

        # Unique enforcement (DB check, one query per unique field)
        for fd in field_defs:
            if not fd.get("unique"):
                continue
            key = fd["key"]
            if f"fields.{key}" in errors:
                continue
            value = coerced.get(key)
            if value is None or value == "":
                continue
            q = tenant_filter(
                self.org_id,
                {"entity_type_id": self.entity_type_id, f"fields.{key}": value},
            )
            if exclude_record_id:
                q["_id"] = {"$ne": exclude_record_id}
            existing = await self.db.records.find_one(q, {"_id": 1})
            if existing:
                errors[f"fields.{key}"] = "must be unique — value already exists"

        # image/file: verify referenced media exists in this org + optional
        # mime + max_size constraints. Batch one query per (org).
        media_targets: dict[str, tuple[str, dict]] = {}  # media_id -> (field_key, fdef)
        for fd in field_defs:
            if fd["type"] not in ("image", "file"):
                continue
            key = fd["key"]
            v = coerced.get(key)
            if v is None:
                continue
            refs = v if isinstance(v, list) else [v]
            for r in refs:
                if isinstance(r, dict) and r.get("media_id"):
                    media_targets[r["media_id"]] = (key, fd)
        if media_targets:
            docs = {
                m["_id"]: m
                async for m in self.db.media.find(
                    {"_id": {"$in": list(media_targets.keys())},
                     "org_id": self.org_id, "deleted_at": None},
                    {"mime": 1, "size": 1, "filename": 1},
                )
            }
            for mid, (fkey, fd) in media_targets.items():
                m = docs.get(mid)
                if not m:
                    errors[f"fields.{fkey}"] = f"media '{mid}' does not exist in this workspace"
                    continue
                cfg = fd.get("config") or {}
                if fd["type"] == "image" and not (m.get("mime") or "").startswith("image/"):
                    errors[f"fields.{fkey}"] = f"'{m.get('filename')}' is not an image"
                    continue
                if fd["type"] == "file":
                    allowed = cfg.get("allowed_mimes")
                    if allowed and m.get("mime") not in allowed:
                        errors[f"fields.{fkey}"] = f"'{m.get('mime')}' is not in this field's allowed mimes"
                        continue
                max_mb = cfg.get("max_size_mb")
                if max_mb and int(m.get("size", 0)) > int(max_mb) * 1024 * 1024:
                    errors[f"fields.{fkey}"] = f"'{m.get('filename')}' exceeds max size of {max_mb} MB"

        if errors:
            raise ValidationErrors(errors)

        return coerced, " ".join(search_parts)
