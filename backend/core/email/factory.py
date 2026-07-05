"""Factory: picks provider based on env keys in priority order."""
from __future__ import annotations

import os
from functools import lru_cache

from .base import EmailProvider
from .dev import DevEmailProvider
from .resend import ResendProvider
from .sendgrid import SendGridProvider
from .ses import SESProvider


def _from_addr() -> str:
    return os.environ.get("EMAIL_FROM", "noreply@ubos.local")


def _from_name() -> str | None:
    return os.environ.get("EMAIL_FROM_NAME") or None


@lru_cache(maxsize=1)
def get_email_provider() -> EmailProvider:
    resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    if resend_key:
        return ResendProvider(api_key=resend_key, from_addr=_from_addr(), from_name=_from_name())
    sg_key = os.environ.get("SENDGRID_API_KEY", "").strip()
    if sg_key:
        return SendGridProvider(api_key=sg_key, from_addr=_from_addr(), from_name=_from_name())
    ses_region = os.environ.get("AWS_SES_REGION", "").strip()
    if ses_region:
        return SESProvider(region=ses_region, from_addr=_from_addr(), from_name=_from_name())
    return DevEmailProvider()


def reset_provider_cache() -> None:  # test helper
    get_email_provider.cache_clear()
