"""Unit tests for revenue, order and KPI calculations (parts A and E)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from novacart.analytics.common import AnalyticsError
from novacart.analytics.kpis import business_kpi_snapshot, kpi_display
from novacart.analytics.revenue import revenue_by_dimension, revenue_summary


@pytest.fixture()
def orders() -> pd.DataFrame:
    """Four orders, one of which is a refund and must not count as revenue."""
    return pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3", "O4"],
            "customer_id": ["C1", "C1", "C2", "C3"],
            "order_date": pd.to_datetime(
                ["2026-01-05", "2026-01-20", "2026-02-02", "2026-02-10"]
            ),
            "order_month": pd.to_datetime(["2026-01-01", "2026-01-01", "2026-02-01", "2026-02-01"]),
            "sales_channel": ["web", "mobile_app", "web", "marketplace"],
            "is_revenue_recognised": [True, True, False, True],
            "recognised_net_revenue": [100.0, 50.0, 999.0, 80.0],
            "recognised_units": [2, 1, 9, 3],
        }
    )


@pytest.fixture()
def customers() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3"],
            "has_purchased": [True, False, True],
            "repeat_customer": [True, False, False],
            "total_orders": [2, 0, 1],
            "total_units": [3, 0, 3],
            "total_revenue": [150.0, 0.0, 80.0],
        }
    )


def test_revenue_summary_known_values(orders: pd.DataFrame) -> None:
    summary = revenue_summary(orders).iloc[0]
    assert summary["total_revenue"] == pytest.approx(230.0)
    assert summary["total_orders"] == 3
    assert summary["total_units"] == 6
    assert summary["unique_customers"] == 2
    assert summary["average_order_value"] == pytest.approx(76.67)
    assert summary["average_units_per_order"] == pytest.approx(2.0)
    assert summary["orders_per_customer"] == pytest.approx(1.5)
    assert summary["repeat_customers"] == 1
    assert summary["one_time_customers"] == 1
    assert summary["repeat_customer_rate"] == pytest.approx(0.5)
    assert summary["revenue_per_customer"] == pytest.approx(115.0)
    assert str(summary["period_start"]) == "2026-01-05"
    assert str(summary["period_end"]) == "2026-02-10"


def test_revenue_summary_excludes_non_recognised_orders(orders: pd.DataFrame) -> None:
    revenue_with_refund = revenue_summary(orders).iloc[0]["total_revenue"]
    without_refund = revenue_summary(orders.drop(index=2)).iloc[0]["total_revenue"]
    assert revenue_with_refund == pytest.approx(without_refund)
    assert revenue_with_refund == pytest.approx(orders.loc[orders["is_revenue_recognised"], "recognised_net_revenue"].sum())


def test_revenue_summary_on_empty_frame_returns_zeros_not_errors(orders: pd.DataFrame) -> None:
    summary = revenue_summary(orders.iloc[0:0]).iloc[0]
    assert summary["total_revenue"] == 0.0
    assert summary["total_orders"] == 0
    assert summary["repeat_customers"] == 0
    assert np.isnan(summary["average_order_value"])
    assert np.isnan(summary["repeat_customer_rate"])
    assert pd.isna(summary["period_start"])


def test_revenue_summary_requires_a_customer_column() -> None:
    with pytest.raises(AnalyticsError):
        revenue_summary(pd.DataFrame({"order_id": ["O1"], "recognised_net_revenue": [1.0]}))


def test_revenue_summary_accepts_frames_without_recognition_flag() -> None:
    frame = pd.DataFrame(
        {
            "order_id": ["O1", "O2"],
            "customer_id": ["C1", "C2"],
            "order_date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
            "net_revenue": [10.0, 20.0],
            "total_units": [1, 1],
        }
    )
    summary = revenue_summary(frame).iloc[0]
    assert summary["total_revenue"] == pytest.approx(30.0)
    assert summary["total_orders"] == 2


def test_revenue_by_dimension_groups_and_shares(orders: pd.DataFrame) -> None:
    by_channel = revenue_by_dimension(orders, "sales_channel")
    assert by_channel["sales_channel"].tolist() == ["web", "marketplace", "mobile_app"]
    web = by_channel.set_index("sales_channel").loc["web"]
    assert web["revenue"] == pytest.approx(100.0)
    assert web["orders"] == 1
    assert web["customers"] == 1
    assert web["average_order_value"] == pytest.approx(100.0)
    assert by_channel["revenue_share_pct"].sum() == pytest.approx(100.0, abs=1e-6)


def test_business_kpi_snapshot_uses_customer_mart(
    orders: pd.DataFrame, customers: pd.DataFrame
) -> None:
    snapshot = business_kpi_snapshot(orders, customers).iloc[0]
    assert snapshot["total_revenue"] == pytest.approx(230.0)
    assert snapshot["registered_customers"] == 3
    assert snapshot["unique_customers"] == 2
    assert snapshot["repeat_customers"] == 1
    assert snapshot["one_time_customers"] == 1
    assert snapshot["repeat_customer_rate"] == pytest.approx(0.5)
    assert snapshot["revenue_per_customer"] == pytest.approx(115.0)
    assert snapshot["revenue_per_registered_customer"] == pytest.approx(76.67)
    assert snapshot["days_in_period"] == 37


def test_business_kpi_snapshot_without_customers_falls_back_to_orders(
    orders: pd.DataFrame,
) -> None:
    snapshot = business_kpi_snapshot(orders, pd.DataFrame()).iloc[0]
    assert snapshot["repeat_customer_rate"] == pytest.approx(0.5)
    assert snapshot["registered_customers"] == 0
    assert np.isnan(snapshot["revenue_per_registered_customer"])


def test_kpi_display_presents_every_metric(orders: pd.DataFrame, customers: pd.DataFrame) -> None:
    display = kpi_display(business_kpi_snapshot(orders, customers))
    assert list(display.columns) == ["metric", "value"]
    metrics = dict(zip(display["metric"], display["value"], strict=True))
    assert metrics["Total revenue"] == "EUR 230.00"
    assert metrics["Total orders"] == "3"
    assert metrics["Repeat customer rate"] == "50.0%"

