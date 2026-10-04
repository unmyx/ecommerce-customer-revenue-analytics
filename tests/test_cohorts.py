"""Unit tests for cohort retention (part B)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from novacart.analytics.cohorts import (
    cohort_analysis,
    customer_cohorts,
    validate_retention,
)
from novacart.analytics.common import AnalyticsError


@pytest.fixture()
def orders() -> pd.DataFrame:
    """Three cohorts with a known retention pattern.

    A (2026-01): A1 orders in Jan, Feb, Mar; A2 only in Jan.
    B (2026-02): B1 orders in Feb and Mar.
    C (2026-03): C1, C2, C3 order only in March.
    """
    rows = [
        ("O1", "A1", "2026-01-05", 100.0),
        ("O2", "A2", "2026-01-20", 50.0),
        ("O3", "A1", "2026-02-10", 40.0),
        ("O4", "B1", "2026-02-15", 200.0),
        ("O5", "A1", "2026-03-10", 30.0),
        ("O6", "B1", "2026-03-20", 150.0),
        ("O7", "C1", "2026-03-02", 60.0),
        ("O8", "C2", "2026-03-03", 60.0),
        ("O9", "C3", "2026-03-04", 60.0),
    ]
    return pd.DataFrame(
        [
            {
                "order_id": order_id,
                "customer_id": customer_id,
                "order_month": pd.Timestamp(order_date).replace(day=1),
                "order_date": pd.Timestamp(order_date),
                "is_revenue_recognised": True,
                "recognised_net_revenue": revenue,
                "recognised_units": 1,
            }
            for order_id, customer_id, order_date, revenue in rows
        ]
    )


def test_customer_cohorts_assigns_first_purchase_month(orders: pd.DataFrame) -> None:
    cohorts = customer_cohorts(orders, analysis_end_date="2026-06-30").set_index("customer_id")
    assert cohorts.loc["A1", "cohort_month"] == pd.Timestamp("2026-01-01")
    assert cohorts.loc["A2", "cohort_month"] == pd.Timestamp("2026-01-01")
    assert cohorts.loc["B1", "cohort_month"] == pd.Timestamp("2026-02-01")
    assert cohorts.loc["C3", "cohort_month"] == pd.Timestamp("2026-03-01")
    assert cohorts.loc["A1", "cohort_index"] == 0
    assert cohorts.loc["B1", "cohort_index"] == 1
    assert cohorts.loc["C1", "cohort_index"] == 2
    assert cohorts.loc["A1", "months_observed"] == 6
    assert cohorts.loc["B1", "months_observed"] == 5
    assert cohorts.loc["C1", "months_observed"] == 4
    assert cohorts.loc["A1", "repeat_customers"] == 1
    assert cohorts.loc["A2", "repeat_customers"] == 0


def test_cohort_sizes_and_revenue(orders: pd.DataFrame) -> None:
    analysis = cohort_analysis(orders, analysis_end_date="2026-06-30")
    sizes = analysis.sizes.set_index("cohort_month")
    assert sizes.loc["2026-01-01", "cohort_size"] == 2
    assert sizes.loc["2026-02-01", "cohort_size"] == 1
    assert sizes.loc["2026-03-01", "cohort_size"] == 3
    assert sizes["cohort_size"].sum() == 6
    assert sizes.loc["2026-01-01", "total_revenue"] == pytest.approx(220.0)
    assert sizes.loc["2026-02-01", "total_revenue"] == pytest.approx(350.0)
    assert sizes.loc["2026-03-01", "total_revenue"] == pytest.approx(180.0)
    assert sizes.loc["2026-01-01", "revenue_per_customer"] == pytest.approx(110.0)
    assert sizes.loc["2026-01-01", "repeat_customer_rate"] == pytest.approx(0.5)


def test_retention_matrix_month_zero_is_the_baseline(orders: pd.DataFrame) -> None:
    analysis = cohort_analysis(orders, analysis_end_date="2026-06-30")
    matrix = analysis.retention_matrix

    assert list(matrix.index) == [
        pd.Timestamp("2026-01-01"),
        pd.Timestamp("2026-02-01"),
        pd.Timestamp("2026-03-01"),
    ]
    assert matrix[0].tolist() == [1.0, 1.0, 1.0]
    assert matrix.loc[pd.Timestamp("2026-01-01"), 1] == pytest.approx(0.5)
    assert matrix.loc[pd.Timestamp("2026-01-01"), 2] == pytest.approx(0.5)
    assert matrix.loc[pd.Timestamp("2026-01-01"), 3] == pytest.approx(0.0)
    assert matrix.loc[pd.Timestamp("2026-02-01"), 1] == pytest.approx(1.0)
    assert matrix.loc[pd.Timestamp("2026-03-01"), 1] == pytest.approx(0.0)

    # Unobservable months stay NaN rather than being reported as zero retention.
    assert list(matrix.columns) == [0, 1, 2, 3, 4, 5]
    assert np.isnan(matrix.loc[pd.Timestamp("2026-03-01"), 4])
    assert np.isnan(matrix.loc[pd.Timestamp("2026-03-01"), 5])
    assert matrix.loc[pd.Timestamp("2026-01-01")].notna().sum() == 6
    assert matrix.loc[pd.Timestamp("2026-03-01")].notna().sum() == 4


def test_retention_long_table_invariants(orders: pd.DataFrame) -> None:
    analysis = cohort_analysis(orders, analysis_end_date="2026-06-30")
    retention = analysis.retention

    validate_retention(retention, analysis.sizes)
    assert retention["retention_rate"].between(0, 1).all()
    assert retention["retained_customers"].ge(0).all()
    assert (
        retention.groupby("cohort_index")["cohort_size"].nunique() == 1
    ).all()
    first = retention.loc[retention["month_offset"] == 0]
    assert (first["retained_customers"] == first["cohort_size"]).all()
    assert set(retention["month_offset"]) == set(range(6))


def test_cohort_revenue_is_cumulative(orders: pd.DataFrame) -> None:
    analysis = cohort_analysis(orders, analysis_end_date="2026-06-30")
    revenue = analysis.revenue
    cohort_a = revenue.loc[revenue["cohort_month"] == pd.Timestamp("2026-01-01")]
    assert cohort_a["revenue"].tolist()[:3] == [150.0, 40.0, 30.0]
    assert cohort_a["cumulative_revenue"].tolist()[:3] == [150.0, 190.0, 220.0]
    assert cohort_a.iloc[0]["revenue_per_cohort_customer"] == pytest.approx(75.0)
    assert revenue["revenue"].sum() == pytest.approx(750.0)


def test_cohort_outputs_are_deterministic(orders: pd.DataFrame) -> None:
    first = cohort_analysis(orders, analysis_end_date="2026-06-30")
    second = cohort_analysis(orders.sample(frac=1.0, random_state=11), analysis_end_date="2026-06-30")
    pd.testing.assert_frame_equal(first.sizes, second.sizes)
    pd.testing.assert_frame_equal(first.retention, second.retention)
    pd.testing.assert_frame_equal(first.revenue, second.revenue)
    pd.testing.assert_frame_equal(first.retention_matrix, second.retention_matrix)


def test_validate_retention_rejects_impossible_tables(orders: pd.DataFrame) -> None:
    analysis = cohort_analysis(orders, analysis_end_date="2026-06-30")
    broken = analysis.retention.copy()
    broken.loc[0, "retention_rate"] = 1.5
    with pytest.raises(ValueError):
        validate_retention(broken, analysis.sizes)

    broken = analysis.retention.copy()
    broken.loc[broken["month_offset"] == 0, "retention_rate"] = 0.8
    with pytest.raises(ValueError):
        validate_retention(broken, analysis.sizes)


def test_cohort_analysis_handles_empty_input(orders: pd.DataFrame) -> None:
    analysis = cohort_analysis(orders.iloc[0:0], analysis_end_date="2026-06-30")
    assert analysis.sizes.empty
    assert analysis.retention.empty
    assert analysis.revenue.empty
    assert analysis.retention_matrix.empty

    with pytest.raises(AnalyticsError):
        cohort_analysis(pd.DataFrame({"customer_id": ["C1"]}))

