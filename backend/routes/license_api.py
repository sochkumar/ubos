"""License status/activation endpoints (desktop build).

Unauthenticated on purpose: the user must be able to see the machine id and load
a license *before* they can log in. In cloud mode (UBOS_DESKTOP unset) the app is
always "licensed" and /load is disabled.
"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import licensing

router = APIRouter(prefix="/license", tags=["license"])


def is_desktop() -> bool:
    return os.environ.get("UBOS_DESKTOP", "").lower() in ("1", "true", "yes", "on")


def _license_path() -> str:
    return os.environ.get("UBOS_LICENSE_PATH", "")


def status() -> dict:
    mid = licensing.machine_id()
    if not is_desktop():
        return {"desktop": False, "licensed": True, "machine_id": mid, "reason": "cloud mode"}
    path = _license_path()
    if not path or not os.path.exists(path):
        return {"desktop": True, "licensed": False, "machine_id": mid, "reason": "no license loaded"}
    ok, payload, reason = licensing.verify_license_file(path, mid)
    return {
        "desktop": True, "licensed": ok, "machine_id": mid, "reason": reason,
        "licensee": (payload or {}).get("licensee") if ok else None,
    }


@router.get("/status")
async def license_status():
    return status()


class LoadBody(BaseModel):
    license: str


@router.post("/load")
async def license_load(body: LoadBody):
    if not is_desktop():
        raise HTTPException(404, "licensing is only used in the desktop build")
    mid = licensing.machine_id()
    ok, _payload, reason = licensing.verify_license(body.license, mid)
    if not ok:
        raise HTTPException(400, {"code": "invalid_license", "detail": reason, "machine_id": mid})
    path = _license_path()
    if not path:
        raise HTTPException(500, "UBOS_LICENSE_PATH is not configured")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(body.license.strip() + "\n")
    return status()
