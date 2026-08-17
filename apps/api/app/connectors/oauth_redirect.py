"""Resolve OAuth redirect URIs per connector key (Phase 9E)."""

from __future__ import annotations

from app.core.config import Settings


def effective_oauth_redirect_uri(settings: Settings, connector_key: str) -> str:
    """Return the redirect URI for the given connector.

    Google Drive may override via ``GOOGLE_DRIVE_REDIRECT_URI``.
    Microsoft OneDrive may override via ``MICROSOFT_ONEDRIVE_REDIRECT_URI``.
    Otherwise derive ``{APP_URL}/api/connectors/oauth/{connector_key}/callback``.
    """
    key = (connector_key or "").strip()
    if key == "google_drive":
        return settings.effective_google_drive_redirect_uri
    if key == "microsoft_onedrive":
        return settings.effective_microsoft_onedrive_redirect_uri
    base = (settings.app_url or "").rstrip("/")
    return f"{base}/api/connectors/oauth/{key}/callback"
