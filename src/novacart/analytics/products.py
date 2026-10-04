"""Product and category analytics (Milestone 3, part C)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from novacart.analytics.common import (
    LINE_REVENUE_COLUMN,
    AnalyticsError,
    empty_frame,
    percentage_change,
    recognised,
    require_columns,
    resolve_column,
    safe_divide,
)

#: Declining-product rule (documented in the README).
#:
#: A product is "declining" when, comparing the most recent ``window_days`` of the
#: analysis window with the ``window_days`` immediately before it:
#:   * it sold at least ``DECLINE_MIN_PRIOR_UNITS`` units in the prior window
#:     (so a single lost sale cannot trigger a signal), and
#:   * its recognised unit sales fell by at least ``DECLINE_SHARE`` (30%).
DECLINE_WINDOW_DAYS = 90
DECLINE_MIN_PRIOR_UNITS = 10
DECLINE_SHARE = 0.30

CATEGORY_COLUMNS = (
    "category",
    "revenue",
    "units",
    "orders",
    "customers",
    "average_selling_price",
    "revenue_share_pct",
)

PRODUCT_COLUMNS = (
    "product_id",
    "product_name",
    "brand",
    "category",
    "revenue",
    "units",
    "orders",
    "customers",
    "average_selling_price",
    "revenue_share_pct",
)

DECLINING_COLUMNS = (
    "product_id",
    "product_name",
    "category",
    "prior_units",
    "recent_units",
    "prior_revenue",
    "recent_revenue",
    "units_change",
    "units_change_pct",
    "revenue_change_pct",
    "is_declining",
)


def _line_totals(lines: pd.DataFrame, keys: list[str], purpose: str) -> pd.DataFrame:
    require_columns(lines, ("order_id", "customer_id"), purpose)
    revenue_col = resolve_column(lines, (LINE_REVENUE_COLUMN, "line_net_revenue"), purpose)
    units_col = resolve_column(lines, ("recognised_units", "quantity"), purpose)
    recognised_lines = recognised(lines)
    if recognised_lines.empty:
        return empty_frame(keys + ["orders", "customers", "units", "revenue"])

    return recognised_lines.groupby(keys, as_index=False).agg(
        orders=("order_id", "nunique"),
        customers=("customer_id", "nunique"),
        units=(units_col, "sum"),
        revenue=(revenue_col, "sum"),
    )


def category_summary(lines: pd.DataFrame) -> pd.DataFrame:
    """Revenue, units, orders, customers and realised price per category."""
    require_columns(lines, ("category",), "category_summary")
    totals = _line_totals(lines, ["category"], "category_summary")
    if totals.empty:
        return empty_frame(CATEGORY_COLUMNS)

    totals["revenue"] = totals["revenue"].round(2)
    totals["units"] = totals["units"].astype("int64")
    totals["average_selling_price"] = safe_divide(totals["revenue"], totals["units"]).round(2)
    totals["revenue_share_pct"] = (
        safe_divide(totals["revenue"], float(totals["revenue"].sum())) * 100
    ).round(4)
    return totals[list(CATEGORY_COLUMNS)].sort_values(
        ["revenue", "category"], ascending=[False, True]
    ).reset_index(drop=True)


def product_summary(lines: pd.DataFrame) -> pd.DataFrame:
    """Revenue, units, orders, customers and realised price per product."""
    require_columns(lines, ("product_id",), "product_summary")
    totals = _line_totals(lines, ["product_id"], "product_summary")
    if totals.empty:
        return empty_frame(PRODUCT_COLUMNS)

    attributes = (
        lines.loc[:, ["product_id", "product_name", "brand", "category"]]
        .drop_duplicates("product_id")
    )
    summary = totals.merge(attributes, on="product_id", how="left")
    summary["revenue"] = summary["revenue"].round(2)
    summary["units"] = summary["units"].astype("int64")
    summary["average_selling_price"] = safe_divide(summary["revenue"], summary["units"]).round(2)
    summary["revenue_share_pct"] = (
        safe_divide(summary["revenue"], float(summary["revenue"].sum())) * 100
    ).round(4)
    return summary[list(PRODUCT_COLUMNS)].sort_values(
        ["revenue", "product_id"], ascending=[False, True]
    ).reset_index(drop=True)


def top_products_by_revenue(products: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top ``n`` products by recognised revenue (ties broken by product_id)."""
    require_columns(products, ("product_id", "revenue"), "top_products_by_revenue")
    if n <= 0:
        raise AnalyticsError("n must be positive")
    return (
        products.sort_values(["revenue", "product_id"], ascending=[False, True])
        .head(n)
        .reset_index(drop=True)
    )


