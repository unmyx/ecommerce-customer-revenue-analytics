"""Orchestration for the analytics layer: tables, figures and console summary.

One command produces every analytical artefact:

* business KPIs, revenue, product and customer tables and charts (Milestone 3);
* RFM segments and cohort retention (Milestone 4);
* campaign comparison and significance testing (Milestone 4).
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from novacart.analytics.campaigns import (
    campaign_comparison,
    campaign_statistics,
    significance_overview,
)
from novacart.analytics.cohorts import CohortAnalysis, cohort_analysis
from novacart.analytics.common import (
    AnalysisInputs,
    ensure_output_dirs,
    format_compact_currency,
    format_count,
    format_percent,
    load_analysis_inputs,
)
from novacart.analytics.customers import (
    country_summary,
    customer_segment_summary,
    revenue_concentration,
    revenue_deciles,
    top_customers_by_revenue,
)
from novacart.analytics.kpis import business_kpi_snapshot
from novacart.analytics.plots import (
    render_all_figures,
    render_campaign_figures,
    render_segmentation_figures,
)
from novacart.analytics.products import (
    category_summary,
    declining_products,
    product_summary,
    top_products_by_revenue,
    top_products_by_units,
)
from novacart.analytics.revenue import revenue_summary
from novacart.analytics.rfm import rfm_table, segment_score_profile, segment_summary
from novacart.analytics.trends import (
    add_month_over_month,
    add_rolling_metrics,
    daily_metrics,
    monthly_metrics,
    weekly_metrics,
)
from novacart.logging_config import configure_logging
from novacart.settings import ConfigurationError, load_database_settings

logger = logging.getLogger(__name__)


@dataclass
class BusinessAnalysis:
    """Every table produced by the analytics layer, plus written paths."""

    # Milestone 3 - descriptive business analysis
    kpis: pd.DataFrame
    revenue: pd.DataFrame
    daily: pd.DataFrame
    weekly: pd.DataFrame
    monthly: pd.DataFrame
    categories: pd.DataFrame
    products: pd.DataFrame
    top_products_revenue: pd.DataFrame
    top_products_units: pd.DataFrame
    declining_products: pd.DataFrame
    countries: pd.DataFrame
    segments: pd.DataFrame
    deciles: pd.DataFrame
    concentration: pd.DataFrame
    top_customers: pd.DataFrame
    # Milestone 4 - RFM, cohorts and campaign statistics
    rfm: pd.DataFrame
    rfm_segments: pd.DataFrame
    rfm_profile: pd.DataFrame
    cohorts: CohortAnalysis
    campaign_comparison: pd.DataFrame
    campaign_statistics: pd.DataFrame
    campaign_overview: pd.DataFrame
    figures: dict[str, Path] = field(default_factory=dict)
    tables: dict[str, Path] = field(default_factory=dict)

    def as_tables(self) -> dict[str, pd.DataFrame]:
        """Named tables for writing to CSV or displaying in a notebook."""
        return {
            "business_kpis": self.kpis,
            "revenue_summary": self.revenue,
            "revenue_daily": self.daily,
            "revenue_weekly": self.weekly,
            "revenue_monthly": self.monthly,
            "category_performance": self.categories,
            "product_performance": self.products,
            "top_products_by_revenue": self.top_products_revenue,
            "top_products_by_units": self.top_products_units,
            "declining_products": self.declining_products,
            "customers_by_country": self.countries,
            "customer_segments": self.segments,
            "customer_revenue_deciles": self.deciles,
            "customer_revenue_concentration": self.concentration,
            "top_customers_by_revenue": self.top_customers,
            "rfm_customers": self.rfm,
            "rfm_segments": self.rfm_segments,
            "rfm_segment_scores": self.rfm_profile,
            "cohort_sizes": self.cohorts.sizes,
            "cohort_retention": self.cohorts.retention,
            "cohort_retention_matrix": self.cohorts.retention_matrix.reset_index(),
            "cohort_revenue": self.cohorts.revenue,
            "campaign_comparison": self.campaign_comparison,
            "campaign_statistics": self.campaign_statistics,
            "campaign_significance_overview": self.campaign_overview,
        }


def analyse(inputs: AnalysisInputs) -> BusinessAnalysis:
    """Run every analytical calculation on already-loaded frames."""
    monthly = add_month_over_month(monthly_metrics(inputs.orders))
    daily = add_rolling_metrics(daily_metrics(inputs.orders))
    products = product_summary(inputs.order_lines)
    categories = category_summary(inputs.order_lines)
    countries = country_summary(inputs.customers)

    rfm = rfm_table(inputs.customers)
    analysis_end_date = (
        inputs.window["analysis_end_date"].iloc[0] if not inputs.window.empty else None
    )
    cohorts = cohort_analysis(inputs.orders, analysis_end_date=analysis_end_date)
    statistics = campaign_statistics(inputs.campaign_outcomes)

    return BusinessAnalysis(
        kpis=business_kpi_snapshot(inputs.orders, inputs.customers),
        revenue=revenue_summary(inputs.orders),
        daily=daily,
        weekly=weekly_metrics(inputs.orders),
        monthly=monthly,
        categories=categories,
        products=products,
        top_products_revenue=top_products_by_revenue(products, 10),
        top_products_units=top_products_by_units(products, 10),
        declining_products=declining_products(inputs.order_lines),
        countries=countries,
        segments=customer_segment_summary(inputs.customers),
        deciles=revenue_deciles(inputs.customers),
        concentration=revenue_concentration(inputs.customers),
        top_customers=top_customers_by_revenue(inputs.customers, 10),
        rfm=rfm,
        rfm_segments=segment_summary(rfm),
        rfm_profile=segment_score_profile(rfm),
        cohorts=cohorts,
        campaign_comparison=campaign_comparison(inputs.campaign_outcomes),
        campaign_statistics=statistics,
        campaign_overview=significance_overview(statistics),
    )


def build_business_analysis(
    *,
    inputs: AnalysisInputs | None = None,
    output_dir: Path | None = None,
    write_tables: bool = True,
    write_figures: bool = True,
) -> BusinessAnalysis:
    """Load the analytical marts, run the analysis and write tables + figures."""
    loaded = inputs or load_analysis_inputs()
    analysis = analyse(loaded)
    figures_dir, tables_dir = ensure_output_dirs(output_dir)

    if write_tables:
        for name, frame in analysis.as_tables().items():
            path = tables_dir / f"{name}.csv"
            frame.to_csv(path, index=False)
            analysis.tables[name] = path

    if write_figures:
        analysis.figures = render_all_figures(
            monthly=analysis.monthly,
            categories=analysis.categories,
            products=analysis.products,
            customers=loaded.customers,
            countries=analysis.countries,
            output_dir=figures_dir,
        )
        analysis.figures |= render_segmentation_figures(
            segments=analysis.rfm_segments,
            profile=analysis.rfm_profile,
            cohort=analysis.cohorts,
            output_dir=figures_dir,
        )
        analysis.figures |= render_campaign_figures(
            statistics=analysis.campaign_statistics,
            output_dir=figures_dir,
        )
    return analysis


def _print_kpi(analysis: BusinessAnalysis) -> None:
    row = analysis.kpis.iloc[0]
    concentration = analysis.concentration.iloc[0] if not analysis.concentration.empty else None
    print(f"Analysis window              : {row['period_start']} to {row['period_end']}")
    print(f"Total net revenue            : {format_compact_currency(row['total_revenue'])}")
    print(
        f"Orders / units               : {format_count(row['total_orders'])} / "
        f"{format_count(row['total_units'])}"
    )
    print(
        f"Purchasing / registered      : {format_count(row['unique_customers'])} / "
        f"{format_count(row['registered_customers'])} customers"
    )
    print(f"Average order value          : {format_compact_currency(row['average_order_value'])}")
    print(
        f"Revenue per purchasing cust. : "
        f"{format_compact_currency(row['revenue_per_customer'])}"
    )
    print(f"Repeat customer rate         : {format_percent(row['repeat_customer_rate'])}")
    if concentration is not None:
        print(
            f"Top 10% customer share       : "
            f"{format_percent(concentration['top_10pct_revenue_share_pct'] / 100)}"
        )
    print(f"Declining products flagged   : {int(analysis.declining_products['is_declining'].sum())}")

    if not analysis.rfm_segments.empty:
        leaders = analysis.rfm_segments.sort_values("revenue", ascending=False).iloc[0]
        print(
            f"Top RFM segment by revenue   : {leaders['rfm_segment']} "
            f"({format_count(leaders['customers'])} customers, "
            f"{format_compact_currency(leaders['revenue'])})"
        )
    if not analysis.cohorts.sizes.empty:
        sizes = analysis.cohorts.sizes
        print(
            f"Acquisition cohorts          : {len(sizes)} "
            f"({sizes['cohort_month'].min():%Y-%m} to {sizes['cohort_month'].max():%Y-%m})"
        )
        month_one = analysis.cohorts.retention
        month_one = month_one.loc[month_one["month_offset"] == 1, "retention_rate"]
        if not month_one.empty:
            print(f"Median month-1 retention     : {format_percent(float(month_one.median()))}")
    if not analysis.campaign_statistics.empty:
        statistics = analysis.campaign_statistics
        print(
            f"Campaigns significant (FDR)  : "
            f"{int(statistics['statistically_significant'].sum())} of {len(statistics)}"
        )
        print(
            f"Campaigns with practical lift: "
            f"{int(statistics['practically_significant'].sum())} of {len(statistics)}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="novacart-analyze",
        description="Run the analytics layer and write tables and figures.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--no-figures", action="store_true")
    parser.add_argument("--no-tables", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(logging.WARNING if args.quiet else logging.INFO)

    try:
        settings = load_database_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2

    try:
        inputs = load_analysis_inputs(settings)
        analysis = build_business_analysis(
            inputs=inputs,
            output_dir=args.output_dir,
            write_tables=not args.no_tables,
            write_figures=not args.no_figures,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator
        print(f"Business analysis failed: {exc}")
        return 1

    _print_kpi(analysis)
    if analysis.figures:
        print(f"Figures written              : {len(analysis.figures)}")
    if analysis.tables:
        print(f"Tables written               : {len(analysis.tables)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

