"""Unit tests for customer analytics (part D)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from novacart.analytics.common import AnalyticsError
from novacart.analytics.customers import (
    country_summary,
    customer_segment_summary,
    revenue_concentration,
    revenue_deciles,
    top_customers_by_revenue,
)


@pytest.fixture()
def customers() -> pd.DataFrame:
    """Ten purchasing customers (revenue 10..100) and one who never purchased."""
    countries = ["DE", "DE", "DE", "NL", "NL", "NL", "FR", "FR", "FR", "FR"]
    rows = []
    for index in range(10):
        revenue = float((index + 1) * 10)
        repeat = index >= 4  # the six highest spenders are repeat customers
        rows.append(
            {
                "customer_id": f"C{index + 1:02d}",
                "customer_name": f"Customer {index + 1:02d}",
                "country_code": countries[index],
                "acquisition_channel": "organic_search" if index % 2 == 0 else "paid_search",
                "has_purchased": True,
                "repeat_customer": repeat,
                "total_orders": 2 if repeat else 1,
                "total_units": int(revenue // 10),
                "total_revenue": revenue,
                "average_order_value": revenue / (2 if repeat else 1),
                "days_since_last_order": 100 - index,
            }
        )
    rows.append(
        {
            "customer_id": "C11",
            "customer_name": "Customer 11",
            "country_code": "DE",
            "acquisition_channel": "display",
            "has_purchased": False,
            "repeat_customer": False,
            "total_orders": 0,
            "total_units": 0,
            "total_revenue": 0.0,
            "average_order_value": np.nan,
            "days_since_last_order": np.nan,
        }
    )
    return pd.DataFrame(rows)


def test_country_summary_known_values(customers: pd.DataFrame) -> None:
    summary = country_summary(customers).set_index("country_code")
    assert summary.loc["FR", "revenue"] == pytest.approx(340.0)
    assert summary.loc["FR", "registered_customers"] == 4
    assert summary.loc["FR", "purchasing_customers"] == 4
    assert summary.loc["FR", "orders"] == 8
    assert summary.loc["FR", "average_customer_revenue"] == pytest.approx(85.0)
    assert summary.loc["NL", "revenue"] == pytest.approx(150.0)
    assert summary.loc["DE", "revenue"] == pytest.approx(60.0)
    assert summary.loc["DE", "registered_customers"] == 4  # includes the non-purchaser
    assert summary.loc["DE", "purchasing_customers"] == 3
    assert summary["revenue_share_pct"].sum() == pytest.approx(100.0, abs=1e-6)
    assert summary.index[0] == "FR"  # sorted by revenue desc


def test_customer_segment_summary(customers: pd.DataFrame) -> None:
    segments = customer_segment_summary(customers).set_index("segment")
    assert segments.loc["never_purchased", "customers"] == 1
    assert segments.loc["never_purchased", "revenue"] == pytest.approx(0.0)
    assert segments.loc["one_time", "customers"] == 4
    assert segments.loc["one_time", "revenue"] == pytest.approx(100.0)
    assert segments.loc["one_time", "average_customer_revenue"] == pytest.approx(25.0)
    assert segments.loc["repeat", "customers"] == 6
    assert segments.loc["repeat", "revenue"] == pytest.approx(450.0)
    assert segments.loc["repeat", "average_customer_revenue"] == pytest.approx(75.0)
    assert segments.loc["repeat", "average_orders_per_customer"] == pytest.approx(2.0)
    assert segments.loc["repeat", "revenue_share_pct"] == pytest.approx(81.8182, abs=1e-3)
    assert list(segments.index) == ["never_purchased", "one_time", "repeat"]


def test_revenue_deciles_are_equal_count_and_cumulative(customers: pd.DataFrame) -> None:
    deciles = revenue_deciles(customers)
    assert deciles["revenue_decile"].tolist() == list(range(1, 11))
    assert deciles["customers"].sum() == 10
    assert deciles["revenue"].sum() == pytest.approx(550.0)
    assert deciles.iloc[0]["revenue"] == pytest.approx(10.0)
    assert deciles.iloc[-1]["revenue"] == pytest.approx(100.0)
    assert deciles["revenue_share_pct"].sum() == pytest.approx(100.0, abs=1e-6)
    assert deciles.iloc[-1]["cumulative_revenue_share_pct"] == pytest.approx(100.0, abs=1e-6)
    assert deciles["cumulative_revenue_share_pct"].is_monotonic_increasing
    assert deciles.iloc[0]["min_customer_revenue"] == pytest.approx(10.0)
    assert deciles.iloc[0]["max_customer_revenue"] == pytest.approx(10.0)


def test_revenue_concentration(customers: pd.DataFrame) -> None:
    concentration = revenue_concentration(customers).iloc[0]
    assert concentration["purchasing_customers"] == 10
    assert concentration["total_revenue"] == pytest.approx(550.0)
    # 1% and 10% of ten customers both round up to the single highest spender.
    assert concentration["top_1pct_revenue_share_pct"] == pytest.approx(18.1818, abs=1e-3)
    assert concentration["top_10pct_revenue_share_pct"] == pytest.approx(18.1818, abs=1e-3)
    assert concentration["bottom_50pct_revenue_share_pct"] == pytest.approx(27.2727, abs=1e-3)


def test_top_customers_expose_the_metric(customers: pd.DataFrame) -> None:
    top = top_customers_by_revenue(customers, n=3)
    assert top["customer_id"].tolist() == ["C10", "C09", "C08"]
    assert top["total_revenue"].tolist() == [100.0, 90.0, 80.0]
    assert top.iloc[0]["revenue_share_pct"] == pytest.approx(18.1818, abs=1e-3)
    assert top["average_order_value"].notna().all()

    with pytest.raises(AnalyticsError):
        top_customers_by_revenue(customers, n=0)


def test_customer_analytics_handle_empty_frames(customers: pd.DataFrame) -> None:
    empty = customers.iloc[0:0]
    assert country_summary(empty).empty
    assert customer_segment_summary(empty).empty
    assert revenue_deciles(empty).empty
    assert revenue_concentration(empty).empty
    assert top_customers_by_revenue(empty, 5).empty


def test_customer_analytics_handle_no_purchasers(customers: pd.DataFrame) -> None:
    never_purchased = customers.loc[~customers["has_purchased"]]
    concentration = revenue_concentration(never_purchased)
    assert concentration.empty
    segments = customer_segment_summary(never_purchased).set_index("segment")
    assert segments.loc["never_purchased", "customers"] == 1
    assert "repeat" not in segments.index


def test_country_summary_requires_the_customer_mart_columns() -> None:
    with pytest.raises(AnalyticsError):
        country_summary(pd.DataFrame({"customer_id": ["C1"], "country_code": ["DE"]}))

