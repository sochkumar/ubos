"""Resend email provider (uses `resend` SDK)."""
from __future__ import annotations

import logging
import os
import uuid

from .base import EmailProvider, EmailSendResult
from .dev import DevEmailProvider

log = logging.getLogger("ubos.email.resend")


class ResendProvider(EmailProvider):
    name = "resend"

    def __init__(self, api_key: str, from_addr: str, from_name: str | None = None):
        self.api_key = api_key
        self.from_addr = from_addr
        self.from_name = from_name

    async def send(
        self, *, to: str, subject: str, html: str, text: str,
        reply_to: str | None = None, headers: dict | None = None,
    ) -> EmailSendResult:
        try:
            import resend  # type: ignore
        except Exception as e:
            log.warning("resend SDK not available (%s) — falling back to dev provider", e)
            return await DevEmailProvider().send(
                to=to, subject=subject, html=html, text=text,
                reply_to=reply_to, headers=headers,
            )
        resend.api_key = self.api_key
        params = {
            "from": (f"{self.from_name} <{self.from_addr}>" if self.from_name else self.from_addr),
            "to": [to],
            "subject": subject,
            "html": html,
            "text": text,
        }
        if reply_to:
            params["reply_to"] = reply_to
        if headers:
            params["headers"] = headers
        try:
            # resend SDK is synchronous; run in default loop executor
            import asyncio
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: resend.Emails.send(params)
            )
            mid = resp.get("id") if isinstance(resp, dict) else str(resp)
            return EmailSendResult(
                provider=self.name,
                message_id=mid or f"resend-{uuid.uuid4()}",
                sent_at=self._now(),
            )
        except Exception as e:
            log.warning("resend send failed: %s", e)
            return EmailSendResult(
                provider=self.name, message_id="", sent_at=self._now(),
                ok=False, error=str(e),
            )
