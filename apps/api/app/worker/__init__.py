from __future__ import annotations

from typing import Any

__all__ = ["celery_app"]


def __getattr__(name: str) -> Any:
    """Preserve the public worker app without loading it for Beat submodules."""

    if name != "celery_app":
        raise AttributeError(name)
    from app.worker.celery_app import celery_app

    return celery_app
