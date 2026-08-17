"""Fake Google Drive HTTP client for Phase 9D tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

from app.core.errors import AppError, ErrorCategory


class FakeGoogleDriveClient:
    """In-memory Drive/OAuth stand-in — never talks to Google."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _ = args, kwargs
        self.files: dict[str, dict[str, Any]] = {}
        self.file_bytes: dict[str, bytes] = {}
        self.start_page_token = "token-1"
        self.changes_pages: list[dict[str, Any]] = []
        self.watch_result: dict[str, Any] = {
            "id": "channel-1",
            "resourceId": "resource-1",
            "expiration": str(
                int((datetime.now(timezone.utc) + timedelta(days=1)).timestamp() * 1000)
            ),
        }
        self.stopped_channels: list[tuple[str, str]] = []
        self.userinfo = {
            "sub": "google-user-1",
            "email": "drive-user@example.com",
            "name": "Drive User",
        }
        self.token_response = {
            "access_token": "access-test-token",
            "refresh_token": "refresh-test-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": (
                "openid https://www.googleapis.com/auth/userinfo.email "
                "https://www.googleapis.com/auth/userinfo.profile "
                "https://www.googleapis.com/auth/drive.file"
            ),
        }
        self.fail_refresh = False
        self.access_token: str | None = kwargs.get("access_token")

    def close(self) -> None:
        return None

    def exchange_code(self, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return dict(self.token_response)

    def refresh_access_token(self, *, refresh_token: str) -> dict[str, Any]:
        if self.fail_refresh:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_REAUTHORIZATION_REQUIRED,
                "invalid_grant",
            )
        return {
            "access_token": f"refreshed-{refresh_token[:8]}",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

    def get_userinfo(self, *, access_token: str | None = None) -> dict[str, Any]:
        _ = access_token
        return dict(self.userinfo)

    def get_about_user(self, *, access_token: str | None = None) -> dict[str, Any]:
        _ = access_token
        return {
            "user": {
                "displayName": self.userinfo.get("name"),
                "emailAddress": self.userinfo.get("email"),
            }
        }

    def get_file_metadata(self, file_id: str, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        if file_id not in self.files:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_FILE_NOT_FOUND, "File not found."
            )
        return dict(self.files[file_id])

    def download_blob(self, file_id: str, **kwargs: Any) -> bytes:
        max_bytes = int(kwargs.get("max_bytes") or 10_000_000)
        data = self.file_bytes.get(file_id, b"hello from drive")
        if len(data) > max_bytes:
            raise AppError(
                ErrorCategory.GOOGLE_DRIVE_EXPORT_TOO_LARGE, "too large"
            )
        return data

    def export_workspace_file(self, file_id: str, **kwargs: Any) -> bytes:
        return self.download_blob(file_id, **kwargs)

    def list_files_page(self, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {"files": [{"id": fid} for fid in list(self.files)[:1]]}

    def get_start_page_token(self, **kwargs: Any) -> str:
        _ = kwargs
        return self.start_page_token

    def list_changes(self, *, page_token: str, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        if self.changes_pages:
            return self.changes_pages.pop(0)
        return {
            "changes": [],
            "newStartPageToken": f"next-{page_token}",
        }

    def create_changes_watch(self, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return dict(self.watch_result)

    def stop_channel(self, *, channel_id: str, resource_id: str, **kwargs: Any) -> None:
        _ = kwargs
        self.stopped_channels.append((channel_id, resource_id))

    def add_file(
        self,
        file_id: str,
        *,
        name: str = "doc.pdf",
        mime_type: str = "application/pdf",
        content: bytes = b"%PDF-1.4 fake",
        version: str = "1",
        trashed: bool = False,
    ) -> None:
        self.files[file_id] = {
            "id": file_id,
            "name": name,
            "mimeType": mime_type,
            "modifiedTime": "2024-01-01T00:00:00.000Z",
            "version": version,
            "md5Checksum": "abc",
            "size": str(len(content)),
            "trashed": trashed,
            "webViewLink": f"https://drive.google.com/file/d/{file_id}/view",
        }
        self.file_bytes[file_id] = content


def patch_google_drive_client(monkeypatch, fake: FakeGoogleDriveClient | None = None):
    """Monkeypatch GoogleDriveClient constructor to return a shared fake."""
    fake = fake or FakeGoogleDriveClient()

    def _factory(*args: Any, **kwargs: Any) -> FakeGoogleDriveClient:
        if kwargs.get("access_token"):
            fake.access_token = kwargs["access_token"]
        return fake

    monkeypatch.setattr(
        "app.connectors.providers.google_drive.client.GoogleDriveClient",
        _factory,
    )
    monkeypatch.setattr(
        "app.connectors.providers.google_drive.adapter.GoogleDriveClient",
        _factory,
    )
    monkeypatch.setattr(
        "app.connectors.providers.google_drive.token.GoogleDriveClient",
        _factory,
    )
    monkeypatch.setattr(
        "app.experts.connector_sources.GoogleDriveClient",
        _factory,
    )
    return fake