def top_products_by_units(products: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top ``n`` products by recognised units sold (ties broken by product_id)."""
    require_columns(products, ("product_id", "units"), "top_products_by_units")
    if n <= 0:
        raise AnalyticsError("n must be positive")
    return (
        products.sort_values(["units", "product_id"], ascending=[False, True])
        .head(n)
        .reset_index(drop=True)
    )


def _window_totals(
    lines: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, label: str
) -> pd.DataFrame:
    window = lines.loc[(lines["order_date"] >= start) & (lines["order_date"] <= end)]
    units_col = resolve_column(lines, ("recognised_units", "quantity"), "declining_products")
    revenue_col = resolve_column(
        lines, (LINE_REVENUE_COLUMN, "line_net_revenue"), "declining_products"
    )
    if window.empty:
        return empty_frame(["product_id", f"{label}_units", f"{label}_revenue"])
    return window.groupby("product_id", as_index=False).agg(
        **{
            f"{label}_units": (units_col, "sum"),
            f"{label}_revenue": (revenue_col, "sum"),
        }
    )


def declining_products(
    lines: pd.DataFrame,
    *,
    as_of: date | str | pd.Timestamp | None = None,
    window_days: int = DECLINE_WINDOW_DAYS,
    min_prior_units: int = DECLINE_MIN_PRIOR_UNITS,
    decline_share: float = DECLINE_SHARE,
) -> pd.DataFrame:
    """Products whose recent recognised unit sales fell sharply.

    The two comparison windows are ``window_days`` long and do not overlap:

        recent: (as_of - window_days + 1) .. as_of
        prior : (as_of - 2 * window_days) .. (as_of - window_days)

    ``as_of`` defaults to the latest ``order_date`` in the data, never the wall
    clock, so results are reproducible. Only products with at least
    ``min_prior_units`` units in the prior window are reported, and a product is
    flagged ``is_declining`` when its unit change is at or below ``-decline_share``.
    """
    require_columns(
        lines,
        ("product_id", "order_date", "recognised_units"),
        "declining_products",
    )
    if window_days <= 0:
        raise AnalyticsError("window_days must be positive")
    if not 0 < decline_share <= 1:
        raise AnalyticsError("decline_share must be in (0, 1]")

    frame = recognised(lines).copy()
    frame["order_date"] = pd.to_datetime(frame["order_date"]).dt.normalize()
    if frame.empty:
        return empty_frame(DECLINING_COLUMNS)

    as_of_date = (
        pd.Timestamp(as_of).normalize() if as_of is not None else frame["order_date"].max()
    )
    recent_start = as_of_date - pd.Timedelta(days=window_days - 1)
    prior_end = recent_start - pd.Timedelta(days=1)
    prior_start = prior_end - pd.Timedelta(days=window_days - 1)

    recent = _window_totals(frame, recent_start, as_of_date, "recent")
    prior = _window_totals(frame, prior_start, prior_end, "prior")
    if prior.empty:
        return empty_frame(DECLINING_COLUMNS)

    comparison = prior.merge(recent, on="product_id", how="left")
    comparison["recent_units"] = comparison["recent_units"].fillna(0).astype("int64")
    comparison["recent_revenue"] = comparison["recent_revenue"].fillna(0.0).round(2)
    comparison["prior_units"] = comparison["prior_units"].astype("int64")
    comparison["prior_revenue"] = comparison["prior_revenue"].round(2)

    comparison = comparison.loc[comparison["prior_units"] >= min_prior_units].copy()
    if comparison.empty:
        return empty_frame(DECLINING_COLUMNS)

    comparison["units_change"] = comparison["recent_units"] - comparison["prior_units"]
    comparison["units_change_pct"] = pd.Series(
        percentage_change(comparison["recent_units"], comparison["prior_units"]),
        index=comparison.index,
    ).round(4)
    comparison["revenue_change_pct"] = pd.Series(
        percentage_change(comparison["recent_revenue"], comparison["prior_revenue"]),
        index=comparison.index,
    ).round(4)
    comparison["is_declining"] = comparison["units_change_pct"] <= -decline_share

    attributes = (
        frame.loc[:, ["product_id", "product_name", "category"]]
        .drop_duplicates("product_id")
    )
    comparison = comparison.merge(attributes, on="product_id", how="left")
    return comparison[list(DECLINING_COLUMNS)].sort_values(
        ["is_declining", "units_change_pct", "product_id"], ascending=[False, True, True]
    ).reset_index(drop=True)

