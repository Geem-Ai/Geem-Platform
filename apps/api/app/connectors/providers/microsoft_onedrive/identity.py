"""DriveItem identity helpers for Microsoft OneDrive (Phase 9E)."""

from __future__ import annotations

from app.core.errors import AppError, ErrorCategory


def compose_external_id(drive_id: str, item_id: str) -> str:
    drive = (drive_id or "").strip()
    item = (item_id or "").strip()
    if not drive or not item:
        raise AppError(
            ErrorCategory.VALIDATION,
            "drive_id and item_id are required.",
        )
    if ":" in drive:
        raise AppError(
            ErrorCategory.VALIDATION,
            "drive_id must not contain ':' separators.",
        )
    return f"{drive}:{item}"


def parse_external_id(external_id: str) -> tuple[str, str]:
    raw = (external_id or "").strip()
    if ":" not in raw:
        raise AppError(
            ErrorCategory.VALIDATION,
            "OneDrive external_id must be drive_id:item_id.",
            details={"external_id": raw or None},
        )
    drive_id, item_id = raw.split(":", 1)
    drive_id = drive_id.strip()
    item_id = item_id.strip()
    if not drive_id or not item_id:
        raise AppError(
            ErrorCategory.VALIDATION,
            "OneDrive external_id must be drive_id:item_id.",
            details={"external_id": raw},
        )
    return drive_id, item_id
