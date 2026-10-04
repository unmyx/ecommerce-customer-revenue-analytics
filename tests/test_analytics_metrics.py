"""Unit tests for the shared metric helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from novacart.analytics.common import (
    AnalyticsError,
    format_compact_currency,
    format_count,
    format_currency,
    format_percent,
    percentage_change,
    recognised,
    require_columns,
    resolve_column,
    rolling_sum,
    safe_divide,
)


def test_safe_divide_handles_zero_and_missing_denominators() -> None:
    assert safe_divide(10, 4) == pytest.approx(2.5)
    assert np.isnan(safe_divide(10, 0))
    assert np.isnan(safe_divide(0, 0))
    assert np.isnan(safe_divide(None, 5))

    series = safe_divide(pd.Series([10.0, 10.0]), pd.Series([2.0, 0.0]))
    assert series[0] == pytest.approx(5.0)
    assert np.isnan(series[1])


def test_percentage_change_uses_absolute_base_and_guards_zero() -> None:
    assert percentage_change(150, 100) == pytest.approx(0.5)
    assert percentage_change(50, 100) == pytest.approx(-0.5)
    assert percentage_change(100, -100) == pytest.approx(2.0)
    assert np.isnan(percentage_change(100, 0))
    assert np.isnan(percentage_change(100, float("nan")))

    result = percentage_change(pd.Series([100.0, 80.0]), pd.Series([80.0, 0.0]))
    assert result[0] == pytest.approx(0.25)
    assert np.isnan(result[1])


def test_rolling_sum_is_trailing_and_includes_current_period() -> None:
    series = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    result = rolling_sum(series, 7)
    assert result.iloc[0] == pytest.approx(1.0)  # min_periods = 1
    assert result.iloc[6] == pytest.approx(7.0)
    assert result.iloc[7] == pytest.approx(7.0)  # oldest point drops out

    with pytest.raises(AnalyticsError):
        rolling_sum(series, 0)


def test_rolling_sum_respects_gaps_in_the_input() -> None:
    series = pd.Series([100.0] + [0.0] * 5 + [10.0])
    result = rolling_sum(series, 7)
    assert result.iloc[-1] == pytest.approx(110.0)
    # A 7-day window ending on the last row starts at index 1, so the 100 is out of scope.
    assert rolling_sum(series, 2).iloc[-1] == pytest.approx(10.0)


def test_recognised_filters_completed_rows_but_keeps_plain_frames() -> None:
    frame = pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3"],
            "is_revenue_recognised": [True, False, True],
            "recognised_net_revenue": [10.0, 99.0, 30.0],
        }
    )
    filtered = recognised(frame)
    assert filtered["order_id"].tolist() == ["O1", "O3"]

    plain = frame.drop(columns=["is_revenue_recognised"])
    assert recognised(plain)["order_id"].tolist() == ["O1", "O2", "O3"]


def test_require_and_resolve_columns_raise_informative_errors() -> None:
    frame = pd.DataFrame({"a": [1], "net_revenue": [1.0]})
    require_columns(frame, ("a",), "test")
    with pytest.raises(AnalyticsError) as excinfo:
        require_columns(frame, ("b",), "test purpose")
    assert "test purpose" in str(excinfo.value)

    assert resolve_column(frame, ("recognised_net_revenue", "net_revenue"), "test") == "net_revenue"
    with pytest.raises(AnalyticsError):
        resolve_column(frame, ("missing",), "test")


def test_formatting_helpers_are_business_readable() -> None:
    assert format_currency(1234.5) == "EUR 1,234.50"
    assert format_currency(None) == "n/a"
    assert format_compact_currency(15_873_819.08) == "EUR 15.87m"
    assert format_compact_currency(250_000) == "EUR 250.00k"
    assert format_compact_currency(999.5) == "EUR 999.50"
    assert format_count(84_263) == "84,263"
    assert format_count(None) == "n/a"
    assert format_percent(0.5716) == "57.2%"
    assert format_percent(float("nan")) == "n/a"

