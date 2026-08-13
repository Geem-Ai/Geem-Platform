from __future__ import annotations

import pytest

from app.core.errors import AppError, ErrorCategory
from app.usage.api_activity import DEFAULT_PERIOD, normalize_api_usage_period


def test_normalize_api_usage_period_defaults_and_allows() -> None:
    assert normalize_api_usage_period(None) == DEFAULT_PERIOD
    assert normalize_api_usage_period("24h") == "24h"
    assert normalize_api_usage_period("7D") == "7d"


def test_normalize_api_usage_period_rejects_unknown() -> None:
    with pytest.raises(AppError) as exc:
        normalize_api_usage_period("year")
    assert exc.value.category == ErrorCategory.VALIDATION
