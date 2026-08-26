from __future__ import annotations

import json
import uuid
from dataclasses import replace
from types import MethodType
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.connectors.oauth_state import OAuthStatePayload
from app.core.config import Settings
from app.core.errors import AppError, ErrorCategory
from app.mcp.oauth import (
    McpOAuthService,
    OAuthHttpResponse,
    _ConnectionSnapshot,
    _PersistedStart,
    _apply_mcp_token_response,
    _is_concurrent_refresh_winner,
    _parse_bearer_challenge,
    _validate_callback_issuer,
    _without_token_material,
)
from app.mcp.gateway_client import HttpMcpGatewayClient


class _Gateway:
    def __init__(self, responses: list[OAuthHttpResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def request(self, **kwargs) -> OAuthHttpResponse:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected outbound OAuth request")
        return self.responses.pop(0)


class _StateStore:
    def __init__(self) -> None:
        self.created: dict | None = None

    def create(self, **kwargs) -> OAuthStatePayload:
        self.created = kwargs
        return OAuthStatePayload(
            state="state-value",
            workspace_id=kwargs["workspace_id"],
            actor_id=kwargs["actor_id"],
            app_installation_id=kwargs["app_installation_id"],
            connector_key=kwargs["connector_key"],
            connection_id=kwargs["connection_id"],
            return_path=kwargs["return_path"],
            code_verifier="v" * 64,
            binding=kwargs["binding"],
            created_at=1.0,
        )


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "app_url": "https://api.geem.example",
        "workspace_web_url": "https://app.geem.example",
        "mcp_connector_enabled": True,
        "mcp_client_metadata_url": (
            "https://api.geem.example/api/connectors/oauth/"
            "mcp_remote/client-metadata.json"
        ),
    }
    values.update(overrides)
    return Settings(**values)


def _json_response(status: int, payload: dict, **headers: str) -> OAuthHttpResponse:
    return OAuthHttpResponse(
        status_code=status,
        headers=headers,
        body=json.dumps(payload, separators=(",", ":")).encode(),
    )


def _snapshot(*, strategy: str = "cimd") -> _ConnectionSnapshot:
    return _ConnectionSnapshot(
        workspace_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        installation_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        server_url="https://mcp.example.com/mcp",
        resource_uri="https://mcp.example.com/mcp",
        auth={"mode": "oauth", "strategy": strategy, "scopes": []},
        credential_epoch=1,
        encrypted_credentials="old-ciphertext",
        had_principal=False,
    )


def _discovery_responses(*, issuer: str = "https://auth.example.com") -> list[OAuthHttpResponse]:
    return [
        OAuthHttpResponse(
            status_code=401,
            headers={
                "WWW-Authenticate": (
                    'Bearer resource_metadata="https://mcp.example.com/prm", '
                    'scope="files:read"'
                )
            },
            body=b"",
        ),
        _json_response(
            200,
            {
                "resource": "https://mcp.example.com/mcp",
                "authorization_servers": [issuer],
                "scopes_supported": ["files:read", "files:write"],
            },
        ),
        _json_response(
            200,
            {
                "issuer": issuer,
                "authorization_endpoint": f"{issuer}/authorize",
                "token_endpoint": f"{issuer}/token",
                "code_challenge_methods_supported": ["S256"],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_methods_supported": ["none"],
                "client_id_metadata_document_supported": True,
                "authorization_response_iss_parameter_supported": True,
            },
        ),
    ]


def test_cimd_document_is_exact_and_secret_free() -> None:
    service = McpOAuthService(settings=_settings())
    document = service.public_client_metadata()
    assert document == {
        "client_id": (
            "https://api.geem.example/api/connectors/oauth/"
            "mcp_remote/client-metadata.json"
        ),
        "client_name": "Geem",
        "client_uri": "https://app.geem.example",
        "redirect_uris": [
            "https://api.geem.example/api/connectors/oauth/mcp_remote/callback"
        ],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": "web",
    }
    assert "secret" not in json.dumps(document).casefold()


def test_start_uses_401_prm_pkce_resource_and_bound_state() -> None:
    snapshot = _snapshot()
    gateway = _Gateway(_discovery_responses())
    states = _StateStore()
    service = McpOAuthService(
        settings=_settings(), gateway=gateway, state_service=states  # type: ignore[arg-type]
    )
    service._admit_start = MethodType(  # type: ignore[method-assign]
        lambda _self, **_kwargs: snapshot,
        service,
    )
    service._persist_start = MethodType(  # type: ignore[method-assign]
        lambda _self, **_kwargs: _PersistedStart(
            installation_id=snapshot.installation_id,
            credential_epoch=1,
            encrypted_credentials="new-ciphertext",
            reauthorization=False,
        ),
        service,
    )

    result = service.start_authorization(
        workspace_id=snapshot.workspace_id,
        actor_id=snapshot.actor_id,
        connection_id=snapshot.connection_id,
        return_path="/apps/mcp",
    )

    query = parse_qs(urlsplit(result.authorization_url).query)
    assert query["response_type"] == ["code"]
    assert query["resource"] == [snapshot.resource_uri]
    assert query["scope"] == ["files:read"]
    assert query["state"] == ["state-value"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["code_challenge"][0]) == 43
    assert [call["method"] for call in gateway.calls] == ["POST", "GET", "GET"]
    assert gateway.calls[0]["url"] == snapshot.server_url
    assert states.created is not None
    binding = states.created["binding"]
    assert binding["issuer"] == "https://auth.example.com"
    assert binding["resource"] == snapshot.resource_uri
    assert binding["credential_token_sha256"]
    assert "client_secret" not in binding
    assert "access_token" not in binding


def test_oauth_challenge_posts_fixed_initialize_first() -> None:
    snapshot = _snapshot(strategy="dynamic_registration")
    challenge = _discovery_responses()[0]
    gateway = _Gateway([challenge])
    service = McpOAuthService(settings=_settings(), gateway=gateway)

    response = service._oauth_challenge(snapshot)

    assert response is challenge
    assert [call["method"] for call in gateway.calls] == ["POST"]
    post = gateway.calls[0]
    assert post["url"] == snapshot.server_url
    assert post["follow_redirects"] is False
    assert post["headers"] == {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    assert json.loads(post["body"]) == {
        "jsonrpc": "2.0",
        "id": "oauth-discovery",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "Geem", "version": "1"},
        },
    }


