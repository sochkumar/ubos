"""Email provider abstraction (Phase 5-B).

Providers: dev (logs), resend, sendgrid, ses. Picked by env vars.
Same abstraction is used by invitations + password-reset flows.
"""
from .factory import get_email_provider  # noqa: F401
from .base import EmailProvider, EmailSendResult  # noqa: F401
