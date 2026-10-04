"""Static previews of the Power BI pages (Milestone 5, part E).

Power BI Desktop cannot be driven from this environment, so each dashboard page is
also rendered as a static image **from the same exported datasets** that Power BI
loads. The previews are design references and portfolio screenshots; they are not
Power BI screenshots and they contain no metrics that are not already in the
exports.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from novacart.analytics.common import AnalyticsError, require_columns
from novacart.analytics.plots import (
    bar_panel as _bar_panel,
)
from novacart.analytics.plots import (
    count_formatter,
    currency_formatter,
)
from novacart.analytics.plots import (
    line_panel as _line_panel,
)

logger = logging.getLogger(__name__)

PAGE_FILENAMES: dict[str, str] = {
    "executive_overview": "page1_executive_overview.png",
    "customer_analytics": "page2_customer_analytics.png",
    "product_analytics": "page3_product_analytics.png",
    "campaign_analytics": "page4_campaign_analytics.png",
}

PAGE_SIZE = (16.0, 9.0)
PAGE_DPI = 130
ACCENT = "#1f4e79"
ACCENT_LIGHT = "#9dc3e6"
ACCENT_WARM = "#c55a11"
INK = "#1f2933"
MUTED = "#6b7280"


def _style() -> None:
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.22,
            "grid.linestyle": "-",
            "figure.facecolor": "white",
        }
    )


_style()


def _page(title: str, subtitle: str) -> Figure:
    figure = plt.figure(figsize=PAGE_SIZE, dpi=PAGE_DPI)
    figure.suptitle(title, x=0.012, ha="left", fontsize=16, fontweight="bold", color=INK)
    figure.text(0.012, 0.945, subtitle, ha="left", fontsize=9.5, color=MUTED)
    figure.text(
        0.012,
        0.012,
        "Static preview rendered from outputs/dashboard/csv - the same datasets the Power BI "
        "model loads. Revenue = recognised net merchandise revenue (completed orders).",
        ha="left",
        fontsize=7.5,
        color=MUTED,
    )
    return figure


def _kpi_cards(figure: Figure, items: list[tuple[str, str]], *, top: float = 0.845) -> None:
    count = len(items)
    left = 0.02
    width = (1.0 - left - 0.02) / count
    for index, (label, value) in enumerate(items):
        x = left + index * width
        axis = figure.add_axes((x + 0.006, top, width - 0.012, 0.085))
        axis.set_xticks([])
        axis.set_yticks([])
        axis.grid(visible=False)
        for spine in axis.spines.values():
            spine.set_visible(True)
            spine.set_color("#d6dbe1")
        axis.set_facecolor("#f7f9fc")
        axis.text(0.5, 0.66, label.upper(), ha="center", va="center", fontsize=8, color=MUTED)
        axis.text(0.5, 0.28, value, ha="center", va="center", fontsize=14, fontweight="bold", color=ACCENT)


def _table_panel(axis, headers: list[str], rows: list[list[str]], title: str) -> None:
    axis.set_xticks([])
    axis.set_yticks([])
    axis.grid(visible=False)
    for spine in axis.spines.values():
        spine.set_visible(False)
    axis.set_title(title, loc="left")
    table = axis.table(cellText=rows, colLabels=headers, loc="center", cellLoc="left")
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.25)
    for (row, _column), cell in table.get_celld().items():
        cell.set_edgecolor("#e6e9ed")
        if row == 0:
            cell.set_text_props(fontweight="bold", color="white")
            cell.set_facecolor(ACCENT)


def _heatmap(axis, matrix: pd.DataFrame, title: str) -> None:
    values = np.ma.masked_invalid(matrix.to_numpy(dtype="float64"))
    colour_map = plt.get_cmap("Blues").with_extremes(bad="#f0f0f0")
    axis.imshow(values, aspect="auto", cmap=colour_map, vmin=0.0, vmax=1.0)
    axis.set_xticks(range(matrix.shape[1]))
    axis.set_xticklabels([str(column) for column in matrix.columns], fontsize=8)
    axis.set_yticks(range(matrix.shape[0]))
    axis.set_yticklabels(
        [timestamp.strftime("%Y-%m") for timestamp in pd.to_datetime(matrix.index)], fontsize=7.5
    )
    axis.set_xlabel("Months since first purchase", fontsize=8.5)
    axis.set_title(title, loc="left")
    axis.grid(visible=False)


def _require(frame: pd.DataFrame, columns: tuple[str, ...], purpose: str) -> None:
    if frame is None or frame.empty:
        raise AnalyticsError(f"{purpose} needs a non-empty dashboard dataset")
    require_columns(frame, columns, purpose)


def _require_datasets(frames: dict[str, pd.DataFrame], names: tuple[str, ...], purpose: str) -> None:
    """Fail with a clear message when a required dashboard dataset is missing."""
    missing = [
        name for name in names if name not in frames or frames[name] is None or frames[name].empty
    ]
    if missing:
        raise AnalyticsError(f"{purpose} is missing dashboard dataset(s): {', '.join(missing)}")


def draw_executive_overview(frames: dict[str, pd.DataFrame]) -> Figure:
    """Page 1: headline KPIs with revenue, orders, category, country, segment and campaign panels."""
    _require_datasets(
        frames,
        (
            "kpi_summary",
            "monthly_revenue",
            "category_performance",
            "country_performance",
            "customer_segments",
            "campaign_results",
        ),
        "executive overview",
    )
    kpis = frames["kpi_summary"]
    monthly = frames["monthly_revenue"]
    categories = frames["category_performance"]
    countries = frames["country_performance"]
    segments = frames["customer_segments"]
    campaigns = frames["campaign_results"]
    _require(kpis, ("total_revenue", "total_orders", "unique_customers"), "executive overview")

    figure = _page(
        "NovaCart - Executive overview",
        "Power BI page 1 design preview  |  24 months of trading  |  page filters: month, country, category, segment",
    )
    kpi = kpis.iloc[0]
    _kpi_cards(
        figure,
        [
            ("Net revenue", currency_formatter(kpi["total_revenue"])),
            ("Orders", f"{kpi['total_orders']:,.0f}"),
            ("Customers", f"{kpi['unique_customers']:,.0f}"),
            ("AOV", f"€{kpi['average_order_value']:,.2f}"),
            ("Repeat rate", f"{kpi['repeat_customer_rate']:.1%}"),
            ("Revenue / customer", f"€{kpi['revenue_per_customer']:,.0f}"),
        ],
    )

    grid = figure.add_gridspec(
        2, 3, left=0.055, right=0.985, top=0.80, bottom=0.09, hspace=0.55, wspace=0.28
    )
    monthly = monthly.sort_values("month_start")
    _line_panel(
        figure.add_subplot(grid[0, 0]),
        list(monthly["year_month"]),
        monthly["revenue"].to_numpy(),
        "Monthly net revenue",
    )
    _bar_panel(
        figure.add_subplot(grid[0, 1]),
        list(monthly["year_month"]),
        monthly["orders_recognised"].to_numpy(),
        "Orders per month",
        horizontal=False,
        formatter=count_formatter,
        annotate=False,
    )
    top_categories = categories.sort_values("revenue", ascending=True)
    _bar_panel(
        figure.add_subplot(grid[0, 2]),
        list(top_categories["category"]),
        top_categories["revenue"].to_numpy(),
        "Revenue by category",
    )

    top_countries = countries.sort_values("revenue", ascending=False).head(10).sort_values("revenue")
    _bar_panel(
        figure.add_subplot(grid[1, 0]),
        list(top_countries["country_code"]),
        top_countries["revenue"].to_numpy(),
        "Revenue by country (top 10)",
    )
    segment_view = segments.loc[segments["revenue"] > 0].sort_values("revenue")
    _bar_panel(
        figure.add_subplot(grid[1, 1]),
        list(segment_view["rfm_segment"]),
        segment_view["revenue"].to_numpy(),
        "Revenue by customer segment",
    )
    campaign_view = campaigns.sort_values("absolute_difference", ascending=False).head(10).sort_values(
        "absolute_difference"
    )
    colours = [
        ACCENT if significant else ACCENT_LIGHT
        for significant in campaign_view["statistically_significant"]
    ]
    _bar_panel(
        figure.add_subplot(grid[1, 2]),
        list(campaign_view["campaign_id"]),
        campaign_view["absolute_difference"].to_numpy(),
        "Campaign lift vs holdout (EUR per customer)",
        colors=colours,
    )
    return figure


def draw_customer_analytics(frames: dict[str, pd.DataFrame]) -> Figure:
    """Page 2: RFM distribution, revenue by segment, value deciles and cohort views."""
    _require_datasets(
        frames,
        ("customer_segments", "customer_value_deciles", "cohort_retention", "cohort_sizes"),
        "customer analytics",
    )
    segments = frames["customer_segments"]
    deciles = frames["customer_value_deciles"]
    retention = frames["cohort_retention"]
    sizes = frames["cohort_sizes"]
    _require(segments, ("rfm_segment", "customers", "revenue"), "customer analytics")

    figure = _page(
        "NovaCart - Customer analytics",
        "Power BI page 2 design preview  |  RFM segments, customer value distribution and cohort retention",
    )
    grid = figure.add_gridspec(
        2, 3, left=0.055, right=0.985, top=0.86, bottom=0.09, hspace=0.5, wspace=0.28
    )

    by_customers = segments.sort_values("customers")
    _bar_panel(
        figure.add_subplot(grid[0, 0]),
        list(by_customers["rfm_segment"]),
        by_customers["customers"].to_numpy(),
        "Customers by RFM segment",
        formatter=count_formatter,
    )
    by_revenue = segments.loc[segments["revenue"] > 0].sort_values("revenue")
    _bar_panel(
        figure.add_subplot(grid[0, 1]),
        list(by_revenue["rfm_segment"]),
        by_revenue["revenue"].to_numpy(),
        "Revenue by RFM segment",
    )
    _bar_panel(
        figure.add_subplot(grid[0, 2]),
        [str(int(value)) for value in deciles["revenue_decile"]],
        deciles["revenue_share_pct"].to_numpy(),
        "Revenue share by customer decile (%)",
        horizontal=False,
        formatter=lambda value, _position=None: f"{value:.0f}%",
        annotate=False,
    )

    matrix = retention.pivot(
        index="cohort_month", columns="month_offset", values="retention_rate"
    ).sort_index()
    _heatmap(figure.add_subplot(grid[1, 0:2]), matrix, "Cohort retention by month offset")
    sizes_sorted = sizes.sort_values("cohort_month")
    labels = [str(pd.Timestamp(value).strftime("%Y-%m")) for value in sizes_sorted["cohort_month"]]
    _bar_panel(
        figure.add_subplot(grid[1, 2]),
        labels,
        sizes_sorted["cohort_size"].to_numpy(),
        "Customers per acquisition cohort",
        horizontal=False,
        formatter=count_formatter,
        annotate=False,
    )
    return figure


def draw_product_analytics(frames: dict[str, pd.DataFrame]) -> Figure:
    """Page 3: category revenue and units, top products and declining products."""
    _require_datasets(
        frames,
        ("category_performance", "product_performance"),
        "product analytics",
    )
    categories = frames["category_performance"]
    products = frames["product_performance"]
    declining = frames["declining_products"]
    _require(categories, ("category", "revenue", "units"), "product analytics")

    figure = _page(
        "NovaCart - Product analytics",
        "Power BI page 3 design preview  |  category mix, top products and declining products",
    )
    grid = figure.add_gridspec(
        2, 3, left=0.075, right=0.985, top=0.86, bottom=0.09, hspace=0.55, wspace=0.4
    )

    ordered = categories.sort_values("revenue")
    _bar_panel(
        figure.add_subplot(grid[0, 0]),
        list(ordered["category"]),
        ordered["revenue"].to_numpy(),
        "Revenue by category",
    )
    by_units = categories.sort_values("units")
    _bar_panel(
        figure.add_subplot(grid[0, 1]),
        list(by_units["category"]),
        by_units["units"].to_numpy(),
        "Units by category",
        formatter=count_formatter,
    )
    top_products = products.sort_values("revenue", ascending=False).head(10).sort_values("revenue")
    labels = [
        name if len(name) <= 30 else f"{name[:27]}..." for name in top_products["product_name"]
    ]
    _bar_panel(
        figure.add_subplot(grid[1, 0:2]),
        labels,
        top_products["revenue"].to_numpy(),
        "Top 10 products by revenue",
    )
    decline_axis = figure.add_subplot(grid[1, 2])
    flagged = (
        declining.loc[declining["is_declining"]].sort_values("units_change_pct").head(10)
        if declining is not None and not declining.empty
        else declining
    )
    if flagged is None or flagged.empty:
        # A small window (or a filtered selection) can legitimately have no product
        # meeting the decline rule; show that explicitly rather than an empty chart.
        decline_axis.set_xticks([])
        decline_axis.set_yticks([])
        decline_axis.grid(visible=False)
        decline_axis.set_title("Declining products (unit change %)", loc="left")
        decline_axis.text(
            0.5,
            0.5,
            "No product met the decline rule\n(prior units >= 10 and unit change <= -30%)",
            ha="center",
            va="center",
            fontsize=9,
            color=MUTED,
            transform=decline_axis.transAxes,
        )
    else:
        flagged = flagged.sort_values("units_change_pct", ascending=False)
        decline_labels = [
            name if len(name) <= 26 else f"{name[:23]}..." for name in flagged["product_name"]
        ]
        _bar_panel(
            decline_axis,
            decline_labels,
            flagged["units_change_pct"].to_numpy() * 100,
            "Declining products (unit change %)",
            formatter=lambda value, _position=None: f"{value:.0f}%",
        )
    return figure


def draw_campaign_analytics(frames: dict[str, pd.DataFrame]) -> Figure:
    """Page 4: treatment vs holdout results, lift, confidence intervals and significance."""
    _require_datasets(frames, ("campaign_results",), "campaign analytics")
    campaigns = frames["campaign_results"]
    _require(
        campaigns,
        ("campaign_id", "absolute_difference", "relative_difference", "confidence_interval_low"),
        "campaign analytics",
    )

    figure = _page(
        "NovaCart - Campaign analytics",
        "Power BI page 4 design preview  |  intention-to-treat comparison with 95% confidence intervals and FDR control",
    )
    grid = figure.add_gridspec(
        2, 3, left=0.055, right=0.985, top=0.86, bottom=0.09, hspace=0.45, wspace=0.3
    )

    lift = campaigns.sort_values("relative_difference")
    colours = [
        ACCENT if significant else ACCENT_LIGHT for significant in lift["statistically_significant"]
    ]
    _bar_panel(
        figure.add_subplot(grid[0, 0]),
        list(lift["campaign_id"]),
        lift["relative_difference"].to_numpy() * 100,
        "Relative lift vs holdout (%)",
        colors=colours,
        formatter=lambda value, _position=None: f"{value:.0f}%",
        annotate=False,
    )

    intervals = campaigns.sort_values("absolute_difference").reset_index(drop=True)
    axis = figure.add_subplot(grid[0, 1])
    for position, row in intervals.iterrows():
        colour = ACCENT if row["statistically_significant"] else ACCENT_LIGHT
        axis.plot(
            [row["confidence_interval_low"], row["confidence_interval_high"]],
            [position, position],
            color=colour,
            linewidth=2.2,
        )
        axis.plot(row["absolute_difference"], position, marker="o", color=colour, markersize=4)
    axis.axvline(0, color=INK, linewidth=1)
    axis.set_yticks(range(len(intervals)))
    axis.set_yticklabels(intervals["campaign_id"], fontsize=7.5)
    axis.xaxis.set_major_formatter(plt.FuncFormatter(currency_formatter))
    axis.set_title("Lift with 95% confidence intervals", loc="left")
    axis.grid(axis="y", visible=False)

    axis = figure.add_subplot(grid[0, 2])
    significant = campaigns["statistically_significant"]
    scores = -np.log10(campaigns["adjusted_p_value"].clip(lower=1e-12))
    axis.scatter(
        campaigns["relative_difference"] * 100,
        scores,
        c=[ACCENT if value else ACCENT_LIGHT for value in significant],
        s=60,
    )
    for row in campaigns.itertuples():
        axis.annotate(
            row.campaign_id.replace("CMP-", ""),
            (row.relative_difference * 100, -np.log10(max(row.adjusted_p_value, 1e-12))),
            textcoords="offset points",
            xytext=(4, 3),
            fontsize=7,
        )
    axis.axvline(10, color=ACCENT_WARM, linestyle="--", linewidth=1)
    axis.axhline(-np.log10(0.05), color=MUTED, linestyle=":", linewidth=1)
    axis.set_title("Evidence vs practical lift", loc="left")
    axis.set_xlabel("Relative lift (%)", fontsize=8.5)
    axis.set_ylabel("-log10 adjusted p", fontsize=8.5)

    table_rows = [
        [
            row.campaign_id,
            f"{row.treatment_n:,.0f}",
            f"{row.control_n:,.0f}",
            f"{row.absolute_difference:+,.2f}",
            f"{row.relative_difference:+.1%}",
            f"{row.adjusted_p_value:.4g}",
            "yes" if row.statistically_significant else "no",
            row.effect_size_label,
        ]
        for row in campaigns.sort_values("absolute_difference", ascending=False).head(10).itertuples()
    ]
    _table_panel(
        figure.add_subplot(grid[1, 0:3]),
        ["Campaign", "Treat n", "Holdout n", "Lift EUR", "Lift %", "Adj. p", "Significant", "Effect"],
        table_rows,
        "Campaign results (top 10 by absolute lift)",
    )
    return figure


DRAWERS = {
    "executive_overview": draw_executive_overview,
    "customer_analytics": draw_customer_analytics,
    "product_analytics": draw_product_analytics,
    "campaign_analytics": draw_campaign_analytics,
}


def render_dashboard_previews(
    frames: dict[str, pd.DataFrame], *, output_dir: Path
) -> dict[str, Path]:
    """Render all four page previews and return the saved paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, drawer in DRAWERS.items():
        figure = drawer(frames)
        path = output_dir / PAGE_FILENAMES[name]
        figure.savefig(path, dpi=PAGE_DPI, bbox_inches="tight", facecolor="white")
        plt.close(figure)
        paths[name] = path
        logger.debug("Rendered dashboard preview %s", path)
    return paths

