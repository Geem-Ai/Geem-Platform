"""Unit tests for OneDrive identity / formats / token merge / account kind."""

from __future__ import annotations

import pytest

from app.connectors.oauth_tokens import merge_token_response
from app.connectors.providers.microsoft_onedrive.formats import (
    needs_pdf_conversion,
    require_supported_mime,
)
from app.connectors.providers.microsoft_onedrive.identity import (
    compose_external_id,
    parse_external_id,
    same_drive_id,
)
from app.connectors.providers.microsoft_onedrive.picker_auth import (
    assert_picker_resource_allowed,
    classify_account_kind,
    is_personal_onedrive_host,
    resolve_picker_base_url,
)
from app.connectors.providers.microsoft_onedrive.client import (
    build_authorization_url,
)
from app.connectors.providers.microsoft_onedrive.scopes import (
    ONEDRIVE_OAUTH_PROMPT,
    PERSONAL_PICKER_BASE_URL,
    PERSONAL_PICKER_SCOPE,
    auth_tenant_for_account_kind,
    oauth_scopes_for_tenant,
    tenant_allows_personal_accounts,
)
from app.core.errors import AppError, ErrorCategory


def test_compose_parse_external_id() -> None:
    ext = compose_external_id("drive-abc", "item-xyz")
    assert ext == "drive-abc:item-xyz"
    assert parse_external_id(ext) == ("drive-abc", "item-xyz")


def test_same_drive_id_is_case_insensitive_for_msa() -> None:
    assert same_drive_id("2D1100F7D39529F3", "2d1100f7d39529f3")
    assert not same_drive_id("2D1100F7D39529F3", "aaaaaaaaaaaaaaaa")
    assert not same_drive_id("", "2D1100F7D39529F3")


def test_personal_onedrive_host_detection() -> None:
    assert is_personal_onedrive_host(drive_type="personal")
    assert is_personal_onedrive_host(
        web_url="https://my.microsoftpersonalcontent.com/personal/x/Documents"
    )
    assert is_personal_onedrive_host(web_url="https://onedrive.live.com/picker")
    assert not is_personal_onedrive_host(
        web_url="https://contoso-my.sharepoint.com/personal/user",
        drive_type="business",
    )
    # Do not treat arbitrary *.live.com hosts as OneDrive personal.
    assert not is_personal_onedrive_host(web_url="https://account.live.com/")
    assert classify_account_kind(drive_type="personal") == "personal"
    assert (
        classify_account_kind(
            web_url="https://contoso-my.sharepoint.com/personal/u",
            drive_type="business",
        )
        == "work_school"
    )
    # Explicit kind wins over conflicting drive metadata.
    assert (
        classify_account_kind(
            web_url="https://contoso-my.sharepoint.com/personal/u",
            drive_type="business",
            explicit="personal",
        )
        == "personal"
    )


def test_oauth_authorize_scopes_are_graph_only() -> None:
    """Authorize must not mix OneDrive.ReadOnly (breaks MSA token exchange)."""
    assert tenant_allows_personal_accounts("common")
    assert PERSONAL_PICKER_SCOPE not in oauth_scopes_for_tenant("common")
    assert PERSONAL_PICKER_SCOPE not in oauth_scopes_for_tenant("organizations")
    assert "Files.Read" in oauth_scopes_for_tenant("common")


def test_personal_picker_resource_allowlist() -> None:
    for resource in (
        "https://onedrive.live.com/picker",
        "https://api.onedrive.com",
        "https://api.onedrive.com/v1.0/drive",
        "https://my.microsoftpersonalcontent.com",
        "https://cid-abc.my.microsoftpersonalcontent.com/personal/x",
        "https://skyapi.onedrive.live.com",
    ):
        assert_picker_resource_allowed(
            resource=resource,
            expected_web_url=PERSONAL_PICKER_BASE_URL,
            account_kind="personal",
        )
    with pytest.raises(AppError) as exc:
        assert_picker_resource_allowed(
            resource="https://contoso-my.sharepoint.com",
            expected_web_url=PERSONAL_PICKER_BASE_URL,
            account_kind="personal",
        )
    assert (
        exc.value.category
        == ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED
    )
    with pytest.raises(AppError) as exc2:
        assert_picker_resource_allowed(
            resource="https://graph.microsoft.com",
            expected_web_url=PERSONAL_PICKER_BASE_URL,
            account_kind="personal",
        )
    assert (
        exc2.value.category
        == ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED
    )


def test_resolve_picker_base_url_personal() -> None:
    class _S:
        microsoft_onedrive_tenant = "common"

    base, state, kind = resolve_picker_base_url(
        sync_state={
            "drive_web_url": (
                "https://my.microsoftpersonalcontent.com/personal/abc/Documents"
            ),
            "drive_type": "personal",
        },
        credentials={},
        settings=_S(),  # type: ignore[arg-type]
        access_token="tok",
    )
    assert kind == "personal"
    assert base == PERSONAL_PICKER_BASE_URL
    assert state["account_kind"] == "personal"


def test_auth_tenant_personal_always_consumers() -> None:
    assert (
        auth_tenant_for_account_kind(
            account_kind="personal",
            settings_tenant="common",
            stored_auth_tenant="common",
        )
        == "consumers"
    )
    assert (
        auth_tenant_for_account_kind(
            account_kind="work_school",
            settings_tenant="organizations",
            stored_auth_tenant="consumers",
        )
        == "organizations"
    )


def test_parse_external_id_rejects_bare_item() -> None:
    with pytest.raises(AppError) as exc:
        parse_external_id("item-only")
    assert exc.value.category == ErrorCategory.VALIDATION


def test_office_needs_conversion() -> None:
    mime = require_supported_mime(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert needs_pdf_conversion(mime)
    assert not needs_pdf_conversion("application/pdf")


def test_unsupported_mime() -> None:
    with pytest.raises(AppError) as exc:
        require_supported_mime("image/png", name="x.png")
    assert (
        exc.value.category
        == ErrorCategory.MICROSOFT_ONEDRIVE_FILE_TYPE_UNSUPPORTED
    )


def test_refresh_token_preservation() -> None:
    merged = merge_token_response(
        {"refresh_token": "keep-me", "access_token": "old"},
        {"access_token": "new", "expires_in": 3600},
    )
    assert merged["refresh_token"] == "keep-me"
    assert merged["access_token"] == "new"


def test_oauth_prompt_includes_account_picker() -> None:
    assert ONEDRIVE_OAUTH_PROMPT == "select_account"
    url = build_authorization_url(
        client_id="cid",
        redirect_uri="http://localhost/cb",
        state="s",
        scopes=("Files.Read",),
        tenant="common",
    )
    assert "select_account" in url
