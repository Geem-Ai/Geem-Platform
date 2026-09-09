"""Deployment entrypoints must not log secret-bearing request targets."""

from __future__ import annotations

from pathlib import Path

from app.mcp.oauth import _OAUTH_CALLBACK_PATH


_API_ROOT = Path(__file__).resolve().parents[2]


def test_structured_http_observability_cannot_capture_oauth_query_material() -> None:
    # OAuth callbacks necessarily carry one-time material in their request
    # target. Repository policy tests enforce disabled Uvicorn request-line
    # logging; the replacement middleware may record only route and method.
    sensitive_target = (
        f"{_OAUTH_CALLBACK_PATH}?state=one-time-state&code=authorization-code"
    )
    middleware = (
        _API_ROOT / "app/observability/http_middleware.py"
    ).read_text(encoding="utf-8")

    assert "?state=" in sensitive_target and "&code=" in sensitive_target
    assert "query_string" not in middleware
    assert "raw_path" not in middleware
    assert "request.url" not in middleware
    assert '"http.route"' in middleware
