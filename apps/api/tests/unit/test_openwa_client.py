"""Phase 9F — OpenWA HTTP client unit tests."""

from __future__ import annotations

import httpx
import pytest

from app.connectors.providers.openwa.client import OpenWAClient
from app.core.config import Settings
from app.core.errors import ErrorCategory


def _settings(**overrides) -> Settings:
    values = {
        "openwa_base_url": "https://openwa.example.test",
        "openwa_api_key": "test-openwa-key",
        "openwa_timeout_seconds": 5,
    }
    values.update(overrides)
    return Settings(**values)


def test_openwa_client_uses_headers_paths_and_parses_responses() -> None:
    seen: list[tuple[str, str, dict[str, str] | None, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = None
        if request.content:
            body = __import__("json").loads(request.content.decode("utf-8"))
        seen.append((request.method, request.url.path, dict(request.headers), body))
        if request.url.path == "/api/sessions":
            return httpx.Response(
                201,
                json={"id": "sess-1", "name": "geem-ws-1", "status": "created"},
            )
        if request.url.path == "/api/sessions/sess-1/qr":
            return httpx.Response(
                200,
                json={"status": "qr_ready", "qrCode": "data:image/png;base64,qr"},
            )
        if request.url.path == "/api/sessions/sess-1/pairing-code":
            return httpx.Response(
                201,
                json={"status": "qr_ready", "pairingCode": "ABCD1234"},
            )
        if request.url.path == "/api/sessions/sess-1/messages/send-text":
            return httpx.Response(
                201,
                json={"messageId": "msg-1", "timestamp": 1723900000},
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    client = OpenWAClient(settings=_settings(), http_client=http_client)

    created = client.create_session(name="geem-ws-1")
    qr = client.get_qr("sess-1")
    pairing = client.request_pairing_code("sess-1", phone_number="966500000000")
    sent = client.send_text("sess-1", chat_id="966500000000@c.us", text="مرحبا")

    assert created.id == "sess-1"
    assert qr.qrCode.startswith("data:image/png")
    assert pairing.pairingCode == "ABCD1234"
    assert sent.messageId == "msg-1"

    assert [item[1] for item in seen] == [
        "/api/sessions",
        "/api/sessions/sess-1/qr",
        "/api/sessions/sess-1/pairing-code",
        "/api/sessions/sess-1/messages/send-text",
    ]
    assert all(item[2]["x-api-key"] == "test-openwa-key" for item in seen)
    assert seen[2][3] == {"phoneNumber": "966500000000"}
    assert seen[3][3] == {
        "chatId": "966500000000@c.us",
        "text": "مرحبا",
        "linkPreview": False,
    }


@pytest.mark.parametrize(
    ("status_code", "body", "expected"),
    [
        (401, {"message": "bad key"}, ErrorCategory.OPENWA_UNAUTHORIZED),
        (404, {"message": "missing"}, ErrorCategory.OPENWA_SESSION_NOT_FOUND),
        (
            409,
            {"code": "SESSION_NAME_TEARDOWN_PENDING"},
            ErrorCategory.OPENWA_SESSION_CONFLICT,
        ),
        (500, {"message": "boom"}, ErrorCategory.OPENWA_UNAVAILABLE),
    ],
)
def test_openwa_client_maps_http_errors(
    status_code: int,
    body: dict,
    expected: ErrorCategory,
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json=body))
    client = OpenWAClient(
        settings=_settings(),
        http_client=httpx.Client(transport=transport),
    )

    with pytest.raises(Exception) as excinfo:
        client.get_session("sess-404")

    assert getattr(excinfo.value, "category", None) == expected


def test_openwa_client_is_unavailable_without_required_config() -> None:
    client = OpenWAClient(
        settings=_settings(openwa_api_key="", openwa_base_url=""),
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: None)),
    )

    with pytest.raises(Exception) as excinfo:
        client.get_session("sess-1")

    assert getattr(excinfo.value, "category", None) == ErrorCategory.OPENWA_NOT_CONFIGURED