@pytest.mark.parametrize("post_status", [400, 404, 405])
def test_oauth_challenge_falls_back_to_legacy_get(post_status: int) -> None:
    snapshot = _snapshot(strategy="dynamic_registration")
    challenge = _discovery_responses()[0]
    gateway = _Gateway(
        [
            OAuthHttpResponse(status_code=post_status, headers={}, body=b""),
            challenge,
        ]
    )
    service = McpOAuthService(settings=_settings(), gateway=gateway)

    response = service._oauth_challenge(snapshot)

    assert response is challenge
    assert [call["method"] for call in gateway.calls] == ["POST", "GET"]
    get = gateway.calls[1]
    assert get["url"] == snapshot.server_url
    assert get["headers"] == {"Accept": "application/json, text/event-stream"}
    assert get["follow_redirects"] is True


@pytest.mark.parametrize("post_status", [200, 302, 403, 429, 500])
def test_oauth_challenge_does_not_fallback_for_other_post_statuses(
    post_status: int,
) -> None:
    snapshot = _snapshot(strategy="dynamic_registration")
    gateway = _Gateway(
        [OAuthHttpResponse(status_code=post_status, headers={}, body=b"")]
    )
    service = McpOAuthService(settings=_settings(), gateway=gateway)

    with pytest.raises(AppError) as caught:
        service._discover_flow(snapshot, requested_scopes=None)

    assert caught.value.category == ErrorCategory.MCP_AUTH_REQUIRED
    assert [call["method"] for call in gateway.calls] == ["POST"]


def test_oauth_challenge_does_not_pair_initialize_with_discovery_revision() -> None:
    snapshot = _snapshot(strategy="dynamic_registration")
    challenge = _discovery_responses()[0]
    gateway = _Gateway([challenge])
    service = McpOAuthService(
        settings=_settings(mcp_supported_protocol_versions="2026-07-28"),
        gateway=gateway,
    )

    response = service._oauth_challenge(snapshot)

    assert response is challenge
    assert [call["method"] for call in gateway.calls] == ["GET"]


def test_start_rejects_resource_mismatch_before_registration() -> None:
    snapshot = _snapshot()
    responses = _discovery_responses()
    responses[1] = _json_response(
        200,
        {
            "resource": "https://other.example.com/mcp",
            "authorization_servers": ["https://auth.example.com"],
        },
    )
    gateway = _Gateway(responses)
    service = McpOAuthService(settings=_settings(), gateway=gateway)
    service._admit_start = MethodType(  # type: ignore[method-assign]
        lambda _self, **_kwargs: snapshot,
        service,
    )
    with pytest.raises(AppError) as caught:
        service.start_authorization(
            workspace_id=snapshot.workspace_id,
            actor_id=snapshot.actor_id,
            connection_id=snapshot.connection_id,
            return_path=None,
        )
    assert caught.value.category == ErrorCategory.MCP_AUTH_REQUIRED
    assert len(gateway.calls) == 2


