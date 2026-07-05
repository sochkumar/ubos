"""SendGrid email provider."""
from __future__ import annotations

import logging
import uuid

from .base import EmailProvider, EmailSendResult
from .dev import DevEmailProvider

log = logging.getLogger("ubos.email.sendgrid")


class SendGridProvider(EmailProvider):
    name = "sendgrid"

    def __init__(self, api_key: str, from_addr: str, from_name: str | None = None):
        self.api_key = api_key
        self.from_addr = from_addr
        self.from_name = from_name

    async def send(
        self, *, to: str, subject: str, html: str, text: str,
        reply_to: str | None = None, headers: dict | None = None,
    ) -> EmailSendResult:
        try:
            from sendgrid import SendGridAPIClient  # type: ignore
            from sendgrid.helpers.mail import Mail, Email, To, Content  # type: ignore
        except Exception as e:
            log.warning("sendgrid SDK not available (%s) — falling back to dev provider", e)
            return await DevEmailProvider().send(
                to=to, subject=subject, html=html, text=text,
                reply_to=reply_to, headers=headers,
            )
        try:
            msg = Mail(
                from_email=Email(self.from_addr, self.from_name),
                to_emails=To(to),
                subject=subject,
                plain_text_content=Content("text/plain", text),
                html_content=Content("text/html", html),
            )
            if reply_to:
                msg.reply_to = Email(reply_to)
            client = SendGridAPIClient(self.api_key)
            import asyncio
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.send(msg)
            )
            mid = resp.headers.get("X-Message-Id") or f"sendgrid-{uuid.uuid4()}"
            return EmailSendResult(
                provider=self.name, message_id=mid, sent_at=self._now(),
            )
        except Exception as e:
            log.warning("sendgrid send failed: %s", e)
            return EmailSendResult(
                provider=self.name, message_id="", sent_at=self._now(),
                ok=False, error=str(e),
            )
