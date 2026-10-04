"""Unit tests for the dashboard export layer (Milestone 5, part F)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from novacart.analytics.common import AnalyticsError
from novacart.dashboard.exports import (
    DATA_DICTIONARY_NAME,
    MANIFEST_NAME,
    build_dashboard_exports,
    build_data_dictionary,
    build_export_frames,
    load_export_frame,
)
from novacart.dashboard.schema import EXPORT_SPECS

MONEY_TOLERANCE = 0.01


@pytest.fixture()
def frames(presentation_analysis, presentation_inputs) -> dict[str, pd.DataFrame]:
    return build_export_frames(presentation_analysis, presentation_inputs)


def test_every_export_matches_its_declared_schema(frames) -> None:
    assert set(frames) == set(EXPORT_SPECS)
    for name, frame in frames.items():
        assert list(frame.columns) == list(EXPORT_SPECS[name].columns), name


def test_export_row_counts_match_the_canonical_tables(frames, presentation_inputs) -> None:
    assert len(frames["kpi_summary"]) == 1
    assert len(frames["monthly_revenue"]) == 3  # January, February, March
    assert len(frames["daily_revenue"]) == 75  # complete calendar, 2026-01-05 .. 2026-03-20
    assert len(frames["fact_orders"]) == len(presentation_inputs.orders)
    assert len(frames["fact_order_lines"]) == len(presentation_inputs.order_lines)
    assert len(frames["customer_rfm"]) == len(presentation_inputs.customers)
    assert len(frames["campaign_results"]) == 2
    assert len(frames["campaign_comparison"]) == 2
    assert len(frames["country_performance"]) == 4  # DE, NL, FR, IT
    # Two acquisition cohorts (January: 4 customers, February: 2) with 3 and 2
    # observable month offsets respectively.
    assert len(frames["cohort_sizes"]) == 2
    assert len(frames["cohort_retention"]) == 3 + 2


def test_kpi_values_ignore_the_refunded_order(frames) -> None:
    kpi = frames["kpi_summary"].iloc[0]
    assert kpi["total_revenue"] == pytest.approx(1290.0)
    assert kpi["total_orders"] == 13
    assert kpi["total_units"] == 21  # the refunded order's five units are excluded
    assert kpi["unique_customers"] == 6
    assert kpi["registered_customers"] == 8
    assert kpi["average_order_value"] == pytest.approx(1290 / 13, abs=0.01)
    assert kpi["repeat_customers"] == 4
    assert kpi["repeat_customer_rate"] == pytest.approx(4 / 6, abs=1e-4)


def test_fact_orders_reconciles_with_the_aggregates(frames) -> None:
    facts = frames["fact_orders"]
    kpi = frames["kpi_summary"].iloc[0]

    assert facts["revenue"].sum() == pytest.approx(kpi["total_revenue"], abs=MONEY_TOLERANCE)
    assert facts["recognised_orders"].sum() == kpi["total_orders"]
    assert facts["units"].sum() == kpi["total_units"]

    by_month = facts.groupby("year_month", as_index=False)["revenue"].sum()
    monthly = frames["monthly_revenue"][["year_month", "revenue", "orders_recognised"]]
    merged = by_month.merge(monthly, on="year_month", suffixes=("_fact", "_canonical"))
    assert len(merged) == 3
    assert (merged["revenue_fact"] - merged["revenue_canonical"]).abs().max() <= MONEY_TOLERANCE

    orders_by_month = facts.groupby("year_month", as_index=False)["recognised_orders"].sum()
    merged_orders = orders_by_month.merge(monthly, on="year_month")
    assert len(merged_orders) == 3
    assert (
        merged_orders["recognised_orders"] - merged_orders["orders_recognised"]
    ).abs().max() == 0

    by_country = facts.groupby("country_code", as_index=False)["revenue"].sum()
    countries = frames["country_performance"][["country_code", "revenue"]]
    merged_countries = by_country.merge(countries, on="country_code", suffixes=("_fact", "_canonical"))
    assert len(merged_countries) == 4
    assert (merged_countries["revenue_fact"] - merged_countries["revenue_canonical"]).abs().max() <= MONEY_TOLERANCE

    by_segment = facts.groupby("rfm_segment", as_index=False)["revenue"].sum()
    segments = frames["customer_segments"][["rfm_segment", "revenue"]]
    merged_segments = by_segment.merge(segments, on="rfm_segment", suffixes=("_fact", "_canonical"))
    assert len(merged_segments) >= 4
    assert (merged_segments["revenue_fact"] - merged_segments["revenue_canonical"]).abs().max() <= MONEY_TOLERANCE


def test_fact_order_lines_reconciles_with_products_and_categories(frames) -> None:
    lines = frames["fact_order_lines"]
    kpi = frames["kpi_summary"].iloc[0]
    assert lines["revenue"].sum() == pytest.approx(kpi["total_revenue"], abs=MONEY_TOLERANCE)
    assert lines["units"].sum() == kpi["total_units"]

    by_category = lines.groupby("category", as_index=False)["revenue"].sum()
    categories = frames["category_performance"][["category", "revenue"]]
    merged = by_category.merge(categories, on="category", suffixes=("_fact", "_canonical"))
    assert len(merged) == len(categories)
    assert (merged["revenue_fact"] - merged["revenue_canonical"]).abs().max() <= MONEY_TOLERANCE

    by_product = lines.groupby("product_id", as_index=False)["revenue"].sum()
    products = frames["product_performance"][["product_id", "revenue"]]
    merged_products = by_product.merge(products, on="product_id", suffixes=("_fact", "_canonical"))
    assert len(merged_products) == len(products)
    assert (
        merged_products["revenue_fact"] - merged_products["revenue_canonical"]
    ).abs().max() <= MONEY_TOLERANCE


def test_facts_support_the_published_repeat_customer_rate(frames) -> None:
    """The repeat-rate definition must be reproducible from the fact export."""
    facts = frames["fact_orders"]
    recognised = facts.loc[facts["is_revenue_recognised"]]
    per_customer = recognised.groupby("customer_id")["recognised_orders"].sum()
    recomputed = (per_customer >= 2).sum() / len(per_customer)
    assert recomputed == pytest.approx(
        frames["kpi_summary"].iloc[0]["repeat_customer_rate"], abs=1e-4
    )


def test_campaign_exports_carry_the_statistical_columns(frames) -> None:
    results = frames["campaign_results"]
    for column in ("confidence_interval_low", "adjusted_p_value", "effect_size"):
        assert column in results.columns
    comparison = frames["campaign_comparison"]
    merged = results.merge(comparison, on="campaign_id", suffixes=("_stats", "_comparison"))
    assert len(merged) == 2
    assert (
        merged["absolute_difference_stats"] - merged["absolute_difference_comparison"]
    ).abs().max() <= MONEY_TOLERANCE


def test_written_exports_include_manifest_and_data_dictionary(
    tmp_path, presentation_analysis, presentation_inputs
) -> None:
    exports = build_dashboard_exports(
        analysis=presentation_analysis,
        inputs=presentation_inputs,
        output_dir=tmp_path,
    )

    assert (tmp_path / MANIFEST_NAME).is_file()
    assert (tmp_path / DATA_DICTIONARY_NAME).is_file()
    manifest = json.loads((tmp_path / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert set(manifest["datasets"]) == set(EXPORT_SPECS)
    for name, entry in manifest["datasets"].items():
        assert entry["rows"] == len(exports.frames[name])
        assert entry["columns"] == list(EXPORT_SPECS[name].columns)
        assert len(entry["checksum_sha256"]) == 64
        assert (tmp_path / f"{name}.csv").is_file()
    assert manifest["analysis_window"]["end"] == "2026-03-20"


def test_exports_are_deterministic(tmp_path, presentation_analysis, presentation_inputs) -> None:
    first = build_dashboard_exports(
        analysis=presentation_analysis, inputs=presentation_inputs, output_dir=tmp_path / "a"
    )
    second = build_dashboard_exports(
        analysis=presentation_analysis, inputs=presentation_inputs, output_dir=tmp_path / "b"
    )
    for name in EXPORT_SPECS:
        assert (
            first.manifest["datasets"][name]["checksum_sha256"]
            == second.manifest["datasets"][name]["checksum_sha256"]
        ), name


def test_data_dictionary_covers_every_exported_column() -> None:
    dictionary = build_data_dictionary()
    declared = {
        (name, column) for name, spec in EXPORT_SPECS.items() for column in spec.columns
    }
    documented = set(zip(dictionary["dataset"], dictionary["column"], strict=True))
    assert declared == documented
    assert dictionary["description"].str.len().gt(0).all()
    assert dictionary["source"].str.len().gt(0).all()
    assert dictionary["data_type"].isin(["date", "int", "decimal", "boolean", "text"]).all()


def test_unknown_dataset_is_rejected() -> None:
    with pytest.raises(AnalyticsError):
        load_export_frame("not_a_dataset")

