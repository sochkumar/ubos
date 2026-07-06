"""Client-IP helper honouring reverse proxy headers (Phase 6-B, hardened).

We run behind Cloudflare + Kubernetes ingress in production. Naive readings of
`request.client.host` return a rotating infrastructure IP; naive `right-index`
readings of `X-Forwarded-For` are similarly fooled because ingress prepends
its own hop and the caller's XFF value gets pushed off the trusted slice.

Resolution order (first hit wins):

1. **`CF-Connecting-IP`** — Cloudflare *overwrites* any client-supplied value
   on ingress, so it's tamper-proof through their network. Present iff the
   request actually traversed Cloudflare. Prefer this whenever it exists.
2. **Leftmost `X-Forwarded-For`** (gated by `TRUST_LEFTMOST_XFF`, default `true`).
   The leftmost entry is the original client per the XFF spec. Any hop the
   client injected is still recorded to the left of anything ingress adds,
   which is what we want behind a *trusted* front door (Cloudflare, ELB, etc).
   If your deployment is NOT behind a trusted front door, set
   `TRUST_LEFTMOST_XFF=false` to fall back to the legacy right-index behaviour
   controlled by `TRUST_PROXY_HOPS`.
3. **`TRUST_PROXY_HOPS` right-index** — legacy behaviour retained for backward
   compat. Only used when `TRUST_LEFTMOST_XFF=false` and `CF-Connecting-IP`
   is absent.
4. **`request.client.host`** — direct-connect fallback.
5. **`"unknown"`** — never `None`, always a stable string for bucketing.

Note: `X-Real-IP` is intentionally not consulted. Many stacks pass it through
untouched from the client; trusting it opens a rate-limit bypass.
"""
from __future__ import annotations

import ipaddress
import os

from fastapi import Request


def _trust_hops() -> int:
    raw = os.environ.get("TRUST_PROXY_HOPS", "1")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _trust_leftmost_xff() -> bool:
    raw = (os.environ.get("TRUST_LEFTMOST_XFF") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _is_valid_ip(candidate: str) -> bool:
    """Accept IPv4 / IPv6 addresses (bare, no port). Reject blanks & garbage."""
    if not candidate:
        return False
    try:
        ipaddress.ip_address(candidate)
        return True
    except ValueError:
        return False


def get_client_ip(request: Request | None) -> str:
    """Return the best-effort client IP given optional proxy trust."""
    if not request:
        return "unknown"

    # 1) Cloudflare — tamper-proof through their network.
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        cf = cf.strip()
        if _is_valid_ip(cf):
            return cf

    xff = request.headers.get("x-forwarded-for")
    parts: list[str] = []
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]

    # 2) Leftmost XFF (default behind Cloudflare / trusted front doors).
    if parts and _trust_leftmost_xff():
        candidate = parts[0]
        if _is_valid_ip(candidate):
            return candidate

    # 3) Legacy right-index XFF (only when TRUST_LEFTMOST_XFF=false).
    if parts and not _trust_leftmost_xff():
        hops = _trust_hops()
        if hops > 0:
            idx = max(0, len(parts) - hops - 1)
            candidate = parts[idx]
            if _is_valid_ip(candidate):
                return candidate

    # 4) Direct-connect fallback.
    if request.client and request.client.host:
        return request.client.host

    return "unknown"
