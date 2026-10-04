"""Reusable business charts (Milestone 3).

Every figure answers one business question, uses the same visual language, and is
saved under a deterministic filename in ``outputs/figures/``. The matplotlib
backend is pinned to ``Agg`` so figure generation is identical in a notebook, in
a script and in CI.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from novacart.analytics.common import (
    FIGURES_DIR,
    AnalyticsError,
    require_columns,
)

FIGURE_SIZE = (11.0, 5.5)
FIGURE_DPI = 150
PRIMARY_COLOR = "#1f4e79"
INK_COLOR = "#1f2933"

FIGURE_FILENAMES: dict[str, str] = {
    "monthly_revenue": "monthly_revenue_trend.png",
    "monthly_orders": "monthly_orders_trend.png",
    "monthly_aov": "monthly_aov_trend.png",
    "revenue_by_category": "revenue_by_category.png",
    "top_products_by_revenue": "top10_products_by_revenue.png",
    "customer_revenue_distribution": "customer_revenue_distribution.png",
    "revenue_by_country": "revenue_by_country.png",
    "rfm_customer_counts": "rfm_customer_counts.png",
    "rfm_revenue_by_segment": "rfm_revenue_by_segment.png",
    "rfm_segment_comparison": "rfm_segment_comparison.png",
    "cohort_retention_heatmap": "cohort_retention_heatmap.png",
    "cohort_sizes": "cohort_sizes.png",
    "cohort_revenue_curve": "cohort_revenue_curve.png",
    "campaign_lift_comparison": "campaign_lift_comparison.png",
    "campaign_confidence_intervals": "campaign_confidence_intervals.png",
    "campaign_significance_overview": "campaign_significance_overview.png",
}

REVENUE_DEFINITION = (
    "Revenue = recognised net merchandise revenue (completed orders, after line discounts); "
    "shipping and VAT excluded."
)


def apply_business_style() -> None:
    """One consistent, non-decorative style for every figure."""
    plt.rcParams.update(
        {
            "figure.figsize": FIGURE_SIZE,
            "figure.dpi": FIGURE_DPI,
            "savefig.dpi": FIGURE_DPI,
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linestyle": "-",
            "legend.frameon": False,
            "figure.autolayout": False,
        }
    )


apply_business_style()


def currency_formatter(value: float, _position: float | None = None) -> str:
    if abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:.1f}m"
    if abs(value) >= 1_000:
        return f"€{value / 1_000:.0f}k"
    return f"€{value:.0f}"


def count_formatter(value: float, _position: float | None = None) -> str:
    return f"{value:,.0f}"


def _add_definition(figure: Figure, text: str = REVENUE_DEFINITION) -> None:
    figure.text(0.01, 0.005, text, fontsize=8, color="#555555", ha="left", va="bottom")


def _require_rows(frame: pd.DataFrame, purpose: str) -> None:
    if frame is None or frame.empty:
        raise AnalyticsError(f"{purpose} needs at least one row of data")


def save_figure(figure: Figure, filename: str, *, output_dir: Path | None = None) -> Path:
    """Save a figure under a deterministic name and return its path."""
    directory = output_dir or FIGURES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    figure.savefig(path, dpi=FIGURE_DPI, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return path


def bar_panel(
    axis,
    labels: list[str],
    values: np.ndarray,
    title: str,
    *,
    horizontal: bool = True,
    formatter=currency_formatter,
    colors=None,
    annotate: bool = True,
    label_size: float = 8.5,
) -> None:
    """Draw one bar panel with the project's formatting (shared by every page/report)."""
    positions = np.arange(len(labels))
    if horizontal:
        axis.barh(positions, values, color=colors or PRIMARY_COLOR, height=0.72)
        axis.set_yticks(positions)
        axis.set_yticklabels(labels, fontsize=label_size)
        axis.grid(axis="y", visible=False)
        axis.xaxis.set_major_formatter(FuncFormatter(formatter))
        if annotate:
            for position, value in zip(positions, values):
                axis.text(
                    value,
                    position,
                    f"  {formatter(value)}",
                    va="center",
                    fontsize=label_size - 1,
                    color=INK_COLOR,
                )
    else:
        axis.bar(positions, values, color=colors or PRIMARY_COLOR, width=0.7)
        axis.set_xticks(positions)
        axis.set_xticklabels(labels, fontsize=label_size - 0.5, rotation=45, ha="right")
        axis.yaxis.set_major_formatter(FuncFormatter(formatter))
    axis.set_title(title, loc="left")


