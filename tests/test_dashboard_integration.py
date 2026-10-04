"""Database-backed checks for the dashboard export layer.

They prove that the exported datasets - and therefore everything Power BI loads -
reconcile with the canonical SQL marts and the Python analytics outputs.

Skipped unless ``NOVACART_RUN_DB_TESTS=1``.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from novacart.analytics.common import AnalysisInputs, load_analysis_inputs, load_relation
from novacart.analytics.report import analyse
from novacart.dashboard.cli import build_dashboard_outputs
from novacart.dashboard.exports import CSV_DIR, MANIFEST_NAME, build_dashboard_exports
from novacart.dashboard.schema import EXPORT_SPECS
from novacart.settings import ConfigurationError, load_database_settings

pytestmark = pytest.mark.integration

MONEY_TOLERANCE = 0.01


def _integration_enabled() -> bool:
    return os.getenv("NOVACART_RUN_DB_TESTS", "").lower() in {"1", "true", "yes"}


def _settings_or_skip():
    if not _integration_enabled():
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


@pytest.fixture(scope="module")
def analysis(inputs: AnalysisInputs):
    return analyse(inputs)


@pytest.fixture(scope="module")
def exports(inputs: AnalysisInputs, analysis):
    """Build the dashboard exports once and reuse them across the checks."""
    return build_dashboard_exports(
        inputs=inputs, analysis=analysis, output_dir=CSV_DIR, write=False
    )


def test_kpi_export_matches_the_analytics_and_the_sql_mart(
    inputs: AnalysisInputs, analysis, exports
) -> None:
    kpi = exports.frames["kpi_summary"].iloc[0]
    published = analysis.kpis.iloc[0]
    assert kpi["total_revenue"] == pytest.approx(published["total_revenue"])
    assert kpi["total_orders"] == published["total_orders"]
    assert kpi["unique_customers"] == published["unique_customers"]

    customers_mart = load_relation("analytics.mart_customer_features")
    assert kpi["total_revenue"] == pytest.approx(
        float(customers_mart["total_revenue"].sum()), abs=MONEY_TOLERANCE
    )
    assert kpi["total_orders"] == int(customers_mart["total_orders"].sum())
    assert kpi["registered_customers"] == len(customers_mart)


def test_fact_exports_reconcile_with_the_warehouse(inputs: AnalysisInputs, exports) -> None:
    orders = exports.frames["fact_orders"]
    lines = exports.frames["fact_order_lines"]

    assert len(orders) == len(inputs.orders)
    assert len(lines) == len(inputs.order_lines)
    assert orders["order_id"].is_unique
    assert lines["order_item_id"].is_unique
    assert orders["rfm_segment"].notna().all()  # every order joins to a segment

    kpi = exports.frames["kpi_summary"].iloc[0]
    assert orders["revenue"].sum() == pytest.approx(kpi["total_revenue"], abs=MONEY_TOLERANCE)
    assert lines["revenue"].sum() == pytest.approx(kpi["total_revenue"], abs=MONEY_TOLERANCE)
    assert orders["recognised_orders"].sum() == kpi["total_orders"]
    assert orders["units"].sum() == kpi["total_units"]

    monthly = exports.frames["monthly_revenue"]
    by_month = orders.groupby("year_month", as_index=False)["revenue"].sum()
    merged = by_month.merge(monthly[["year_month", "revenue"]], on="year_month", suffixes=("_fact", "_canonical"))
    assert len(merged) == len(monthly)
    assert (merged["revenue_fact"] - merged["revenue_canonical"]).abs().max() <= MONEY_TOLERANCE


def test_campaign_export_matches_the_statistical_results(
    inputs: AnalysisInputs, analysis, exports
) -> None:
    exported = exports.frames["campaign_results"]
    published = analysis.campaign_statistics
    pd.testing.assert_frame_equal(
        exported.reset_index(drop=True), published.reset_index(drop=True)
    )
    mart = load_relation("analytics.mart_campaign_performance")
    merged = exported.merge(mart, on="campaign_id", suffixes=("_export", "_mart"))
    assert len(merged) == len(mart)
    assert merged["treatment_n"].equals(mart.sort_values("campaign_id")["treatment_assigned"].reset_index(drop=True))


def test_full_dashboard_build_writes_every_artefact(inputs: AnalysisInputs, tmp_path) -> None:
    result = build_dashboard_outputs(
        inputs=inputs,
        output_dir=tmp_path / "csv",
        preview_dir=tmp_path / "previews",
    )
    exports = result["exports"]
    assert set(exports.frames) == set(EXPORT_SPECS) | {"data_dictionary"}
    manifest = json.loads((tmp_path / "csv" / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert set(manifest["datasets"]) == set(EXPORT_SPECS)
    assert len(result["previews"]) == 4
    for name, path in result["previews"].items():
        assert path.is_file() and path.stat().st_size > 10_000, name
    for key in ("markdown", "html", "excel"):
        assert result["summary_paths"][key].is_file(), key

    kpi = exports.frames["kpi_summary"].iloc[0]
    summary_text = result["summary_paths"]["markdown"].read_text(encoding="utf-8")
    assert f"{kpi['total_orders']:,.0f}" in summary_text
    assert "## 7. Recommended business actions" in summary_text

