"""Unit tests for daily, weekly and monthly time series (part B)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from novacart.analytics.common import AnalyticsError
from novacart.analytics.trends import (
    add_month_over_month,
    add_rolling_metrics,
    daily_metrics,
    monthly_metrics,
    weekly_metrics,
)


@pytest.fixture()
def orders() -> pd.DataFrame:
    """Four orders across two months; O3 is a refund and must be excluded."""
    return pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3", "O4"],
            "customer_id": ["C1", "C1", "C2", "C3"],
            "order_date": pd.to_datetime(
                ["2026-01-05", "2026-01-20", "2026-02-02", "2026-02-10"]
            ),
            "is_revenue_recognised": [True, True, False, True],
            "recognised_net_revenue": [100.0, 50.0, 999.0, 80.0],
            "recognised_units": [2, 1, 9, 3],
        }
    )


def test_daily_metrics_complete_the_calendar(orders: pd.DataFrame) -> None:
    daily = daily_metrics(orders)
    assert len(daily) == 37  # 2026-01-05 .. 2026-02-10 inclusive
    assert daily["order_date"].is_monotonic_increasing

    by_date = daily.set_index("order_date")
    assert by_date.loc["2026-01-05", "revenue"] == pytest.approx(100.0)
    assert by_date.loc["2026-01-05", "orders_recognised"] == 1
    assert by_date.loc["2026-01-05", "purchasing_customers"] == 1
    assert by_date.loc["2026-01-05", "average_order_value"] == pytest.approx(100.0)
    assert by_date.loc["2026-01-05", "average_units_per_order"] == pytest.approx(2.0)

    # A day with no recognised orders exists and carries zeros, not a missing row.
    assert by_date.loc["2026-01-06", "revenue"] == pytest.approx(0.0)
    assert by_date.loc["2026-01-06", "orders_recognised"] == 0
    assert np.isnan(by_date.loc["2026-01-06", "average_order_value"])

    # The refunded order is excluded from revenue and from the order count.
    assert by_date.loc["2026-02-02", "orders_recognised"] == 0
    assert by_date.loc["2026-02-02", "revenue"] == pytest.approx(0.0)
    assert daily["revenue"].sum() == pytest.approx(230.0)
    assert daily["orders_recognised"].sum() == 3


def test_daily_metrics_calendar_labels(orders: pd.DataFrame) -> None:
    daily = daily_metrics(orders)
    first = daily.iloc[0]
    assert first["year"] == 2026
    assert first["month"] == 1
    assert first["year_month"] == "2026-01"
    assert first["iso_year_week"] == "2026-W02"
    assert first["day_name"] == "Monday"
    assert bool(first["is_weekend"]) is False
    assert bool(daily.set_index("order_date").loc["2026-01-10", "is_weekend"]) is True


def test_daily_metrics_can_skip_calendar_completion(orders: pd.DataFrame) -> None:
    sparse = daily_metrics(orders, complete_calendar=False)
    assert len(sparse) == 3
    assert sparse["revenue"].tolist() == [100.0, 50.0, 80.0]


def test_weekly_metrics_use_monday_weeks(orders: pd.DataFrame) -> None:
    weekly = weekly_metrics(orders)
    assert len(weekly) == 6  # Monday weeks from 2026-01-05 to 2026-02-09
    assert weekly["week_start"].dt.weekday.tolist() == [0] * len(weekly)

    weeks = weekly.set_index("week_start")
    assert weeks.loc["2026-01-05", "revenue"] == pytest.approx(100.0)
    assert weeks.loc["2026-01-19", "revenue"] == pytest.approx(50.0)
    assert weeks.loc["2026-02-09", "revenue"] == pytest.approx(80.0)
    assert weeks.loc["2026-01-05", "iso_year_week"] == "2026-W02"
    assert weeks.loc["2026-02-09", "iso_year_week"] == "2026-W07"
    assert weekly["revenue"].sum() == pytest.approx(230.0)


def test_monthly_metrics_and_month_over_month(orders: pd.DataFrame) -> None:
    monthly = add_month_over_month(monthly_metrics(orders))
    assert monthly["year_month"].tolist() == ["2026-01", "2026-02"]

    january = monthly.iloc[0]
    february = monthly.iloc[1]
    assert january["revenue"] == pytest.approx(150.0)
    assert january["orders_recognised"] == 2
    assert january["average_order_value"] == pytest.approx(75.0)
    assert january["purchasing_customers"] == 1

    assert february["revenue"] == pytest.approx(80.0)
    assert february["revenue_mom_change"] == pytest.approx(-70.0)
    assert february["revenue_mom_pct"] == pytest.approx(-0.4667, abs=1e-4)
    assert february["orders_recognised_mom_change"] == pytest.approx(-1.0)
    assert february["orders_recognised_mom_pct"] == pytest.approx(-0.5)
    assert february["average_order_value_mom_change"] == pytest.approx(5.0)
    assert february["average_order_value_mom_pct"] == pytest.approx(0.0667, abs=1e-4)

    # The first month has no predecessor: changes are NaN, not zero.
    assert pd.isna(january["revenue_mom_change"])
    assert pd.isna(january["revenue_mom_pct"])


def test_month_over_month_with_a_zero_base_month(orders: pd.DataFrame) -> None:
    frame = pd.concat(
        [
            orders,
            pd.DataFrame(
                {
                    "order_id": ["O5"],
                    "customer_id": ["C4"],
                    "order_date": pd.to_datetime(["2026-01-15"]),
                    "is_revenue_recognised": [True],
                    "recognised_net_revenue": [40.0],
                    "recognised_units": [1],
                }
            ),
        ],
        ignore_index=True,
    )
    # 2026-03 has no recognised orders at all, so it is filled with zeros.
    frame.loc[len(frame)] = {
        "order_id": "O6",
        "customer_id": "C5",
        "order_date": pd.Timestamp("2026-03-05"),
        "is_revenue_recognised": False,
        "recognised_net_revenue": 500.0,
        "recognised_units": 5,
    }
    monthly = add_month_over_month(monthly_metrics(frame))
    assert monthly["year_month"].tolist() == ["2026-01", "2026-02", "2026-03"]
    march = monthly.iloc[2]
    assert march["revenue"] == pytest.approx(0.0)
    assert march["revenue_mom_change"] == pytest.approx(-80.0)
    assert march["revenue_mom_pct"] == pytest.approx(-1.0)


def test_month_over_month_reports_nan_when_previous_month_is_zero(orders: pd.DataFrame) -> None:
    monthly = pd.DataFrame(
        {
            "month_start": pd.to_datetime(["2026-01-01", "2026-02-01"]),
            "revenue": [0.0, 500.0],
            "orders_recognised": [0, 10],
            "average_order_value": [np.nan, 50.0],
        }
    )
    result = add_month_over_month(monthly)
    assert result.iloc[1]["revenue_mom_change"] == pytest.approx(500.0)
    assert np.isnan(result.iloc[1]["revenue_mom_pct"])


def test_rolling_metrics_are_trailing_windows(orders: pd.DataFrame) -> None:
    daily = add_rolling_metrics(daily_metrics(orders))
    indexed = daily.set_index("order_date")

    assert indexed.loc["2026-01-05", "revenue_rolling_7d"] == pytest.approx(100.0)
    assert indexed.loc["2026-01-05", "orders_rolling_7d"] == 1
    # 2026-01-20 is 15 days after the first order: outside the 7-day window.
    assert indexed.loc["2026-01-20", "revenue_rolling_7d"] == pytest.approx(50.0)
    # The refund on 2026-02-02 never enters a rolling window.
    assert indexed.loc["2026-02-02", "revenue_rolling_7d"] == pytest.approx(0.0)
    assert indexed.loc["2026-02-10", "revenue_rolling_7d"] == pytest.approx(80.0)
    # The 30-day window starting 2026-01-12 still contains the mid-January order.
    assert indexed.loc["2026-02-10", "revenue_rolling_30d"] == pytest.approx(130.0)
    assert indexed.loc["2026-01-20", "revenue_rolling_30d"] == pytest.approx(150.0)
    assert daily["orders_rolling_7d"].dtype == "int64"


def test_trend_functions_handle_empty_input(orders: pd.DataFrame) -> None:
    empty = orders.iloc[0:0]
    assert daily_metrics(empty).empty
    assert weekly_metrics(empty).empty
    monthly = monthly_metrics(empty)
    assert monthly.empty
    assert list(monthly.columns) == [
        "month_start",
        "year_month",
        "year",
        "quarter",
        "month",
        "month_name",
        "orders_recognised",
        "purchasing_customers",
        "units",
        "revenue",
        "average_order_value",
        "average_units_per_order",
    ]


def test_trend_functions_require_order_date() -> None:
    with pytest.raises(AnalyticsError):
        daily_metrics(pd.DataFrame({"customer_id": ["C1"], "recognised_net_revenue": [1.0]}))

