"""Unit tests — Google Drive MIME / export helpers (Phase 9D)."""

from __future__ import annotations

import pytest

from app.connectors.providers.google_drive.formats import (
    export_mime_for,
    is_google_workspace_doc,
    is_supported_mime,
    require_supported_mime,
    suggested_filename,
)
from app.connectors.providers.google_drive.scopes import (
    DRIVE_FILE_SCOPE,
    DRIVE_READONLY_SCOPE,
    requires_reauthorization,
    scopes_for_mode,
)
from app.core.errors import AppError, ErrorCategory


def test_supported_mimes() -> None:
    assert is_supported_mime("application/pdf")
    assert is_supported_mime("text/plain")
    assert is_supported_mime("text/markdown")
    assert is_supported_mime("application/vnd.google-apps.document")
    assert not is_supported_mime("application/vnd.google-apps.spreadsheet")
    assert not is_supported_mime("application/vnd.google-apps.presentation")
    assert not is_supported_mime("image/png")


def test_require_unsupported_raises() -> None:
    with pytest.raises(AppError) as exc:
        require_supported_mime("application/vnd.google-apps.spreadsheet")
    assert exc.value.category == ErrorCategory.GOOGLE_DRIVE_FILE_TYPE_UNSUPPORTED


def test_export_and_filename() -> None:
    assert is_google_workspace_doc("application/vnd.google-apps.document")
    assert export_mime_for("application/vnd.google-apps.document") == "text/markdown"
    assert suggested_filename("Report", "application/pdf") == "Report.pdf"
    assert suggested_filename("Notes", "application/vnd.google-apps.document").endswith(
        ".md"
    )


def test_scopes_for_mode() -> None:
    selected = scopes_for_mode("selected_files")
    assert DRIVE_FILE_SCOPE in selected
    assert "openid" in selected
    readonly = scopes_for_mode("readonly")
    assert DRIVE_READONLY_SCOPE in readonly
    assert requires_reauthorization([], "selected_files")
    assert not requires_reauthorization(selected, "selected_files")
    assert requires_reauthorization(selected, "readonly")
