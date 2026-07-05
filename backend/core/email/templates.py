"""Simple inline-styled HTML + text templates for auth/invite emails."""
from __future__ import annotations

_BASE_CSS = (
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
    "line-height:1.5;color:#111;max-width:520px;margin:0 auto;padding:32px 16px;"
)
_BTN_CSS = (
    "display:inline-block;padding:10px 20px;border-radius:6px;"
    "background:#0f766e;color:#fff !important;text-decoration:none;"
    "font-weight:600;font-size:14px;margin:20px 0;"
)


def _btn(url: str, label: str) -> str:
    return f'<a href="{url}" style="{_BTN_CSS}">{label}</a>'


def _wrap(body_html: str) -> str:
    return (
        f'<div style="{_BASE_CSS}">'
        f'<div style="font-size:20px;font-weight:700;color:#0f766e;margin-bottom:24px;">UBOS</div>'
        f"{body_html}"
        f'<hr style="border:0;border-top:1px solid #eee;margin:32px 0 16px;"/>'
        '<div style="font-size:11px;color:#888;">'
        'You received this email because someone (probably you) took an action on UBOS. '
        'If it wasn\'t you, you can safely ignore this message.'
        "</div>"
        "</div>"
    )


def invitation_email(
    *, org_name: str, role_name: str, inviter_name: str,
    invitee_email: str, accept_url: str, expires_at_readable: str,
) -> tuple[str, str, str]:
    """Return (subject, html, text)."""
    subject = f"You've been invited to {org_name} on UBOS"
    body = (
        f"<p>Hi,</p>"
        f"<p><strong>{_esc(inviter_name)}</strong> invited you to join "
        f"<strong>{_esc(org_name)}</strong> on UBOS as an <em>{_esc(role_name)}</em>.</p>"
        f"<p>Click the button below to accept the invitation. This link expires on "
        f"<strong>{_esc(expires_at_readable)}</strong>.</p>"
        f'<p style="text-align:center;">{_btn(accept_url, "Accept invitation")}</p>'
        f'<p style="font-size:12px;color:#666;">'
        f"Or copy and paste this URL into your browser:<br/>"
        f'<a href="{accept_url}" style="color:#0f766e;word-break:break-all;">{accept_url}</a>'
        f"</p>"
    )
    text = (
        f"You've been invited to {org_name} on UBOS\n\n"
        f"{inviter_name} invited you to join {org_name} as {role_name}.\n"
        f"Accept: {accept_url}\n"
        f"Expires: {expires_at_readable}\n"
    )
    return subject, _wrap(body), text


def password_reset_email(*, reset_url: str, expires_hours: int = 1) -> tuple[str, str, str]:
    subject = "Reset your UBOS password"
    body = (
        f"<p>Hi,</p>"
        f"<p>We received a request to reset your UBOS password. Click the button below "
        f"to choose a new password. This link expires in {expires_hours} hour(s).</p>"
        f'<p style="text-align:center;">{_btn(reset_url, "Reset password")}</p>'
        f'<p style="font-size:12px;color:#666;">'
        f"Or copy and paste this URL into your browser:<br/>"
        f'<a href="{reset_url}" style="color:#0f766e;word-break:break-all;">{reset_url}</a>'
        f"</p>"
        f"<p>If you didn't request this, you can safely ignore this email.</p>"
    )
    text = (
        f"Reset your UBOS password\n\n"
        f"Follow the link to set a new password: {reset_url}\n"
        f"Expires in {expires_hours} hour(s).\n"
    )
    return subject, _wrap(body), text


def _esc(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
