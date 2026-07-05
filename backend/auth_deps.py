"""FastAPI dependencies for authentication + tenant context + RBAC."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, Header, HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param

from db import get_db
from security import decode_token, permissions_for_role


@dataclass
class AuthContext:
    user: dict
    org_id: str | None
    role: str | None
    permissions: list[str] = field(default_factory=list)

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise HTTPException(status_code=403, detail=f"missing permission: {permission}")


async def get_current_user(request: Request) -> dict:
    """Decode the Bearer JWT and load the user document."""
    auth = request.headers.get("Authorization", "")
    scheme, token = get_authorization_scheme_param(auth)
    if not token or scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="invalid token type")

    db = get_db()
    user = await db.users.find_one({"_id": payload["sub"], "is_active": True})
    if not user:
        raise HTTPException(status_code=401, detail="user not found or disabled")
    # attach the payload for downstream deps
    request.state.jwt_payload = payload
    return user


async def get_current_context(
    request: Request,
    user: dict = Depends(get_current_user),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
) -> AuthContext:
    """Compose the full auth context: user + active org + role + permissions.

    - Base org comes from the JWT (`org_id`) or user's default_org_id.
    - `X-Org-Id` header can override, but ONLY if the user is a member of that org
      (documented as an API-scripting escape hatch).
    """
    payload = getattr(request.state, "jwt_payload", {})
    org_id = payload.get("org_id") or user.get("default_org_id")

    if x_org_id and x_org_id != org_id:
        db = get_db()
        m = await db.memberships.find_one(
            {"user_id": user["_id"], "org_id": x_org_id, "status": "active"}
        )
        if not m:
            raise HTTPException(status_code=403, detail="not a member of requested org")
        org_id = x_org_id
        # role/perms must be re-derived from THIS org's membership
        role_doc = await db.roles.find_one({"_id": m["role_id"]})
        role_name = role_doc["name"] if role_doc else None
        permissions = permissions_for_role(role_name or "viewer")
    else:
        role_name = payload.get("role")
        permissions = list(payload.get("permissions") or [])
        # If token predates a role change we still trust the token until refresh —
        # a simple, well-understood model.

    return AuthContext(user=user, org_id=org_id, role=role_name, permissions=permissions)


def require_permission(permission: str):
    """FastAPI dependency factory — enforce a specific RBAC permission."""

    async def _dep(ctx: AuthContext = Depends(get_current_context)) -> AuthContext:
        if not ctx.org_id:
            raise HTTPException(status_code=400, detail="no active organization")
        ctx.require(permission)
        return ctx

    return _dep


def require_org() -> Any:
    """Dependency: current context with an org_id (any role)."""

    async def _dep(ctx: AuthContext = Depends(get_current_context)) -> AuthContext:
        if not ctx.org_id:
            raise HTTPException(status_code=400, detail="no active organization")
        return ctx

    return _dep


async def try_auth(
    request: Request,
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
) -> AuthContext | None:
    """Optional auth dependency — never raises. Returns AuthContext or None.

    Public endpoints use this to unlock `org_only` visibility when the caller
    is signed in as a member of the owning org."""
    auth = request.headers.get("Authorization", "")
    scheme, token = get_authorization_scheme_param(auth)
    if not token or scheme.lower() != "bearer":
        return None
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    if payload.get("type") != "access":
        return None
    db = get_db()
    user = await db.users.find_one({"_id": payload["sub"], "is_active": True})
    if not user:
        return None
    request.state.jwt_payload = payload
    org_id = payload.get("org_id") or user.get("default_org_id")
    if x_org_id and x_org_id != org_id:
        m = await db.memberships.find_one(
            {"user_id": user["_id"], "org_id": x_org_id, "status": "active"}
        )
        if not m:
            # header points at an org the user is not part of → treat as anon
            return None
        org_id = x_org_id
        role_doc = await db.roles.find_one({"_id": m["role_id"]})
        role_name = role_doc["name"] if role_doc else None
        permissions = permissions_for_role(role_name or "viewer")
    else:
        role_name = payload.get("role")
        permissions = list(payload.get("permissions") or [])
    return AuthContext(user=user, org_id=org_id, role=role_name, permissions=permissions)
