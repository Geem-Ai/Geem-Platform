"""Password-reset email copy (plain text + HTML). User-controlled fields are escaped in HTML."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from xml.sax.saxutils import quoteattr

BRAND = "#0e2f44"
BRAND_ACCENT = "#367d9e"

GEEM_LOGO_URL = "https://geem.ai/assets/geem-avatar.webp"
GEEM_WEBSITE_URL = "https://geem.ai"
GEEM_SUPPORT_URL = "https://geem.ai/support"


@dataclass(frozen=True, slots=True)
class PasswordResetEmailContent:
    subject: str
    text_body: str
    html_body: str


def render_password_reset_email(
    *,
    reset_url: str,
    expires_at: datetime,
    email: str,
) -> PasswordResetEmailContent:
    expires = _format_expiry(expires_at)
    safe_email = (email or "").strip()

    subject = "Reset your Geem password"
    text_body = _text_body(reset_url=reset_url, expires=expires, email=safe_email)
    html_body = _html_body(reset_url=reset_url, expires=expires, email=safe_email)
    return PasswordResetEmailContent(subject=subject, text_body=text_body, html_body=html_body)


def _format_expiry(expires_at: datetime) -> str:
    when = expires_at
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def _text_body(*, reset_url: str, expires: str, email: str) -> str:
    account = f"Account: {email}\n" if email else ""
    account_ar = f"الحساب: {email}\n" if email else ""
    return (
        "Reset your Geem password\n\n"
        f"{account}"
        f"This link expires: {expires}\n\n"
        f"Reset your password:\n{reset_url}\n\n"
        "If you did not request a password reset, you can ignore this email. "
        "Do not share this link.\n\n"
        "—\n"
        "Geem\n\n"
        "إعادة تعيين كلمة مرور جِيم\n\n"
        f"{account_ar}"
        f"ينتهي الرابط: {expires}\n\n"
        f"أعد تعيين كلمة المرور:\n{reset_url}\n\n"
        "إذا لم تطلب إعادة التعيين يمكنك تجاهل هذه الرسالة. لا تشارك هذا الرابط.\n\n"
        f"Website: {GEEM_WEBSITE_URL}\n"
        f"Support: {GEEM_SUPPORT_URL}\n"
    )


def _html_body(*, reset_url: str, expires: str, email: str) -> str:
    safe_expires = escape(expires)
    safe_email = escape(email)
    href = quoteattr(reset_url)
    safe_url = escape(reset_url)

    email_row_en = (
        f'<tr><td style="padding:4px 0;color:#52606d;font-size:14px;">Account</td>'
        f'<td style="padding:4px 0;color:{BRAND};font-size:14px;text-align:right;">{safe_email}</td></tr>'
        if email
        else ""
    )
    email_row_ar = (
        f'<tr><td style="padding:4px 0;color:{BRAND};font-size:14px;">{safe_email}</td>'
        f'<td dir="rtl" style="padding:4px 0;color:#52606d;font-size:14px;text-align:right;">الحساب</td></tr>'
        if email
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
              <td style="background:{BRAND};padding:20px 28px;">
                <img src="{GEEM_LOGO_URL}" alt="Geem" width="40" height="40" style="display:block;border-radius:8px;" />
              </td>
            </tr>
            <tr>
              <td style="padding:28px;">
                <h1 style="margin:0 0 12px;color:{BRAND};font-size:22px;font-family:Arial,sans-serif;">Reset your password</h1>
                <p style="margin:0 0 16px;color:#52606d;font-size:15px;line-height:1.5;font-family:Arial,sans-serif;">
                  We received a request to reset the password for your Geem account.
                </p>
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;">
                  {email_row_en}
                  <tr>
                    <td style="padding:4px 0;color:#52606d;font-size:14px;font-family:Arial,sans-serif;">Expires</td>
                    <td style="padding:4px 0;color:{BRAND};font-size:14px;text-align:right;font-family:Arial,sans-serif;">{safe_expires}</td>
                  </tr>
                </table>
                <a href={href} style="display:inline-block;background:{BRAND_ACCENT};color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:8px;font-size:15px;font-family:Arial,sans-serif;font-weight:600;">
                  Reset password
                </a>
                <p style="margin:20px 0 0;color:#8a94a6;font-size:12px;line-height:1.5;font-family:Arial,sans-serif;word-break:break-all;">
                  Or paste this link into your browser:<br />{safe_url}
                </p>
                <p style="margin:20px 0 0;color:#8a94a6;font-size:13px;line-height:1.5;font-family:Arial,sans-serif;">
                  If you did not request this, you can ignore this email. Do not share this link.
                </p>
                <hr style="border:none;border-top:1px solid #e4e7eb;margin:28px 0;" />
                <h2 dir="rtl" style="margin:0 0 12px;color:{BRAND};font-size:20px;font-family:Arial,sans-serif;text-align:right;">إعادة تعيين كلمة المرور</h2>
                <p dir="rtl" style="margin:0 0 16px;color:#52606d;font-size:15px;line-height:1.5;font-family:Arial,sans-serif;text-align:right;">
                  تلقينا طلباً لإعادة تعيين كلمة مرور حسابك على جِيم.
                </p>
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px;">
                  {email_row_ar}
                  <tr>
                    <td style="padding:4px 0;color:{BRAND};font-size:14px;font-family:Arial,sans-serif;">{safe_expires}</td>
                    <td dir="rtl" style="padding:4px 0;color:#52606d;font-size:14px;text-align:right;font-family:Arial,sans-serif;">ينتهي</td>
                  </tr>
                </table>
                <p dir="rtl" style="text-align:right;margin:0;">
                  <a href={href} style="display:inline-block;background:{BRAND_ACCENT};color:#ffffff;text-decoration:none;padding:12px 22px;border-radius:8px;font-size:15px;font-family:Arial,sans-serif;font-weight:600;">
                    أعد تعيين كلمة المرور
                  </a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 28px 24px;background:#f9fafb;color:#8a94a6;font-size:12px;font-family:Arial,sans-serif;">
                <a href="{GEEM_WEBSITE_URL}" style="color:{BRAND_ACCENT};text-decoration:none;">geem.ai</a>
                &nbsp;·&nbsp;
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