def line_panel(
    axis,
    labels: list[str],
    values: np.ndarray,
    title: str,
    *,
    formatter=currency_formatter,
    max_labels: int = 12,
) -> None:
    """Draw one line panel with the project's formatting."""
    axis.plot(
        range(len(labels)), values, marker="o", markersize=3.5, color=PRIMARY_COLOR, linewidth=2
    )
    step = max(1, len(labels) // max_labels)
    axis.set_xticks(list(range(0, len(labels), step)))
    axis.set_xticklabels(labels[::step], fontsize=8, rotation=45, ha="right")
    axis.yaxis.set_major_formatter(FuncFormatter(formatter))
    axis.set_title(title, loc="left")


def _month_labels(axis, labels: list[str], step: int = 2) -> None:
    positions = list(range(len(labels)))
    axis.set_xticks(positions[::step])
    axis.set_xticklabels(labels[::step], rotation=45, ha="right")


def plot_monthly_revenue_trend(monthly: pd.DataFrame) -> Figure:
    """How is monthly revenue changing over time?"""
    require_columns(monthly, ("year_month", "revenue"), "plot_monthly_revenue_trend")
    _require_rows(monthly, "plot_monthly_revenue_trend")
    frame = monthly.sort_values("month_start") if "month_start" in monthly.columns else monthly

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.plot(
        range(len(frame)), frame["revenue"], marker="o", markersize=4, color="#1f4e79", linewidth=2
    )
    axis.set_title("Monthly net revenue")
    axis.set_xlabel("Month")
    axis.set_ylabel("Net revenue (EUR)")
    axis.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
    _month_labels(axis, list(frame["year_month"]))
    _add_definition(figure)
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_monthly_orders_trend(monthly: pd.DataFrame) -> Figure:
    """How many orders are placed each month?"""
    require_columns(monthly, ("year_month", "orders_recognised"), "plot_monthly_orders_trend")
    _require_rows(monthly, "plot_monthly_orders_trend")
    frame = monthly.sort_values("month_start") if "month_start" in monthly.columns else monthly

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.bar(range(len(frame)), frame["orders_recognised"], color="#2e75b6", width=0.7)
    axis.set_title("Orders per month (completed orders)")
    axis.set_xlabel("Month")
    axis.set_ylabel("Orders")
    axis.yaxis.set_major_formatter(FuncFormatter(count_formatter))
    _month_labels(axis, list(frame["year_month"]))
    _add_definition(figure)
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_monthly_aov_trend(monthly: pd.DataFrame) -> Figure:
    """Is average order value moving up or down?"""
    require_columns(monthly, ("year_month", "average_order_value"), "plot_monthly_aov_trend")
    _require_rows(monthly, "plot_monthly_aov_trend")
    frame = monthly.sort_values("month_start") if "month_start" in monthly.columns else monthly

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.plot(
        range(len(frame)),
        frame["average_order_value"],
        marker="o",
        markersize=4,
        color="#c55a11",
        linewidth=2,
    )
    axis.set_title("Average order value per month")
    axis.set_xlabel("Month")
    axis.set_ylabel("Average order value (EUR)")
    axis.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
    _month_labels(axis, list(frame["year_month"]))
    _add_definition(figure)
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_revenue_by_category(categories: pd.DataFrame) -> Figure:
    """Which categories generate the revenue?"""
    require_columns(categories, ("category", "revenue"), "plot_revenue_by_category")
    _require_rows(categories, "plot_revenue_by_category")
    frame = categories.sort_values("revenue", ascending=True)

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.barh(frame["category"], frame["revenue"], color="#1f4e79")
    axis.set_title("Revenue by category (24 months)")
    axis.set_xlabel("Net revenue (EUR)")
    axis.set_ylabel("")
    axis.xaxis.set_major_formatter(FuncFormatter(currency_formatter))
    axis.grid(axis="y", visible=False)
    total = float(frame["revenue"].sum())
    for position, value in enumerate(frame["revenue"]):
        share = (value / total) if total else np.nan
        axis.text(
            value,
            position,
            f"  {currency_formatter(value)} ({share:.1%})",
            va="center",
            fontsize=9,
        )
    _add_definition(figure)
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_top_products_by_revenue(products: pd.DataFrame, n: int = 10) -> Figure:
    """Which individual products earn the most revenue?"""
    require_columns(
        products, ("product_id", "product_name", "revenue"), "plot_top_products_by_revenue"
    )
    _require_rows(products, "plot_top_products_by_revenue")
    frame = (
        products.sort_values(["revenue", "product_id"], ascending=[False, True])
        .head(n)
        .sort_values("revenue", ascending=True)
    )
    labels = [name if len(name) <= 38 else f"{name[:35]}..." for name in frame["product_name"]]

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.barh(labels, frame["revenue"], color="#2e75b6")
    axis.set_title(f"Top {n} products by revenue")
    axis.set_xlabel("Net revenue (EUR)")
    axis.set_ylabel("")
    axis.xaxis.set_major_formatter(FuncFormatter(currency_formatter))
    axis.grid(axis="y", visible=False)
    for position, value in enumerate(frame["revenue"]):
        axis.text(value, position, f"  {currency_formatter(value)}", va="center", fontsize=9)
    _add_definition(figure)
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_customer_revenue_distribution(customers: pd.DataFrame) -> Figure:
    """How concentrated is customer revenue?

    Left panel: distribution of revenue across purchasing customers (clipped at
    the 99th percentile so the long tail stays readable). Right panel: share of
    revenue by customer decile.
    """
    from novacart.analytics.customers import _purchasing, revenue_deciles

    require_columns(customers, ("customer_id", "total_revenue"), "plot_customer_revenue_distribution")
    purchasing = _purchasing(customers, "plot_customer_revenue_distribution")
    purchasing = purchasing.loc[purchasing["total_revenue"] > 0]
    _require_rows(purchasing, "plot_customer_revenue_distribution")

    deciles = revenue_deciles(customers)
    values = purchasing["total_revenue"].astype("float64")
    clip = float(values.quantile(0.99))
    clipped = values.clip(upper=clip)

    figure, (left, right) = plt.subplots(1, 2, figsize=(13.0, 5.5))
    left.hist(clipped, bins=40, color="#1f4e79")
    left.set_title("Customer revenue distribution")
    left.set_xlabel("Revenue per purchasing customer (EUR, clipped at 99th percentile)")
    left.set_ylabel("Customers")
    left.xaxis.set_major_formatter(FuncFormatter(currency_formatter))
    left.yaxis.set_major_formatter(FuncFormatter(count_formatter))

    positions = list(range(len(deciles)))
    right.bar(positions, deciles["revenue_share_pct"], color="#c55a11")
    right.set_xticks(positions)
    right.set_xticklabels(deciles["revenue_decile"].astype(int).astype(str))
    right.set_title("Share of revenue by customer decile")
    right.set_xlabel("Revenue decile (1 = lowest spending, 10 = highest)")
    right.set_ylabel("Share of revenue (%)")
    right.grid(axis="x", visible=False)

    _add_definition(figure)
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    return figure


def plot_revenue_by_country(countries: pd.DataFrame, n: int = 12) -> Figure:
    """Which markets contribute the most revenue?"""
    require_columns(countries, ("country_code", "revenue"), "plot_revenue_by_country")
    _require_rows(countries, "plot_revenue_by_country")
    frame = countries.sort_values("revenue", ascending=False).head(n).sort_values("revenue")

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.barh(frame["country_code"], frame["revenue"], color="#2e75b6")
    axis.set_title(f"Revenue by country (top {min(n, len(frame))} markets)")
    axis.set_xlabel("Net revenue (EUR)")
    axis.set_ylabel("Country")
    axis.xaxis.set_major_formatter(FuncFormatter(currency_formatter))
    axis.grid(axis="y", visible=False)
    for position, value in enumerate(frame["revenue"]):
        axis.text(value, position, f"  {currency_formatter(value)}", va="center", fontsize=9)
    _add_definition(figure)
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def render_all_figures(
    *,
    monthly: pd.DataFrame,
    categories: pd.DataFrame,
    products: pd.DataFrame,
    customers: pd.DataFrame,
    countries: pd.DataFrame,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    """Render every required business figure and return the saved paths."""
    figures = {
        "monthly_revenue": plot_monthly_revenue_trend(monthly),
        "monthly_orders": plot_monthly_orders_trend(monthly),
        "monthly_aov": plot_monthly_aov_trend(monthly),
        "revenue_by_category": plot_revenue_by_category(categories),
        "top_products_by_revenue": plot_top_products_by_revenue(products),
        "customer_revenue_distribution": plot_customer_revenue_distribution(customers),
        "revenue_by_country": plot_revenue_by_country(countries),
    }
    return {
        key: save_figure(figure, FIGURE_FILENAMES[key], output_dir=output_dir)
        for key, figure in figures.items()
    }


# ---------------------------------------------------------------------------
# RFM segmentation figures
# ---------------------------------------------------------------------------
def plot_rfm_segment_customers(segments: pd.DataFrame) -> Figure:
    """How many customers sit in each RFM segment?"""
    require_columns(
        segments,
        ("rfm_segment", "customers", "customer_share_pct"),
        "plot_rfm_segment_customers",
    )
    _require_rows(segments, "plot_rfm_segment_customers")
    frame = segments.sort_values("customers", ascending=True)

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.barh(frame["rfm_segment"], frame["customers"], color="#1f4e79")
    axis.set_title("Customers by RFM segment")
    axis.set_xlabel("Customers")
    axis.set_ylabel("")
    axis.xaxis.set_major_formatter(FuncFormatter(count_formatter))
    axis.grid(axis="y", visible=False)
    for position, row in enumerate(frame.itertuples()):
        axis.text(
            row.customers,
            position,
            f"  {row.customers:,.0f} ({row.customer_share_pct:.1f}%)",
            va="center",
            fontsize=9,
        )
    _add_definition(
        figure,
        "RFM scores are quintiles over purchasing customers; ties broken by customer id. "
        "Segments follow the documented priority rules.",
    )
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_rfm_segment_revenue(segments: pd.DataFrame) -> Figure:
    """Which RFM segments carry the revenue?"""
    require_columns(
        segments,
        ("rfm_segment", "revenue", "revenue_share_pct"),
        "plot_rfm_segment_revenue",
    )
    _require_rows(segments, "plot_rfm_segment_revenue")
    frame = segments.sort_values("revenue", ascending=True)

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.barh(frame["rfm_segment"], frame["revenue"], color="#c55a11")
    axis.set_title("Net revenue by RFM segment")
    axis.set_xlabel("Net revenue (EUR)")
    axis.set_ylabel("")
    axis.xaxis.set_major_formatter(FuncFormatter(currency_formatter))
    axis.grid(axis="y", visible=False)
    for position, row in enumerate(frame.itertuples()):
        axis.text(
            row.revenue,
            position,
            f"  {currency_formatter(row.revenue)} ({row.revenue_share_pct:.1f}%)",
            va="center",
            fontsize=9,
        )
    _add_definition(figure)
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_rfm_segment_comparison(profile: pd.DataFrame) -> Figure:
    """How do segments differ on recency, frequency and monetary scores?"""
    require_columns(
        profile,
        ("rfm_segment", "average_r", "average_f", "average_m"),
        "plot_rfm_segment_comparison",
    )
    _require_rows(profile, "plot_rfm_segment_comparison")
    frame = profile.iloc[::-1].reset_index(drop=True)

    figure, axis = plt.subplots(figsize=(11.0, 6.0))
    positions = np.arange(len(frame))
    width = 0.26
    axis.barh(positions + width, frame["average_r"], height=width, label="Recency score", color="#1f4e79")
    axis.barh(positions, frame["average_f"], height=width, label="Frequency score", color="#2e75b6")
    axis.barh(positions - width, frame["average_m"], height=width, label="Monetary score", color="#9dc3e6")
    axis.set_yticks(positions)
    axis.set_yticklabels(frame["rfm_segment"])
    axis.set_xlim(0, 5.4)
    axis.set_xlabel("Average score (1 = weakest, 5 = strongest)")
    axis.set_title("RFM segment comparison (average scores)")
    axis.grid(axis="y", visible=False)
    axis.legend(loc="lower right")
    _add_definition(
        figure,
        "Scores are quintiles: 5 is the most recent / most frequent / highest spending fifth.",
    )
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


# ---------------------------------------------------------------------------
# Cohort figures
# ---------------------------------------------------------------------------
def plot_cohort_retention_heatmap(retention_matrix: pd.DataFrame) -> Figure:
    """Which acquisition cohorts retain best, and for how long?"""
    if retention_matrix is None or retention_matrix.empty:
        raise AnalyticsError("plot_cohort_retention_heatmap needs a non-empty matrix")

    values = np.ma.masked_invalid(retention_matrix.to_numpy(dtype="float64"))
    colour_map = plt.get_cmap("Blues").with_extremes(bad="#f0f0f0")

    height = max(4.5, 0.32 * len(retention_matrix) + 1.6)
    figure, axis = plt.subplots(figsize=(11.0, height))
    image = axis.imshow(values, aspect="auto", cmap=colour_map, vmin=0.0, vmax=1.0)
    axis.set_xticks(range(retention_matrix.shape[1]))
    axis.set_xticklabels([str(column) for column in retention_matrix.columns])
    axis.set_yticks(range(retention_matrix.shape[0]))
    # The matrix arrives either from the analytics layer (datetime index) or from a
    # CSV round-trip (text); normalise before formatting.
    axis.set_yticklabels(
        list(pd.to_datetime(list(retention_matrix.index)).strftime("%Y-%m"))
    )
    axis.set_xlabel("Months since first purchase")
    axis.set_ylabel("Cohort (first purchase month)")
    axis.set_title("Monthly cohort retention")
    axis.grid(visible=False)

    for row in range(values.shape[0]):
        for column in range(values.shape[1]):
            value = values[row, column]
            if np.ma.is_masked(value):
                continue
            axis.text(
                column,
                row,
                f"{value:.0%}",
                ha="center",
                va="center",
                fontsize=8,
                color="white" if value > 0.55 else "#333333",
            )

    colour_bar = figure.colorbar(image, ax=axis, fraction=0.025, pad=0.02)
    colour_bar.ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0%}"))
    _add_definition(
        figure,
        "Retention = share of the cohort with at least one recognised order in that month. "
        "Grey cells are not yet observable as of the analysis end date.",
    )
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_cohort_sizes(sizes: pd.DataFrame) -> Figure:
    """How large is each monthly acquisition cohort?"""
    require_columns(sizes, ("cohort_month", "cohort_size"), "plot_cohort_sizes")
    _require_rows(sizes, "plot_cohort_sizes")
    frame = sizes.sort_values("cohort_month")
    labels = [timestamp.strftime("%Y-%m") for timestamp in pd.to_datetime(frame["cohort_month"])]

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    positions = list(range(len(frame)))
    axis.bar(positions, frame["cohort_size"], color="#2e75b6", width=0.7)
    axis.set_title("Customers per acquisition cohort")
    axis.set_xlabel("Cohort (first purchase month)")
    axis.set_ylabel("Customers")
    axis.yaxis.set_major_formatter(FuncFormatter(count_formatter))
    _step = 2 if len(labels) > 12 else 1
    axis.set_xticks(positions[::_step])
    axis.set_xticklabels(labels[::_step], rotation=45, ha="right")
    _add_definition(
        figure,
        "A cohort is the calendar month of a customer's first recognised order.",
    )
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_cohort_revenue_curve(revenue: pd.DataFrame) -> Figure:
    """How much does an average cohort customer spend over time?"""
    require_columns(
        revenue,
        ("month_offset", "revenue_per_cohort_customer"),
        "plot_cohort_revenue_curve",
    )
    _require_rows(revenue, "plot_cohort_revenue_curve")
    curve = (
        revenue.groupby("month_offset", as_index=False)["revenue_per_cohort_customer"]
        .mean()
        .sort_values("month_offset")
    )

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.plot(
        curve["month_offset"],
        curve["revenue_per_cohort_customer"],
        marker="o",
        markersize=4,
        color="#1f4e79",
        linewidth=2,
    )
    axis.set_title("Average revenue per cohort customer by month offset")
    axis.set_xlabel("Months since first purchase")
    axis.set_ylabel("Revenue per cohort customer (EUR)")
    axis.yaxis.set_major_formatter(FuncFormatter(currency_formatter))
    _add_definition(
        figure,
        "Revenue in an offset month divided by the original cohort size, averaged across cohorts.",
    )
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


# ---------------------------------------------------------------------------
# Campaign figures
# ---------------------------------------------------------------------------
def plot_campaign_lift_comparison(statistics: pd.DataFrame) -> Figure:
    """Which campaigns show the largest lift over their holdout group?"""
    require_columns(
        statistics,
        ("campaign_id", "relative_difference", "statistically_significant"),
        "plot_campaign_lift_comparison",
    )
    _require_rows(statistics, "plot_campaign_lift_comparison")
    from novacart.analytics.campaigns import PRACTICAL_RELATIVE_THRESHOLD

    frame = statistics.dropna(subset=["relative_difference"]).sort_values("relative_difference")
    colours = [
        "#1f4e79" if significant else "#9dc3e6"
        for significant in frame["statistically_significant"]
    ]

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    axis.barh(frame["campaign_id"], frame["relative_difference"] * 100, color=colours)
    axis.axvline(
        PRACTICAL_RELATIVE_THRESHOLD * 100,
        color="#c55a11",
        linestyle="--",
        linewidth=1,
        label=f"Practical threshold ({PRACTICAL_RELATIVE_THRESHOLD:.0%})",
    )
    axis.axvline(0, color="#333333", linewidth=1)
    axis.set_title("Campaign lift vs holdout (revenue per assigned customer)")
    axis.set_xlabel("Relative difference in revenue per assigned customer (%)")
    axis.set_ylabel("Campaign")
    axis.grid(axis="y", visible=False)
    axis.legend(loc="lower right")
    _add_definition(
        figure,
        "Intention-to-treat comparison. Dark bars are statistically significant at FDR 5%; "
        "the dashed line marks the pre-specified practical threshold.",
    )
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_campaign_confidence_intervals(statistics: pd.DataFrame) -> Figure:
    """How precise is each campaign lift estimate?"""
    require_columns(
        statistics,
        (
            "campaign_id",
            "absolute_difference",
            "confidence_interval_low",
            "confidence_interval_high",
        ),
        "plot_campaign_confidence_intervals",
    )
    _require_rows(statistics, "plot_campaign_confidence_intervals")
    frame = (
        statistics.dropna(subset=["absolute_difference"])
        .sort_values("absolute_difference")
        .reset_index(drop=True)
    )

    figure, axis = plt.subplots(figsize=(11.0, max(5.5, 0.34 * len(frame) + 1.6)))
    for position, row in frame.iterrows():
        significant = bool(row.get("statistically_significant", False))
        colour = "#1f4e79" if significant else "#9dc3e6"
        axis.plot(
            [row["confidence_interval_low"], row["confidence_interval_high"]],
            [position, position],
            color=colour,
            linewidth=2.5,
        )
        axis.plot(row["absolute_difference"], position, marker="o", color=colour, markersize=6)
    axis.axvline(0, color="#333333", linewidth=1)
    axis.set_yticks(range(len(frame)))
    axis.set_yticklabels(frame["campaign_id"])
    axis.set_xlabel("Difference in revenue per assigned customer (EUR)")
    axis.set_ylabel("Campaign")
    axis.set_title("Campaign lift with 95% confidence intervals")
    axis.xaxis.set_major_formatter(FuncFormatter(currency_formatter))
    axis.grid(axis="y", visible=False)
    _add_definition(
        figure,
        "Welch 95% confidence intervals on the difference in mean revenue per assigned "
        "customer (treatment minus holdout). Intervals crossing zero are inconclusive.",
    )
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def plot_campaign_significance_overview(statistics: pd.DataFrame) -> Figure:
    """Which campaigns are both statistically and practically significant?"""
    require_columns(
        statistics,
        ("campaign_id", "relative_difference", "adjusted_p_value"),
        "plot_campaign_significance_overview",
    )
    _require_rows(statistics, "plot_campaign_significance_overview")
    from novacart.analytics.campaigns import (
        PRACTICAL_ABSOLUTE_THRESHOLD,
        PRACTICAL_RELATIVE_THRESHOLD,
    )

    frame = statistics.dropna(subset=["adjusted_p_value", "relative_difference"]).copy()
    frame["significance_score"] = -np.log10(frame["adjusted_p_value"].clip(lower=1e-12))

    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    colours = ["#1f4e79" if value else "#9dc3e6" for value in frame["statistically_significant"]]
    sizes = [
        90 if abs(row.absolute_difference) >= PRACTICAL_ABSOLUTE_THRESHOLD else 45
        for row in frame.itertuples()
    ]
    axis.scatter(frame["relative_difference"] * 100, frame["significance_score"], c=colours, s=sizes)
    for row in frame.itertuples():
        axis.annotate(
            row.campaign_id.replace("CMP-", ""),
            (row.relative_difference * 100, row.significance_score),
            textcoords="offset points",
            xytext=(5, 3),
            fontsize=8,
        )
    axis.axvline(PRACTICAL_RELATIVE_THRESHOLD * 100, color="#c55a11", linestyle="--", linewidth=1)
    axis.axhline(-np.log10(0.05), color="#7f7f7f", linestyle=":", linewidth=1)
    axis.set_title("Statistical vs practical significance by campaign")
    axis.set_xlabel("Relative lift vs holdout (%)")
    axis.set_ylabel("Statistical evidence (-log10 of FDR-adjusted p-value)")
    _add_definition(
        figure,
        "Dashed line: 10% practical lift threshold. Dotted line: FDR-adjusted p = 0.05. "
        "Larger markers exceed EUR 5 absolute lift per assigned customer.",
    )
    figure.tight_layout(rect=(0, 0.03, 1, 1))
    return figure


def render_segmentation_figures(
    *,
    segments: pd.DataFrame,
    profile: pd.DataFrame,
    cohort: object,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    """Render the RFM and cohort figures and return the saved paths."""
    figures = {
        "rfm_customer_counts": plot_rfm_segment_customers(segments),
        "rfm_revenue_by_segment": plot_rfm_segment_revenue(segments),
        "rfm_segment_comparison": plot_rfm_segment_comparison(profile),
        "cohort_retention_heatmap": plot_cohort_retention_heatmap(cohort.retention_matrix),
        "cohort_sizes": plot_cohort_sizes(cohort.sizes),
        "cohort_revenue_curve": plot_cohort_revenue_curve(cohort.revenue),
    }
    return {
        key: save_figure(figure, FIGURE_FILENAMES[key], output_dir=output_dir)
        for key, figure in figures.items()
    }


def render_campaign_figures(
    *, statistics: pd.DataFrame, output_dir: Path | None = None
) -> dict[str, Path]:
    """Render the campaign comparison figures and return the saved paths."""
    figures = {
        "campaign_lift_comparison": plot_campaign_lift_comparison(statistics),
        "campaign_confidence_intervals": plot_campaign_confidence_intervals(statistics),
        "campaign_significance_overview": plot_campaign_significance_overview(statistics),
    }
    return {
        key: save_figure(figure, FIGURE_FILENAMES[key], output_dir=output_dir)
        for key, figure in figures.items()
    }

