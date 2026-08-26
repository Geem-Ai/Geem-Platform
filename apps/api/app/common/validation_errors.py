"""Public-safe serialization for request validation failures.

Pydantic includes the rejected input and arbitrary validator context in its
``errors()`` payload.  Echoing those fields can disclose credentials, OAuth
codes, tenant URLs, or other request-body material.  Public API responses need
only the stable error type, location, and human-readable message.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def public_validation_errors(
    errors: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return validation details without rejected values or exception context."""

    safe: list[dict[str, Any]] = []
    for error in errors:
        item: dict[str, Any] = {}
        for key in ("type", "loc", "msg"):
            if key in error:
                item[key] = error[key]
        safe.append(item)
    return safe


__all__ = ["public_validation_errors"]
