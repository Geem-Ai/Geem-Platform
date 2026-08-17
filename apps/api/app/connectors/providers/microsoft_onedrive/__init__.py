"""Microsoft OneDrive knowledge connector (Phase 9E)."""

from app.connectors.providers.microsoft_onedrive.adapter import (
    MicrosoftOneDriveConnector,
    register_microsoft_onedrive_connector,
)

__all__ = ["MicrosoftOneDriveConnector", "register_microsoft_onedrive_connector"]
