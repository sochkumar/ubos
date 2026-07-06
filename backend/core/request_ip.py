"""Client-IP helper honouring reverse proxy headers (Phase 6-B).

Behind Kubernetes ingress + Cloudflare, `request.client.host` is the upstream
proxy IP — not the actual end user. Multiple users hit the same bucket and
lockouts turn into false positives.

We only trust the leftmost `TRUST_PROXY_HOPS` entries of `X-Forwarded-For` (env
default = 1 for this preview infra). Never trust `X-Real-IP` for security
decisions — Cloudflare can be configured to strip it but many stacks pass it
through untouched.
"""
from __future__ import annotations

import os

from fastapi import Request


def _trust_hops() -> int:
    raw = os.environ.get("TRUST_PROXY_HOPS", "1")
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def get_client_ip(request: Request | None) -> str:
    """Return the best-effort client IP given optional proxy trust."""
    if not request:
        return "unknown"
    hops = _trust_hops()
    if hops > 0:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            parts = [p.strip() for p in xff.split(",") if p.strip()]
            if parts:
                # XFF grows left→right as client, proxy1, proxy2, … . We trust the
                # rightmost `hops` entries as our infrastructure and take the
                # entry just before them as the real client. If the chain is
                # shorter than trusted hops (e.g. direct clients bypassing a
                # proxy on the way in), fall back to the leftmost entry.
                idx = max(0, len(parts) - hops - 1)
                candidate = parts[idx]
                if candidate:
                    return candidate
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
