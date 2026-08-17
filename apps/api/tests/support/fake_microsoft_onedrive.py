"""Fake Microsoft Graph / OneDrive client for Phase 9E tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.core.errors import AppError, ErrorCategory


class FakeMicrosoftOneDriveClient:
    """In-memory Graph/OAuth stand-in — never talks to Microsoft."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _ = args
        self.access_token: str | None = kwargs.get("access_token")
        self.tenant = kwargs.get("tenant") or "organizations"
        self.me = {
            "id": "ms-user-1",
            "displayName": "OneDrive User",
            "userPrincipalName": "user@contoso.com",
            "mail": "user@contoso.com",
        }
        self.drive = {
            "id": "drive-1",
            "driveType": "business",
            "webUrl": "https://contoso-my.sharepoint.com/personal/user_contoso_com",
            "name": "OneDrive",
        }
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.item_bytes: dict[tuple[str, str], bytes] = {}
        self.convert_bytes: dict[tuple[str, str], bytes] = {}
        self.convert_fail: set[tuple[str, str]] = set()
        self.delta_pages: list[dict[str, Any]] = []
        self.delta_calls: list[str | None] = []
        self.subscriptions: dict[str, dict[str, Any]] = {}
        self.deleted_subscriptions: list[str] = []
        self.token_response = {
            "access_token": "ms-access-token",
            "refresh_token": "ms-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "openid profile offline_access User.Read Files.Read",
        }
        self.fail_refresh = False
        self.fail_exchange = False
        self.resource_tokens: dict[str, str] = {}
        self._sub_counter = 0

    def close(self) -> None:
        return None

    def exchange_code(self, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        if self.fail_exchange:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_AUTHORIZATION_FAILED,
                "Microsoft authorization failed.",
                details={"oauth_error": "invalid_client", "status": 401},
            )
        return dict(self.token_response)

    def refresh_access_token(
        self, *, refresh_token: str, scope: str | None = None
    ) -> dict[str, Any]:
        if self.fail_refresh:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_REAUTHORIZATION_REQUIRED,
                "invalid_grant",
            )
        payload = {
            "access_token": f"refreshed-{refresh_token[:8]}",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        if scope:
            payload["scope"] = scope
        return payload

    def acquire_resource_token(
        self, *, refresh_token: str, resource: str
    ) -> dict[str, Any]:
        token = self.resource_tokens.get(resource, f"sp-token-for-{resource}")
        payload: dict[str, Any] = {
            "access_token": token,
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        # Optionally rotate refresh token (tests can set rotate_refresh=True).
        if getattr(self, "rotate_refresh", False):
            payload["refresh_token"] = f"rotated-{refresh_token}"
        return payload

    def get_me(self, *, access_token: str | None = None) -> dict[str, Any]:
        _ = access_token
        return dict(self.me)

    def get_drive(self, *, access_token: str | None = None) -> dict[str, Any]:
        _ = access_token
        return dict(self.drive)

    def get_item(
        self, *, drive_id: str, item_id: str, access_token: str | None = None
    ) -> dict[str, Any]:
        _ = access_token
        key = (drive_id, item_id)
        if key not in self.items:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_ITEM_NOT_FOUND,
                "Item not found.",
            )
        return dict(self.items[key])

    def download_content(
        self,
        *,
        drive_id: str,
        item_id: str,
        max_bytes: int,
        access_token: str | None = None,
    ) -> bytes:
        _ = access_token
        data = self.item_bytes.get((drive_id, item_id), b"hello from onedrive")
        if len(data) > max_bytes:
            raise AppError(ErrorCategory.UPLOAD_TOO_LARGE, "too large")
        return data

    def convert_content_to_pdf(
        self,
        *,
        drive_id: str,
        item_id: str,
        max_bytes: int,
        access_token: str | None = None,
    ) -> bytes:
        _ = access_token
        key = (drive_id, item_id)
        if key in self.convert_fail:
            raise AppError(
                ErrorCategory.MICROSOFT_ONEDRIVE_CONVERSION_FAILED,
                "conversion failed",
            )
        data = self.convert_bytes.get(key, b"%PDF-1.4 converted")
        if len(data) > max_bytes:
            raise AppError(ErrorCategory.UPLOAD_TOO_LARGE, "too large")
        return data

    def delta(
        self,
        *,
        drive_id: str,
        delta_link: str | None = None,
        access_token: str | None = None,
    ) -> dict[str, Any]:
        _ = drive_id, access_token
        self.delta_calls.append(delta_link)
        if self.delta_pages:
            return self.delta_pages.pop(0)
        # Default: empty page with a stable deltaLink.
        return {
            "value": [],
            "@odata.deltaLink": delta_link
            or "https://graph.microsoft.com/v1.0/drives/drive-1/root/delta?token=baseline",
        }

    def create_subscription(self, **kwargs: Any) -> dict[str, Any]:
        self._sub_counter += 1
        sub_id = f"sub-{self._sub_counter}"
        exp = (
            datetime.now(timezone.utc) + timedelta(days=2)
        ).isoformat().replace("+00:00", "Z")
        payload = {
            "id": sub_id,
            "resource": kwargs.get("resource"),
            "expirationDateTime": kwargs.get("expiration_datetime") or exp,
            "clientState": kwargs.get("client_state"),
            "changeType": kwargs.get("change_type", "updated"),
            "notificationUrl": kwargs.get("notification_url"),
        }
        self.subscriptions[sub_id] = payload
        return dict(payload)

    def renew_subscription(
        self, *, subscription_id: str, expiration_datetime: str, **kwargs: Any
    ) -> dict[str, Any]:
        _ = kwargs
        existing = self.subscriptions.get(subscription_id, {"id": subscription_id})
        existing["expirationDateTime"] = expiration_datetime
        self.subscriptions[subscription_id] = existing
        return dict(existing)

    def delete_subscription(self, *, subscription_id: str, **kwargs: Any) -> None:
        _ = kwargs
        self.deleted_subscriptions.append(subscription_id)
        self.subscriptions.pop(subscription_id, None)

    def add_file(
        self,
        *,
        drive_id: str = "drive-1",
        item_id: str = "item-1",
        name: str = "doc.pdf",
        mime_type: str = "application/pdf",
        content: bytes = b"%PDF-1.4 fake",
        c_tag: str = "c1",
        e_tag: str = "e1",
        drive_type: str = "business",
        deleted: bool = False,
        folder: bool = False,
    ) -> None:
        key = (drive_id, item_id)
        meta: dict[str, Any] = {
            "id": item_id,
            "name": name,
            "size": len(content),
            "eTag": e_tag,
            "cTag": c_tag,
            "lastModifiedDateTime": "2024-01-01T00:00:00Z",
            "webUrl": f"https://contoso-my.sharepoint.com/{item_id}",
            "parentReference": {"driveId": drive_id, "driveType": drive_type},
        }
        if deleted:
            meta["deleted"] = {"state": "deleted"}
        elif folder:
            meta["folder"] = {"childCount": 0}
        else:
            meta["file"] = {"mimeType": mime_type}
        self.items[key] = meta
        self.item_bytes[key] = content


def patch_microsoft_onedrive_client(
    monkeypatch, fake: FakeMicrosoftOneDriveClient | None = None
):
    """Monkeypatch MicrosoftOneDriveClient constructor to return a shared fake."""
    fake = fake or FakeMicrosoftOneDriveClient()

    def _factory(*args: Any, **kwargs: Any) -> FakeMicrosoftOneDriveClient:
        if kwargs.get("access_token"):
            fake.access_token = kwargs["access_token"]
        if kwargs.get("tenant"):
            fake.tenant = kwargs["tenant"]
        return fake

    targets = [
        "app.connectors.providers.microsoft_onedrive.client.MicrosoftOneDriveClient",
        "app.connectors.providers.microsoft_onedrive.adapter.MicrosoftOneDriveClient",
        "app.connectors.providers.microsoft_onedrive.token.MicrosoftOneDriveClient",
        "app.connectors.providers.microsoft_onedrive.resolve.MicrosoftOneDriveClient",
        "app.connectors.providers.microsoft_onedrive.picker_auth.MicrosoftOneDriveClient",
    ]
    for target in targets:
        monkeypatch.setattr(target, _factory)
    return fake
