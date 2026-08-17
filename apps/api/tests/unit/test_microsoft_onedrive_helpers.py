"""Unit tests for OneDrive identity / formats / token merge."""

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
)
from app.core.errors import AppError, ErrorCategory


def test_compose_parse_external_id() -> None:
    ext = compose_external_id("drive-abc", "item-xyz")
    assert ext == "drive-abc:item-xyz"
    assert parse_external_id(ext) == ("drive-abc", "item-xyz")


def test_personal_onedrive_host_detection() -> None:
    from app.connectors.providers.microsoft_onedrive.picker_auth import (
        assert_work_school_picker_supported,
        is_personal_onedrive_host,
    )

    assert is_personal_onedrive_host(drive_type="personal")
    assert is_personal_onedrive_host(
        web_url="https://my.microsoftpersonalcontent.com/personal/x/Documents"
    )
    assert not is_personal_onedrive_host(
        web_url="https://contoso-my.sharepoint.com/personal/user",
        drive_type="business",
    )
    with pytest.raises(AppError) as exc:
        assert_work_school_picker_supported(
            web_url="https://onedrive.live.com/picker",
            drive_type=None,
        )
    assert (
        exc.value.category
        == ErrorCategory.MICROSOFT_ONEDRIVE_DRIVE_NOT_SUPPORTED
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
