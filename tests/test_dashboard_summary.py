"""Unit tests for the generated executive summary (Milestone 5, part D)."""

from __future__ import annotations

import dataclasses

import pytest

from novacart.analytics.common import (
    format_compact_currency,
    format_count,
    format_percent,
)
from novacart.dashboard.exports import build_export_frames
from novacart.dashboard.summary import (
    ExecutiveSummary,
    build_executive_summary,
    write_executive_summary,
)

REQUIRED_SECTIONS = (
    "## 1. Executive KPIs",
    "## 2. Revenue trend",
    "## 3. Customer behaviour",
    "## 4. Product findings",
    "## 5. Campaign findings",
    "## 6. Data limitations",
    "## 7. Recommended business actions",
)


@pytest.fixture()
def summary(presentation_analysis) -> ExecutiveSummary:
    return build_executive_summary(presentation_analysis)


def test_summary_contains_every_required_section(summary: ExecutiveSummary) -> None:
    for section in REQUIRED_SECTIONS:
        assert section in summary.markdown
    assert "<h2>1. Executive KPIs</h2>" in summary.html
    assert "executive summary" in summary.html.lower()


def test_summary_quotes_measured_values_not_prose(
    summary: ExecutiveSummary, presentation_analysis, presentation_inputs
) -> None:
    kpi = presentation_analysis.kpis.iloc[0]
    assert format_compact_currency(kpi["total_revenue"]) in summary.markdown
    assert format_count(kpi["total_orders"]) in summary.markdown
    assert format_count(kpi["unique_customers"]) in summary.markdown
    assert format_percent(kpi["repeat_customer_rate"]) in summary.markdown
    assert format_percent(summary.metrics["customers"]["top_10pct_revenue_share"] / 100) in (
        summary.markdown
    )

    # The numbers in the summary must equal the dashboard export values.
    frames = build_export_frames(presentation_analysis, presentation_inputs)
    assert float(frames["kpi_summary"].iloc[0]["total_revenue"]) == pytest.approx(
        float(strip_currency(summary.metrics["kpis"]["total_revenue"]))
    )


def strip_currency(value) -> float:
    return float(value)


def test_summary_recommendations_are_derived_from_results(summary: ExecutiveSummary) -> None:
    assert len(summary.recommendations) >= 5
    for recommendation in summary.recommendations:
        assert len(recommendation) > 40
        # Every recommendation quotes at least one measured figure or count.
        assert any(character.isdigit() for character in recommendation)
    joined = " ".join(summary.recommendations)
    assert "Champions" in joined
    assert "At Risk" in joined
    assert "campaign" in joined.lower()


def test_summary_limits_and_caveats_are_present(summary: ExecutiveSummary) -> None:
    limitations = summary.markdown.split("## 6. Data limitations")[1].split(
        "## 7. Recommended business actions"
    )[0]
    assert "synthetic" in limitations.lower()
    assert "confounding" in limitations.lower()
    assert "non-random exposure" in limitations.lower()
    assert "left-censored" in limitations.lower()


def test_summary_changes_when_the_data_changes(presentation_analysis) -> None:
    baseline = build_executive_summary(presentation_analysis)
    inflated_kpis = presentation_analysis.kpis.assign(total_revenue=1_500_000.0)
    changed = build_executive_summary(dataclasses.replace(presentation_analysis, kpis=inflated_kpis))

    assert changed.markdown != baseline.markdown
    assert "EUR 1.50m" in changed.markdown
    assert "EUR 1.50m" not in baseline.markdown


def test_summary_files_are_written(tmp_path, summary: ExecutiveSummary) -> None:
    paths = write_executive_summary(summary, output_dir=tmp_path)
    assert paths["markdown"].is_file()
    assert paths["html"].is_file()
    assert paths["markdown"].read_text(encoding="utf-8") == summary.markdown

    pytest.importorskip("xlsxwriter")
    excel_path = paths.get("excel")
    assert excel_path is not None and excel_path.is_file()


def test_summary_metrics_expose_the_numbers_it_quotes(summary: ExecutiveSummary) -> None:
    metrics = summary.metrics
    assert set(metrics) == {"kpis", "revenue", "customers", "products", "campaigns"}
    assert metrics["campaigns"]["campaigns_tested"] == 2
    assert metrics["customers"]["champions_customers"] >= 0
    assert metrics["products"]["top_category"]
    assert metrics["revenue"]["peak_month"]

