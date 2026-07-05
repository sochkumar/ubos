"""Pluggable Email provider ABC."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class EmailSendResult:
    provider: str
    message_id: str
    sent_at: str
    ok: bool = True
    error: str | None = None


class EmailProvider(ABC):
    """All concrete providers implement `send(...)`. Providers that lack the
    required SDK / credentials should degrade to a dev-mode result rather than
    raising, so callers don't have to guard every call site."""

    name: str = "base"

    @abstractmethod
    async def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
        reply_to: str | None = None,
        headers: dict | None = None,
    ) -> EmailSendResult:
        ...

    def _now(self) -> str:
        from datetime import timezone
        return datetime.now(timezone.utc).isoformat()
