"""Dev email provider — logs to stdout + /app/backend/dev_emails.log."""
from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path

from .base import EmailProvider, EmailSendResult

log = logging.getLogger("ubos.email.dev")

_LOG_FILE = Path(os.environ.get("DEV_EMAIL_LOG", "/app/backend/dev_emails.log"))


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:64] or "mail"


class DevEmailProvider(EmailProvider):
    name = "dev"

    async def send(
        self, *, to: str, subject: str, html: str, text: str,
        reply_to: str | None = None, headers: dict | None = None,
    ) -> EmailSendResult:
        mid = f"dev-{uuid.uuid4()}"
        ts = self._now()
        line = (
            f"\n────── [dev-email] {ts} ──────\n"
            f"To: {to}\n"
            f"Subject: {subject}\n"
            f"Reply-To: {reply_to or '-'}\n"
            f"Message-Id: {mid}\n"
            f"──── text ────\n{text}\n"
            f"──── /text ────\n"
        )
        log.warning(line)
        try:
            _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:  # pragma: no cover
            log.warning("could not write dev email log: %s", e)
        return EmailSendResult(provider=self.name, message_id=mid, sent_at=ts)
