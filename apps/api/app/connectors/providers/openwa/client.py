"""OpenWA HTTP client — sole low-level owner of provider paths (Swagger 0.15.0)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.connectors.providers.openwa.errors import OpenWAClientError, map_openwa_http_error
from app.connectors.providers.openwa.schemas import (
    OpenWACreateSessionRequest,
    OpenWACreateWebhookRequest,
    OpenWAPairingCodeRequest,
    OpenWAPairingCodeResponse,
    OpenWAQrResponse,
    OpenWASendTextRequest,
    OpenWASendTextResponse,
    OpenWASession,
    OpenWAUpdateWebhookRequest,
    OpenWAWebhook,
)
from app.connectors.sanitize import sanitize_error_message
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCategory

logger = logging.getLogger(__name__)

# Paths verified against live Swagger / OpenAPI 0.15.0
_PATH_SESSIONS = "/api/sessions"
_PATH_SESSION = "/api/sessions/{session_id}"
_PATH_START = "/api/sessions/{session_id}/start"
_PATH_QR = "/api/sessions/{session_id}/qr"
_PATH_PAIRING = "/api/sessions/{session_id}/pairing-code"
_PATH_LOGOUT = "/api/sessions/{session_id}/logout"
_PATH_WEBHOOKS = "/api/sessions/{session_id}/webhooks"
_PATH_WEBHOOK = "/api/sessions/{session_id}/webhooks/{webhook_id}"
_PATH_SEND_TEXT = "/api/sessions/{session_id}/messages/send-text"


class OpenWAClient:
    """Typed OpenWA gateway client. Never log API keys, QR, or pairing codes."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._base_url = (base_url or self.settings.openwa_base_url or "").rstrip("/")
        self._api_key = (api_key if api_key is not None else self.settings.openwa_api_key) or ""
        timeout = float(self.settings.openwa_timeout_seconds or 30.0)
        self._owned = http_client is None
        self._client = http_client or httpx.Client(
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout))
        )

    def close(self) -> None:
        if self._owned:
            self._client.close()

    def __enter__(self) -> OpenWAClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def create_session(self, *, name: str) -> OpenWASession:
        body = OpenWACreateSessionRequest(name=name).model_dump()
        data = self._request_json("POST", _PATH_SESSIONS, json_body=body, expect=(201, 200))
        return OpenWASession.model_validate(data)

    def get_session(self, session_id: str) -> OpenWASession:
        path = _PATH_SESSION.format(session_id=session_id)
        data = self._request_json("GET", path, expect=(200,))
        return OpenWASession.model_validate(data)

    def start_session(self, session_id: str) -> OpenWASession:
        path = _PATH_START.format(session_id=session_id)
        data = self._request_json("POST", path, expect=(200,))
        return OpenWASession.model_validate(data)

    def get_qr(self, session_id: str) -> OpenWAQrResponse:
        path = _PATH_QR.format(session_id=session_id)
        data = self._request_json("GET", path, expect=(200,))
        return OpenWAQrResponse.model_validate(data)

    def request_pairing_code(self, session_id: str, *, phone_number: str) -> OpenWAPairingCodeResponse:
        path = _PATH_PAIRING.format(session_id=session_id)
        body = OpenWAPairingCodeRequest(phoneNumber=phone_number).model_dump()
        data = self._request_json("POST", path, json_body=body, expect=(201, 200))
        return OpenWAPairingCodeResponse.model_validate(data)

    def logout_session(self, session_id: str) -> OpenWASession | None:
        path = _PATH_LOGOUT.format(session_id=session_id)
        data = self._request_json("POST", path, expect=(200,), allow_empty=True)
        if not data:
            return None
        return OpenWASession.model_validate(data)

    def delete_session(self, session_id: str) -> None:
        path = _PATH_SESSION.format(session_id=session_id)
        self._request_json("DELETE", path, expect=(204, 200), allow_empty=True)

    def register_webhook(
        self,
        session_id: str,
        *,
        url: str,
        secret: str,
        events: list[str] | None = None,
    ) -> OpenWAWebhook:
        path = _PATH_WEBHOOKS.format(session_id=session_id)
        req = OpenWACreateWebhookRequest(
            url=url,
            events=list(events) if events is not None else None,
            secret=secret,
        )
        body = req.model_dump(exclude_none=True)
        data = self._request_json("POST", path, json_body=body, expect=(201, 200))
        return OpenWAWebhook.model_validate(data)

    def list_webhooks(self, session_id: str) -> list[OpenWAWebhook]:
        path = _PATH_WEBHOOKS.format(session_id=session_id)
        data = self._request_json("GET", path, expect=(200,))
        if not isinstance(data, list):
            return []
        return [OpenWAWebhook.model_validate(item) for item in data]

    def update_webhook(
        self,
        session_id: str,
        webhook_id: str,
        *,
        url: str | None = None,
        secret: str | None = None,
        events: list[str] | None = None,
        active: bool | None = None,
    ) -> OpenWAWebhook:
        path = _PATH_WEBHOOK.format(session_id=session_id, webhook_id=webhook_id)
        req = OpenWAUpdateWebhookRequest(
            url=url, secret=secret, events=events, active=active
        )
        body = req.model_dump(exclude_none=True)
        data = self._request_json("PUT", path, json_body=body, expect=(200,))
        return OpenWAWebhook.model_validate(data)

    def delete_webhook(self, session_id: str, webhook_id: str) -> None:
        path = _PATH_WEBHOOK.format(session_id=session_id, webhook_id=webhook_id)
        self._request_json("DELETE", path, expect=(204, 200), allow_empty=True)

    def send_text(
        self,
        session_id: str,
        *,
        chat_id: str,
        text: str,
        link_preview: bool = False,
    ) -> OpenWASendTextResponse:
        path = _PATH_SEND_TEXT.format(session_id=session_id)
        body = OpenWASendTextRequest(
            chatId=chat_id, text=text, linkPreview=link_preview
        ).model_dump(exclude_none=True)
        data = self._request_json("POST", path, json_body=body, expect=(201, 200))
        return OpenWASendTextResponse.model_validate(data)

    def _headers(self) -> dict[str, str]:
        if not self._api_key.strip():
            raise OpenWAClientError(
                ErrorCategory.OPENWA_NOT_CONFIGURED,
                "OpenWA API key is not configured.",
            )
        return {
            "X-API-Key": self._api_key.strip(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        if not self._base_url:
            raise OpenWAClientError(
                ErrorCategory.OPENWA_NOT_CONFIGURED,
                "OpenWA base URL is not configured.",
            )
        return f"{self._base_url}{path}"

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        expect: tuple[int, ...],
        allow_empty: bool = False,
    ) -> Any:
        url = self._url(path)
        try:
            response = self._client.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
            )
        except httpx.TimeoutException as exc:
            raise OpenWAClientError(
                ErrorCategory.OPENWA_TIMEOUT,
                "OpenWA request timed out.",
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenWAClientError(
                ErrorCategory.OPENWA_UNAVAILABLE,
                "OpenWA is unreachable.",
                details={"error": sanitize_error_message(str(exc))},
            ) from exc

        if response.status_code not in expect:
            body: Any
            try:
                body = response.json()
            except Exception:  # noqa: BLE001
                body = {"message": (response.text or "")[:300]}
            logger.info(
                "openwa_http_error",
                extra={
                    "operation": f"{method} {path}",
                    "status_code": response.status_code,
                },
            )
            raise map_openwa_http_error(
                status_code=response.status_code,
                body=body,
                operation=f"{method} {path}",
            )

        if response.status_code == 204 or not (response.content or b"").strip():
            if allow_empty:
                return None
            return {}
        try:
            return response.json()
        except Exception as exc:  # noqa: BLE001
            raise OpenWAClientError(
                ErrorCategory.OPENWA_REQUEST_INVALID,
                "OpenWA returned an invalid JSON response.",
            ) from exc
