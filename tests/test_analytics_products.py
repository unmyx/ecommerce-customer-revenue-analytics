"""Unit tests for product and category analytics (part C)."""

from __future__ import annotations

import pandas as pd
import pytest

from novacart.analytics.common import AnalyticsError
from novacart.analytics.products import (
    DECLINE_MIN_PRIOR_UNITS,
    category_summary,
    declining_products,
    product_summary,
    top_products_by_revenue,
    top_products_by_units,
)


@pytest.fixture()
def lines() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_id": ["O1", "O1", "O2", "O2", "O3"],
            "customer_id": ["C1", "C1", "C2", "C2", "C3"],
            "order_date": pd.to_datetime(
                ["2026-06-01", "2026-06-01", "2026-07-01", "2026-07-01", "2026-08-01"]
            ),
            "product_id": ["P1", "P2", "P1", "P3", "P1"],
            "product_name": ["Alpha", "Beta", "Alpha", "Gamma", "Alpha"],
            "brand": ["BrandA", "BrandB", "BrandA", "BrandC", "BrandA"],
            "category": ["Electronics", "Home", "Electronics", "Fashion", "Electronics"],
            "quantity": [1, 2, 1, 1, 1],
            "recognised_units": [1, 2, 1, 1, 1],
            "recognised_line_net_revenue": [100.0, 50.0, 120.0, 30.0, 500.0],
            "is_revenue_recognised": [True, True, True, True, False],
        }
    )


def test_category_summary_known_values(lines: pd.DataFrame) -> None:
    summary = category_summary(lines).set_index("category")
    assert summary["revenue"].sum() == pytest.approx(300.0)
    assert summary.loc["Electronics", "revenue"] == pytest.approx(220.0)
    assert summary.loc["Electronics", "units"] == 2
    assert summary.loc["Electronics", "orders"] == 2
    assert summary.loc["Electronics", "customers"] == 2
    assert summary.loc["Electronics", "average_selling_price"] == pytest.approx(110.0)
    assert summary.loc["Home", "revenue"] == pytest.approx(50.0)
    assert summary.loc["Fashion", "revenue"] == pytest.approx(30.0)
    # Refunded order O3 is excluded, so Electronics revenue is 220 rather than 720.
    assert summary.loc["Electronics", "revenue_share_pct"] == pytest.approx(73.3333, abs=1e-3)
    assert summary["revenue_share_pct"].sum() == pytest.approx(100.0, abs=1e-6)
    assert summary.index[0] == "Electronics"  # sorted by revenue desc


def test_product_summary_known_values(lines: pd.DataFrame) -> None:
    summary = product_summary(lines).set_index("product_id")
    assert summary.loc["P1", "revenue"] == pytest.approx(220.0)
    assert summary.loc["P1", "units"] == 2
    assert summary.loc["P1", "orders"] == 2
    assert summary.loc["P1", "customers"] == 2
    assert summary.loc["P1", "average_selling_price"] == pytest.approx(110.0)
    assert summary.loc["P1", "product_name"] == "Alpha"
    assert summary.loc["P1", "brand"] == "BrandA"
    assert summary.loc["P1", "category"] == "Electronics"
    assert summary.loc["P2", "revenue"] == pytest.approx(50.0)
    assert summary["revenue_share_pct"].sum() == pytest.approx(100.0, abs=1e-6)


def test_top_products_use_the_requested_metric_and_break_ties_by_id(
    lines: pd.DataFrame,
) -> None:
    products = product_summary(lines)
    by_revenue = top_products_by_revenue(products, 2)
    assert by_revenue["product_id"].tolist() == ["P1", "P2"]

    by_units = top_products_by_units(products, 2)
    assert by_units["product_id"].tolist() == ["P1", "P2"]
    assert by_units["units"].tolist() == [2, 2]  # tie broken by product_id ascending

    with pytest.raises(AnalyticsError):
        top_products_by_revenue(products, 0)


def test_category_summary_on_empty_frame(lines: pd.DataFrame) -> None:
    summary = category_summary(lines.iloc[0:0])
    assert summary.empty
    assert "average_selling_price" in summary.columns


@pytest.fixture()
def declining_lines() -> pd.DataFrame:
    """Two non-overlapping 90-day windows ending 2026-06-30.

    prior  : 2026-01-02 .. 2026-04-01
    recent : 2026-04-02 .. 2026-06-30
    """
    rows = [
        # P1: 20 units -> 5 units, a 75% decline, above the minimum baseline.
        ("P1", "2026-01-10", 20),
        ("P1", "2026-05-10", 5),
        # P2: 12 units -> 11 units, a small decline that must not be flagged.
        ("P2", "2026-02-10", 12),
        ("P2", "2026-05-10", 11),
        # P3: too few units in the prior window to judge.
        ("P3", "2026-02-10", 5),
        ("P3", "2026-05-10", 0),
        # P4: 30 units -> 0 units, a total collapse.
        ("P4", "2026-03-01", 30),
        # Boundary products: 2026-04-01 counts as prior, 2026-04-02 as recent.
        ("P5", "2026-04-01", 15),
        ("P5", "2026-04-02", 1),
    ]
    frame = pd.DataFrame(
        [
            {
                "order_id": f"O{index}",
                "customer_id": f"C{index}",
                "order_date": pd.Timestamp(order_date),
                "product_id": product_id,
                "product_name": f"Product {product_id}",
                "category": "Test",
                "recognised_units": units,
                "recognised_line_net_revenue": float(units) * 10.0,
                "is_revenue_recognised": True,
            }
            for index, (product_id, order_date, units) in enumerate(rows, start=1)
        ]
    )
    return frame.loc[frame["recognised_units"] > 0].reset_index(drop=True)


def test_declining_products_rule(declining_lines: pd.DataFrame) -> None:
    result = declining_products(declining_lines, as_of="2026-06-30").set_index("product_id")

    assert "P3" not in result.index  # below the minimum prior baseline

    assert result.loc["P1", "prior_units"] == 20
    assert result.loc["P1", "recent_units"] == 5
    assert result.loc["P1", "units_change"] == -15
    assert result.loc["P1", "units_change_pct"] == pytest.approx(-0.75)
    assert bool(result.loc["P1", "is_declining"]) is True

    assert bool(result.loc["P2", "is_declining"]) is False
    assert bool(result.loc["P4", "is_declining"]) is True
    assert result.loc["P4", "units_change_pct"] == pytest.approx(-1.0)

    # Window boundaries: the 2026-04-01 sale is prior, the 2026-04-02 sale is recent.
    assert result.loc["P5", "prior_units"] == 15
    assert result.loc["P5", "recent_units"] == 1
    assert bool(result.loc["P5", "is_declining"]) is True

    assert result["prior_units"].min() >= DECLINE_MIN_PRIOR_UNITS


def test_declining_products_flags_sort_worst_first(declining_lines: pd.DataFrame) -> None:
    result = declining_products(declining_lines, as_of="2026-06-30")
    assert result.iloc[0]["is_declining"]
    assert result["is_declining"].sum() >= 2
    assert result["units_change_pct"].notna().all()


def test_declining_products_with_no_prior_window(lines: pd.DataFrame) -> None:
    # as_of at the very start of the data leaves an empty prior window.
    result = declining_products(lines, as_of="2026-06-01")
    assert result.empty
    assert "is_declining" in result.columns


def test_declining_products_validates_parameters(lines: pd.DataFrame) -> None:
    with pytest.raises(AnalyticsError):
        declining_products(lines, window_days=0)
    with pytest.raises(AnalyticsError):
        declining_products(lines, decline_share=0)