def test_dynamic_registration_is_issuer_bound_and_no_redirects() -> None:
    snapshot = _snapshot(strategy="dynamic_registration")
    responses = _discovery_responses()
    metadata = json.loads(responses[2].body)
    metadata["registration_endpoint"] = "https://auth.example.com/register"
    metadata["client_id_metadata_document_supported"] = False
    responses[2] = _json_response(200, metadata)
    responses.append(
        _json_response(
            201,
            {"client_id": "registered-client", "token_endpoint_auth_method": "none"},
        )
    )
    gateway = _Gateway(responses)
    states = _StateStore()
    service = McpOAuthService(
        settings=_settings(), gateway=gateway, state_service=states  # type: ignore[arg-type]
    )
    service._admit_start = MethodType(  # type: ignore[method-assign]
        lambda _self, **_kwargs: snapshot,
        service,
    )
    service._persist_start = MethodType(  # type: ignore[method-assign]
        lambda _self, **_kwargs: _PersistedStart(
            snapshot.installation_id, 1, "new-ciphertext", False
        ),
        service,
    )
    result = service.start_authorization(
        workspace_id=snapshot.workspace_id,
        actor_id=snapshot.actor_id,
        connection_id=snapshot.connection_id,
        return_path=None,
    )
    registration_call = gateway.calls[-1]
    assert [call["method"] for call in gateway.calls] == [
        "POST",
        "GET",
        "GET",
        "POST",
    ]
    assert registration_call["method"] == "POST"
    assert registration_call["follow_redirects"] is False
    registration = json.loads(registration_call["body"])
    assert registration["application_type"] == "web"
    assert registration["redirect_uris"] == [
        "https://api.geem.example/api/connectors/oauth/mcp_remote/callback"
    ]
    assert parse_qs(urlsplit(result.authorization_url).query)["client_id"] == [
        "registered-client"
    ]
    assert states.created is not None
    assert states.created["binding"]["issuer"] == "https://auth.example.com"


def test_token_exchange_uses_pkce_and_resource_and_rejects_scope_widening() -> None:
    snapshot = _snapshot(strategy="pre_registered")
    snapshot = replace(
        snapshot,
        auth={
            "mode": "oauth",
            "strategy": "pre_registered",
            "client_id": "client-id",
            "client_secret": "client-secret",
        },
    )
    gateway = _Gateway(
        [
            _json_response(
                200,
                {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "files:read files:write",
                },
            )
        ]
    )
    service = McpOAuthService(settings=_settings(), gateway=gateway)
    binding = {
        "token_endpoint": "https://auth.example.com/token",
        "client_id": "client-id",
        "token_endpoint_auth_method": "client_secret_post",
        "redirect_uri": "https://api.geem.example/api/connectors/oauth/mcp_remote/callback",
        "resource": snapshot.resource_uri,
        "scopes": ["files:read"],
    }
    with pytest.raises(AppError) as caught:
        service._exchange_authorization_code(
            snapshot=snapshot,
            binding=binding,
            code="authorization-code",
            code_verifier="v" * 64,
        )
    assert caught.value.category == ErrorCategory.MCP_AUTH_REQUIRED
    request = gateway.calls[0]
    form = parse_qs(request["body"].decode())
    assert form["resource"] == [snapshot.resource_uri]
    assert form["code_verifier"] == ["v" * 64]
    assert form["client_secret"] == ["client-secret"]
    assert request["follow_redirects"] is False


def test_callback_issuer_required_when_advertised_and_exact_when_present() -> None:
    settings = _settings()
    with pytest.raises(AppError):
        _validate_callback_issuer(
            None,
            expected_issuer="https://auth.example.com",
            required=True,
            settings=settings,
        )
    with pytest.raises(AppError):
        _validate_callback_issuer(
            "https://attacker.example.com",
            expected_issuer="https://auth.example.com",
            required=False,
            settings=settings,
        )
    _validate_callback_issuer(
        "https://auth.example.com/",
        expected_issuer="https://auth.example.com",
        required=True,
        settings=settings,
    )


def test_bearer_challenge_parser_rejects_ambiguous_resource_metadata() -> None:
    with pytest.raises(AppError):
        _parse_bearer_challenge(
            'Bearer resource_metadata="https://one.example/prm", '
            'resource_metadata="https://two.example/prm"'
        )


