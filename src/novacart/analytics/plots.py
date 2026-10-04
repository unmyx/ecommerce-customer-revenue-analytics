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

FIGURE_FILENAMES: dict[str, str] = {
    "monthly_revenue": "monthly_revenue_trend.png",
    "monthly_orders": "monthly_orders_trend.png",
    "monthly_aov": "monthly_aov_trend.png",
    "revenue_by_category": "revenue_by_category.png",
    "top_products_by_revenue": "top10_products_by_revenue.png",
    "customer_revenue_distribution": "customer_revenue_distribution.png",
    "revenue_by_country": "revenue_by_country.png",
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


def _currency_formatter(value: float, _position: float | None = None) -> str:
    if abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:.1f}m"
    if abs(value) >= 1_000:
        return f"€{value / 1_000:.0f}k"
    return f"€{value:.0f}"


def _count_formatter(value: float, _position: float | None = None) -> str:
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
    axis.yaxis.set_major_formatter(FuncFormatter(_currency_formatter))
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
    axis.yaxis.set_major_formatter(FuncFormatter(_count_formatter))
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
    axis.yaxis.set_major_formatter(FuncFormatter(_currency_formatter))
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
    axis.xaxis.set_major_formatter(FuncFormatter(_currency_formatter))
    axis.grid(axis="y", visible=False)
    total = float(frame["revenue"].sum())
    for position, value in enumerate(frame["revenue"]):
        share = (value / total) if total else np.nan
        axis.text(
            value,
            position,
            f"  {_currency_formatter(value)} ({share:.1%})",
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
    axis.xaxis.set_major_formatter(FuncFormatter(_currency_formatter))
    axis.grid(axis="y", visible=False)
    for position, value in enumerate(frame["revenue"]):
        axis.text(value, position, f"  {_currency_formatter(value)}", va="center", fontsize=9)
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
    left.xaxis.set_major_formatter(FuncFormatter(_currency_formatter))
    left.yaxis.set_major_formatter(FuncFormatter(_count_formatter))

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
    axis.xaxis.set_major_formatter(FuncFormatter(_currency_formatter))
    axis.grid(axis="y", visible=False)
    for position, value in enumerate(frame["revenue"]):
        axis.text(value, position, f"  {_currency_formatter(value)}", va="center", fontsize=9)
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

