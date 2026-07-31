"""Deployment feature flags (env-driven).

The desktop build for a single-vertical customer sets UBOS_SINGLE_BUSINESS=true.
That tailors the app to one business: global fields (every catalogue shows all
fields), no industry starter packs / demo data, one workspace, and a furnishing
first-run seed. The cloud/universal product never sets it, so it stays generic.
"""
from __future__ import annotations

import os

_TRUE = ("1", "true", "yes", "on")


def single_business() -> bool:
    return os.environ.get("UBOS_SINGLE_BUSINESS", "").lower() in _TRUE


def global_fields() -> bool:
    # single-business implies global fields; also independently togglable.
    return single_business() or os.environ.get("UBOS_GLOBAL_FIELDS", "").lower() in _TRUE


def as_dict() -> dict:
    return {"single_business": single_business(), "global_fields": global_fields()}
