"""Google Drive knowledge-source connector (Phase 9D)."""

from app.connectors.providers.google_drive.adapter import (
    GoogleDriveConnector,
    register_google_drive_connector,
)

__all__ = ["GoogleDriveConnector", "register_google_drive_connector"]
