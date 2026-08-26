"""Deployment entrypoints must not log secret-bearing request targets."""

from __future__ import annotations

from pathlib import Path

from app.mcp.oauth import _OAUTH_CALLBACK_PATH


_REPO_ROOT = Path(__file__).resolve().parents[4]


def test_every_checked_in_api_launch_disables_uvicorn_request_line_logging() -> None:
    launch_files = (
        _REPO_ROOT / "apps/api/Dockerfile",
        _REPO_ROOT / "infra/docker-compose.yml",
        _REPO_ROOT / "infra/docker-compose.tunnel.yml",
        _REPO_ROOT / "docs/deployment.md",
        _REPO_ROOT / "docs/development.md",
    )

    for path in launch_files:
        text = path.read_text(encoding="utf-8")
        assert "uvicorn" in text and "app.main:app" in text, path
        assert "--no-access-log" in text, path


def test_structured_http_observability_cannot_capture_oauth_query_material() -> None:
    # OAuth callbacks necessarily carry one-time material in their request
    # target. Uvicorn request-line logging is disabled above; the replacement
    # structured middleware may record only the route template and method.
    sensitive_target = (
        f"{_OAUTH_CALLBACK_PATH}?state=one-time-state&code=authorization-code"
    )
    middleware = (
        _REPO_ROOT / "apps/api/app/observability/http_middleware.py"
    ).read_text(encoding="utf-8")

    assert "?state=" in sensitive_target and "&code=" in sensitive_target
    assert "query_string" not in middleware
    assert "raw_path" not in middleware
    assert "request.url" not in middleware
    assert '"http.route"' in middleware
