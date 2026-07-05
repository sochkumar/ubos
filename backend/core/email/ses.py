"""AWS SES email provider."""
from __future__ import annotations

import logging
import uuid

from .base import EmailProvider, EmailSendResult
from .dev import DevEmailProvider

log = logging.getLogger("ubos.email.ses")


class SESProvider(EmailProvider):
    name = "ses"

    def __init__(self, region: str, from_addr: str, from_name: str | None = None):
        self.region = region
        self.from_addr = from_addr
        self.from_name = from_name

    async def send(
        self, *, to: str, subject: str, html: str, text: str,
        reply_to: str | None = None, headers: dict | None = None,
    ) -> EmailSendResult:
        try:
            import boto3  # type: ignore
        except Exception as e:
            log.warning("boto3 not available (%s) — falling back to dev provider", e)
            return await DevEmailProvider().send(
                to=to, subject=subject, html=html, text=text,
                reply_to=reply_to, headers=headers,
            )
        try:
            client = boto3.client("ses", region_name=self.region)
            source = f"{self.from_name} <{self.from_addr}>" if self.from_name else self.from_addr
            kwargs = dict(
                Source=source,
                Destination={"ToAddresses": [to]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {
                        "Text": {"Data": text},
                        "Html": {"Data": html},
                    },
                },
            )
            if reply_to:
                kwargs["ReplyToAddresses"] = [reply_to]
            import asyncio
            resp = await asyncio.get_event_loop().run_in_executor(
                None, lambda: client.send_email(**kwargs)
            )
            mid = resp.get("MessageId") or f"ses-{uuid.uuid4()}"
            return EmailSendResult(
                provider=self.name, message_id=mid, sent_at=self._now(),
            )
        except Exception as e:
            log.warning("ses send failed: %s", e)
            return EmailSendResult(
                provider=self.name, message_id="", sent_at=self._now(),
                ok=False, error=str(e),
            )
