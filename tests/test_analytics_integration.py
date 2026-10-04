"""Database-backed checks that the Python layer and the SQL layer agree.

The Milestone 3 modules recompute revenue aggregates from the analytical facts;
these tests prove that the recomputation matches the published SQL marts, which
is what makes the Python layer safe to use for reporting.

Skipped unless ``NOVACART_RUN_DB_TESTS=1``.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from novacart.analytics.common import AnalysisInputs, AnalyticsError, load_analysis_inputs
from novacart.analytics.customers import country_summary
from novacart.analytics.kpis import business_kpi_snapshot
from novacart.analytics.products import category_summary, declining_products, product_summary
from novacart.analytics.report import analyse
from novacart.analytics.revenue import revenue_summary
from novacart.analytics.trends import (
    add_rolling_metrics,
    daily_metrics,
    monthly_metrics,
)
from novacart.settings import ConfigurationError, load_database_settings

pytestmark = pytest.mark.integration

MONEY_TOLERANCE = 0.01


def _settings_or_skip():
    if os.getenv("NOVACART_RUN_DB_TESTS", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("set NOVACART_RUN_DB_TESTS=1 to run database integration tests")
    try:
        return load_database_settings()
    except ConfigurationError as exc:  # pragma: no cover - environment issue
        pytest.skip(f"database configuration unavailable: {exc}")


@pytest.fixture(scope="module")
def inputs() -> AnalysisInputs:
    settings = _settings_or_skip()
    loaded = load_analysis_inputs(settings)
    if loaded.orders.empty:
        pytest.skip("analytical layer is empty; load the raw data and build the views first")
    return loaded


def _assert_frame_totals_match(
    left: pd.DataFrame,
    right: pd.DataFrame,
    key: str,
    left_column: str,
    right_column: str | None = None,
    right_key: str | None = None,
) -> None:
    """Compare one numeric column between a Python frame and a SQL mart."""
    right_column = right_column or left_column
    right_key = right_key or key
    left_frame = left[[key, left_column]].rename(
        columns={key: "join_key", left_column: "python_value"}
    )
    right_frame = right[[right_key, right_column]].rename(
        columns={right_key: "join_key", right_column: "sql_value"}
    )
    merged = left_frame.merge(right_frame, on="join_key", how="inner")
    assert not merged.empty, f"no overlapping {key} values to compare"
    difference = (merged["python_value"] - merged["sql_value"]).abs().max()
    assert difference <= MONEY_TOLERANCE, f"{left_column} differs by {difference} for {key}"


def test_category_and_product_aggregations_match_the_sql_marts(inputs: AnalysisInputs) -> None:
    python_categories = category_summary(inputs.order_lines)
    _assert_frame_totals_match(python_categories, inputs.categories, "category", "revenue")
    _assert_frame_totals_match(
        python_categories, inputs.categories, "category", "units", "units_sold"
    )

    python_products = product_summary(inputs.order_lines)
    _assert_frame_totals_match(python_products, inputs.products, "product_id", "revenue")
    _assert_frame_totals_match(
        python_products, inputs.products, "product_id", "units", "units_sold"
    )


def test_monthly_and_daily_series_match_the_sql_marts(inputs: AnalysisInputs) -> None:
    python_monthly = monthly_metrics(inputs.orders)
    _assert_frame_totals_match(
        python_monthly, inputs.monthly, "month_start", "revenue"
    )

    python_daily = add_rolling_metrics(daily_metrics(inputs.orders))
    _assert_frame_totals_match(
        python_daily,
        inputs.daily,
        "order_date",
        "revenue_rolling_7d",
        right_key="date_key",
    )
    _assert_frame_totals_match(
        python_daily,
        inputs.daily,
        "order_date",
        "revenue_rolling_30d",
        right_key="date_key",
    )


def test_kpi_matches_the_revenue_and_customer_marts(inputs: AnalysisInputs) -> None:
    snapshot = business_kpi_snapshot(inputs.orders, inputs.customers).iloc[0]
    summary = revenue_summary(inputs.orders).iloc[0]

    assert snapshot["total_revenue"] == pytest.approx(summary["total_revenue"], abs=MONEY_TOLERANCE)
    assert snapshot["total_revenue"] == pytest.approx(
        float(inputs.customers["total_revenue"].sum()), abs=MONEY_TOLERANCE
    )
    assert snapshot["total_orders"] == summary["total_orders"]
    assert snapshot["unique_customers"] == int(inputs.customers["has_purchased"].sum())
    assert snapshot["repeat_customers"] == int(inputs.customers["repeat_customer"].sum())
    assert snapshot["total_units"] == int(inputs.customers["total_units"].sum())


def test_country_summary_reconciles_to_the_customer_mart(inputs: AnalysisInputs) -> None:
    countries = country_summary(inputs.customers)
    assert countries["revenue"].sum() == pytest.approx(
        float(inputs.customers["total_revenue"].sum()), abs=MONEY_TOLERANCE
    )
    assert countries["registered_customers"].sum() == len(inputs.customers)
    assert countries["orders"].sum() == int(inputs.customers["total_orders"].sum())


def test_declining_products_follow_the_documented_rule(inputs: AnalysisInputs) -> None:
    flagged = declining_products(inputs.order_lines)
    if flagged.empty:
        pytest.skip("no products met the minimum prior baseline")
    assert (flagged["prior_units"] >= 10).all()
    declining = flagged.loc[flagged["is_declining"]]
    assert (declining["units_change_pct"] <= -0.30).all()
    assert (declining["recent_units"] < declining["prior_units"]).all()


def test_full_analysis_writes_every_table_and_figure(inputs: AnalysisInputs, tmp_path) -> None:
    analysis = analyse(inputs)
    assert not analysis.kpis.empty
    assert analysis.kpis.iloc[0]["total_revenue"] > 0
    assert len(analysis.monthly) >= 12
    assert len(analysis.categories) == len(inputs.categories)
    assert analysis.concentration.iloc[0]["top_10pct_revenue_share_pct"] > 0
    assert not analysis.declining_products.empty

    from novacart.analytics.report import build_business_analysis

    written = build_business_analysis(inputs=inputs, output_dir=tmp_path)
    assert len(written.figures) == 7
    assert len(written.tables) == 15
    for path in list(written.figures.values()) + list(written.tables.values()):
        assert path.is_file()
        assert path.stat().st_size > 0
    assert written.kpis.iloc[0]["total_revenue"] == pytest.approx(
        analysis.kpis.iloc[0]["total_revenue"]
    )


def test_loader_rejects_unknown_relations(inputs: AnalysisInputs) -> None:
    from novacart.analytics.common import load_relation

    with pytest.raises(AnalyticsError):
        load_relation("analytics.raw_orders; DROP TABLE raw.orders")