def test_disconnect_revokes_refresh_token_through_gateway_without_redirect() -> None:
    gateway = _Gateway([OAuthHttpResponse(200, {}, b"")])
    service = McpOAuthService(settings=_settings(), gateway=gateway)

    assert service.revoke_best_effort(
        connection_id=uuid.uuid4(),
        auth={
            "revocation_endpoint": "https://auth.example.com/revoke",
            "client_id": "client/id",
            "client_secret": "client secret",
            "token_endpoint_auth_method": "client_secret_basic",
            "access_token": "access-token",
            "refresh_token": "refresh-token",
        },
    )

    assert len(gateway.calls) == 1
    request = gateway.calls[0]
    assert request["method"] == "POST"
    assert request["url"] == "https://auth.example.com/revoke"
    assert request["follow_redirects"] is False
    assert "refresh-token" not in request["url"]
    form = parse_qs(request["body"].decode())
    assert form == {
        "token": ["refresh-token"],
        "token_type_hint": ["refresh_token"],
    }
    assert request["headers"]["Authorization"].startswith("Basic ")


def test_disconnect_revocation_failure_is_best_effort() -> None:
    gateway = _Gateway([OAuthHttpResponse(503, {}, b"untrusted failure")])
    service = McpOAuthService(settings=_settings(), gateway=gateway)

    assert not service.revoke_best_effort(
        connection_id=uuid.uuid4(),
        auth={
            "revocation_endpoint": "https://auth.example.com/revoke",
            "client_id": "public-client",
            "token_endpoint_auth_method": "none",
            "access_token": "access-token",
        },
    )
    assert len(gateway.calls) == 1


def test_disconnect_without_revocation_endpoint_makes_no_network_request() -> None:
    gateway = _Gateway([])
    service = McpOAuthService(settings=_settings(), gateway=gateway)

    assert not service.revoke_best_effort(
        connection_id=uuid.uuid4(),
        auth={
            "client_id": "public-client",
            "token_endpoint_auth_method": "none",
            "refresh_token": "refresh-token",
        },
    )
    assert gateway.calls == []


def test_refresh_without_expiry_does_not_retain_old_token_expiry() -> None:
    updated = _apply_mcp_token_response(
        {
            "access_token": "old-access-token",
            "refresh_token": "refresh-token",
            "expires_in": 60,
            "expires_at": "2000-01-01T00:00:00+00:00",
        },
        {"access_token": "new-access-token", "token_type": "Bearer"},
    )

    assert updated["access_token"] == "new-access-token"
    assert updated["refresh_token"] == "refresh-token"
    assert "expires_in" not in updated
    assert "expires_at" not in updated


def test_new_authorization_grant_never_reuses_old_refresh_token() -> None:
    updated = _apply_mcp_token_response(
        _without_token_material(
            {
                "client_id": "client-id",
                "access_token": "old-access",
                "refresh_token": "old-refresh",
                "expires_at": "2000-01-01T00:00:00+00:00",
            }
        ),
        {"access_token": "new-access", "token_type": "Bearer"},
    )

    assert updated["client_id"] == "client-id"
    assert updated["access_token"] == "new-access"
    assert "refresh_token" not in updated


def test_rotating_refresh_loser_accepts_same_authority_short_lived_winner() -> None:
    common = {
        "issuer": "https://auth.example.com",
        "client_id": "client-id",
        "token_endpoint": "https://auth.example.com/token",
        "token_endpoint_auth_method": "none",
    }
    assert _is_concurrent_refresh_winner(
        snapshot_auth={
            **common,
            "access_token": "old-access",
            "refresh_token": "old-refresh",
        },
        snapshot_resource="https://mcp.example.com/mcp",
        current_auth={
            **common,
            "access_token": "new-access",
            "refresh_token": "rotated-refresh",
            "expires_in": 30,
        },
        current_resource="https://mcp.example.com/mcp",
    )
    assert not _is_concurrent_refresh_winner(
        snapshot_auth={**common, "access_token": "old-access"},
        snapshot_resource="https://mcp.example.com/mcp",
        current_auth={
            **common,
            "token_endpoint": "https://attacker.example.com/token",
            "access_token": "new-access",
        },
        current_resource="https://mcp.example.com/mcp",
    )


@pytest.mark.parametrize("code", ["mcp_auth_required", "mcp_insufficient_scope"])
def test_application_gateway_maps_runtime_oauth_codes_to_reauthorization(
    code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://mcp-egress-gateway/v1/mcp"
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": code,
                    "message": "untrusted challenge detail",
                    "retryable": False,
                    "outcome_unknown": False,
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    gateway = HttpMcpGatewayClient(
        _settings(mcp_egress_gateway_url="https://mcp-egress-gateway"),
        client=client,
    )
    with pytest.raises(AppError) as caught:
        gateway._post({"operation_id": "test", "operation": "discover"})
    assert caught.value.category == ErrorCategory.MCP_REAUTHORIZATION_REQUIRED
    assert "untrusted" not in caught.value.message
