"""MinIO object keys for chat attachments."""

from __future__ import annotations

import uuid


def chat_attachment_storage_key(
    workspace_id: uuid.UUID | str,
    attachment_id: uuid.UUID | str,
    *,
    extension: str,
) -> str:
    """Canonical key — never embed the user-supplied filename in the path."""
    ext = (extension or "").lstrip(".").lower() or "bin"
    # Allow only short alphanumeric extensions.
    safe_ext = "".join(c for c in ext if c.isalnum())[:12] or "bin"
    return f"workspaces/{workspace_id}/chat-attachments/{attachment_id}/original.{safe_ext}"
