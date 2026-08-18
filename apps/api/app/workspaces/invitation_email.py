"""Invitation email copy (plain text + HTML). User-controlled fields are escaped in HTML."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from xml.sax.saxutils import quoteattr

_ROLE_EN = {"owner": "Owner", "admin": "Admin", "member": "Member"}
_ROLE_AR = {"owner": "مالك", "admin": "مشرف", "member": "عضو"}

BRAND = "#0e2f44"
BRAND_ACCENT = "#367d9e"

# Public brand mark (source of truth for Geem avatar updates).
GEEM_LOGO_URL = "https://geem.ai/assets/geem-avatar.webp"
GEEM_WEBSITE_URL = "https://geem.ai"
GEEM_SUPPORT_URL = "https://geem.ai/support"


@dataclass(frozen=True, slots=True)
class InvitationEmailContent:
    subject: str
    text_body: str
    html_body: str


def render_invitation_email(
    *,
    workspace_name: str,
    role: str,
    accept_url: str,
    expires_at: datetime,
    invitee_email: str,
    inviter_email: str | None,
) -> InvitationEmailContent:
    name = _one_line(workspace_name) or "a workspace"
    role_en, role_ar = _role_labels(role)
    expires = _format_expiry(expires_at)
    inviter = (inviter_email or "").strip() or None
    invitee = (invitee_email or "").strip()

    subject = f"You're invited to join {name} on Geem"
    text_body = _text_body(
        name=name,
        role_en=role_en,
        role_ar=role_ar,
        accept_url=accept_url,
        expires=expires,
        invitee=invitee,
        inviter=inviter,
    )
    html_body = _html_body(
        name=name,
        role_en=role_en,
        role_ar=role_ar,
        accept_url=accept_url,
        expires=expires,
        invitee=invitee,
        inviter=inviter,
    )
    return InvitationEmailContent(subject=subject, text_body=text_body, html_body=html_body)


def _one_line(value: str) -> str:
    return " ".join((value or "").split())


def _role_labels(role: str) -> tuple[str, str]:
    display = _one_line(role)
    key = display.lower()
    if key in _ROLE_EN:
        return _ROLE_EN[key], _ROLE_AR[key]
    if not display:
        return _ROLE_EN["member"], _ROLE_AR["member"]
    return display, display


def _format_expiry(expires_at: datetime) -> str:
    when = expires_at
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def _text_body(
    *,
    name: str,
    role_en: str,
    role_ar: str,
    accept_url: str,
    expires: str,
    invitee: str,
    inviter: str | None,
) -> str:
    invited_by = f"Invited by: {inviter}\n" if inviter else ""
    invited_by_ar = f"دعوة من: {inviter}\n" if inviter else ""
    sign_in = f"Sign in or register with {invitee} to accept.\n" if invitee else ""
    sign_in_ar = (
        f"يجب تسجيل الدخول أو إنشاء حساب بالبريد {invitee} لقبول الدعوة.\n" if invitee else ""
    )
    return (
        f"You've been invited to join {name} on Geem.\n\n"
        f"Role: {role_en}\n"
        f"{invited_by}"
        f"Expires: {expires}\n"
        f"{sign_in}\n"
        f"Accept this invitation:\n{accept_url}\n"
        f"Accept: {accept_url}\n\n"
        "If you weren't expecting this email, you can ignore it. "
        "Do not share this link.\n\n"
        "—\n"
        "Geem\n\n"
        f"دُعيت للانضمام إلى {name} على جِيم.\n\n"
        f"الدور: {role_ar}\n"
        f"{invited_by_ar}"
        f"تنتهي الدعوة: {expires}\n"
        f"{sign_in_ar}\n"
        f"اقبل الدعوة:\n{accept_url}\n\n"
        "إذا لم تكن تتوقع هذه الرسالة يمكنك تجاهلها. لا تشارك هذا الرابط.\n\n"
        f"Website: {GEEM_WEBSITE_URL}\n"
        f"Support: {GEEM_SUPPORT_URL}\n"
    )


def _html_body(
    *,
    name: str,
    role_en: str,
    role_ar: str,
    accept_url: str,
    expires: str,
    invitee: str,
    inviter: str | None,
) -> str:
    safe_name = escape(name)
    safe_role_en = escape(role_en)
    safe_role_ar = escape(role_ar)
    safe_expires = escape(expires)
    safe_invitee = escape(invitee)
    safe_inviter = escape(inviter) if inviter else ""
    href = quoteattr(accept_url)
    safe_url = escape(accept_url)

    inviter_row_en = (
        f'<tr><td style="padding:4px 0;color:#52606d;font-size:14px;">Invited by</td>'
        f'<td style="padding:4px 0;color:{BRAND};font-size:14px;text-align:right;">{safe_inviter}</td></tr>'
        if inviter
        else ""
    )
    inviter_row_ar = (
        f'<tr><td style="padding:4px 0;color:{BRAND};font-size:14px;">{safe_inviter}</td>'
        f'<td dir="rtl" style="padding:4px 0;color:#52606d;font-size:14px;text-align:right;">دعوة من</td></tr>'
        if inviter
        else ""
    )
    sign_in_en = (
        f'<p style="margin:16px 0 0;color:#52606d;font-size:14px;line-height:1.5;">'
        f"You must sign in or register with <strong>{safe_invitee}</strong> to accept."
        f"</p>"
        if invitee
        else ""
    )
    sign_in_ar = (
        f'<p dir="rtl" style="margin:16px 0 0;color:#52606d;font-size:14px;line-height:1.5;">'
        f"يجب تسجيل الدخول أو إنشاء حساب بالبريد <strong>{safe_invitee}</strong> لقبول الدعوة."
        f"</p>"
        if invitee
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f4f6f8;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:24px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e4e7eb;">
            <tr>
              <td style="background:{BRAND};padding:18px 28px;font-family:Arial,Helvetica,sans-serif;">
                <table role="presentation" cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="vertical-align:middle;padding-right:12px;">
                      <img src="{GEEM_LOGO_URL}" width="40" height="40" alt="Geem" style="display:block;border:0;border-radius:8px;outline:none;" />
                    </td>
                    <td style="vertical-align:middle;color:#ffffff;font-size:20px;font-weight:bold;letter-spacing:0.04em;">
                      Geem
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;font-family:Arial,Helvetica,sans-serif;color:{BRAND};">
                <p style="margin:0 0 8px;color:{BRAND_ACCENT};font-size:12px;font-weight:bold;letter-spacing:0.08em;text-transform:uppercase;">Workspace invitation</p>
                <h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;color:{BRAND};">You're invited to join {safe_name}</h1>
                <p style="margin:0 0 20px;color:#3e4c59;font-size:15px;line-height:1.6;">
                  Join this Geem workspace to collaborate with the team. This invitation is for a <strong>{safe_role_en}</strong> role.
                </p>
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 24px;background:#f4f6f8;border-radius:8px;padding:0;">
                  <tr>
                    <td style="padding:16px 18px;">
                      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                          <td style="padding:4px 0;color:#52606d;font-size:14px;">Workspace</td>
                          <td style="padding:4px 0;color:{BRAND};font-size:14px;text-align:right;font-weight:bold;">{safe_name}</td>
                        </tr>
                        <tr>
                          <td style="padding:4px 0;color:#52606d;font-size:14px;">Role</td>
                          <td style="padding:4px 0;color:{BRAND};font-size:14px;text-align:right;">{safe_role_en}</td>
                        </tr>
                        {inviter_row_en}
                        <tr>
                          <td style="padding:4px 0;color:#52606d;font-size:14px;">Expires</td>
                          <td style="padding:4px 0;color:{BRAND};font-size:14px;text-align:right;">{safe_expires}</td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
                <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 16px;">
                  <tr>
                    <td style="background:{BRAND_ACCENT};border-radius:8px;">
                      <a href={href} style="display:inline-block;padding:12px 22px;font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:bold;color:#ffffff;text-decoration:none;">Accept invitation</a>
                    </td>
                  </tr>
                </table>
                {sign_in_en}
                <p style="margin:16px 0 0;color:#7b8794;font-size:12px;line-height:1.5;word-break:break-all;">
                  If the button does not work, open this link:<br />
                  <a href={href} style="color:{BRAND_ACCENT};">{safe_url}</a>
                </p>
                <hr style="border:none;border-top:1px solid #e4e7eb;margin:28px 0;" />
                <div dir="rtl" lang="ar" style="text-align:right;">
                  <p style="margin:0 0 8px;color:{BRAND_ACCENT};font-size:12px;font-weight:bold;">دعوة للانضمام إلى مساحة العمل</p>
                  <h2 style="margin:0 0 12px;font-size:18px;line-height:1.4;color:{BRAND};">دُعيت للانضمام إلى {safe_name}</h2>
                  <p style="margin:0 0 16px;color:#3e4c59;font-size:15px;line-height:1.7;">
                    انضم إلى مساحة العمل على جِيم. هذه الدعوة لدور <strong>{safe_role_ar}</strong>.
                  </p>
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;background:#f4f6f8;border-radius:8px;">
                    <tr>
                      <td style="padding:16px 18px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                          <tr>
                            <td style="padding:4px 0;color:{BRAND};font-size:14px;font-weight:bold;">{safe_name}</td>
                            <td style="padding:4px 0;color:#52606d;font-size:14px;text-align:right;">مساحة العمل</td>
                          </tr>
                          <tr>
                            <td style="padding:4px 0;color:{BRAND};font-size:14px;">{safe_role_ar}</td>
                            <td style="padding:4px 0;color:#52606d;font-size:14px;text-align:right;">الدور</td>
                          </tr>
                          {inviter_row_ar}
                          <tr>
                            <td style="padding:4px 0;color:{BRAND};font-size:14px;">{safe_expires}</td>
                            <td style="padding:4px 0;color:#52606d;font-size:14px;text-align:right;">تنتهي</td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                  </table>
                  <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 12px;margin-left:auto;">
                    <tr>
                      <td style="background:{BRAND_ACCENT};border-radius:8px;">
                        <a href={href} style="display:inline-block;padding:12px 22px;font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:bold;color:#ffffff;text-decoration:none;">قبول الدعوة</a>
                      </td>
                    </tr>
                  </table>
                  {sign_in_ar}
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px 24px;font-family:Arial,Helvetica,sans-serif;color:#9aa5b1;font-size:12px;line-height:1.5;">
                If you weren't expecting this email, you can ignore it. Do not share this link.
                <br />
                إذا لم تكن تتوقع هذه الرسالة يمكنك تجاهلها. لا تشارك هذا الرابط.
                <br /><br />
                <a href="{GEEM_WEBSITE_URL}" style="color:{BRAND_ACCENT};text-decoration:none;">Website</a>
                &nbsp;&middot;&nbsp;
                <a href="{GEEM_SUPPORT_URL}" style="color:{BRAND_ACCENT};text-decoration:none;">Support</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
