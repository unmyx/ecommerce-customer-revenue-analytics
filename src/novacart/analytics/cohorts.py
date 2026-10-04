"""Monthly cohort retention analysis (Milestone 4, part B).

Definitions
    * A customer's cohort is the calendar month of their **first recognised
      order** (``min(order_month)`` per customer).
    * ``month_offset`` is the number of whole months between the cohort month and
      the activity month: ``(year difference * 12) + month difference``. Month 0
      is therefore the acquisition month by construction, so month 0 retention is
      always 100% of the cohort.
    * A customer is *retained* in offset *k* when they placed at least one
      recognised order in that month. Retention is the share of the cohort
      retained, so it can never exceed 1.
    * Offsets beyond the analysis end date are not observable and are omitted
      (left as NaN in the wide matrix) rather than reported as zero.

The analysis end date is fixed and documented: it is the last order date of the
loaded window (``analytics.analysis_window.analysis_end_date``, 2026-09-30 in the
default dataset) and never the wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from novacart.analytics.common import (
    ORDER_REVENUE_COLUMN,
    empty_frame,
    recognised,
    require_columns,
    resolve_column,
    safe_divide,
)

SIZE_COLUMNS = (
    "cohort_index",
    "cohort_month",
    "cohort_size",
    "months_observed",
    "total_revenue",
    "revenue_per_customer",
    "repeat_customers",
    "repeat_customer_rate",
)

RETENTION_COLUMNS = (
    "cohort_index",
    "cohort_month",
    "month_offset",
    "cohort_size",
    "retained_customers",
    "retention_rate",
)

REVENUE_COLUMNS = (
    "cohort_index",
    "cohort_month",
    "month_offset",
    "cohort_size",
    "revenue",
    "cumulative_revenue",
    "revenue_per_cohort_customer",
)


@dataclass(frozen=True)
class CohortAnalysis:
    """Cohort outputs: sizes, long retention, wide retention matrix and revenue."""

    sizes: pd.DataFrame
    retention: pd.DataFrame
    retention_matrix: pd.DataFrame
    revenue: pd.DataFrame


def _month_index(values: pd.Series) -> pd.Series:
    return values.dt.year * 12 + values.dt.month


def customer_cohorts(
    orders: pd.DataFrame, *, analysis_end_date: str | pd.Timestamp | None = None
) -> pd.DataFrame:
    """Customer-level cohort assignment with the months observable to date."""
    require_columns(orders, ("customer_id", "order_month"), "customer_cohorts")
    frame = recognised(orders)
    if frame.empty:
        return empty_frame(
            ["customer_id", "cohort_month", "cohort_index", "months_observed", "total_revenue"]
        )

    frame = frame.copy()
    frame["order_month"] = pd.to_datetime(frame["order_month"]).dt.to_period("M").dt.to_timestamp()
    revenue_col = resolve_column(frame, (ORDER_REVENUE_COLUMN, "net_revenue"), "customer_cohorts")

    cohorts = frame.groupby("customer_id", as_index=False).agg(
        cohort_month=("order_month", "min"),
        total_revenue=(revenue_col, "sum"),
        total_orders=("order_id", "nunique") if "order_id" in frame.columns else ("order_month", "size"),
    )

    end_date = (
        pd.Timestamp(analysis_end_date).to_period("M").to_timestamp()
        if analysis_end_date is not None
        else frame["order_month"].max()
    )
    months_observed = (
        (end_date.year - cohorts["cohort_month"].dt.year) * 12
        + (end_date.month - cohorts["cohort_month"].dt.month)
        + 1
    )
    cohort_months = sorted(cohorts["cohort_month"].unique())
    index_by_month = {month: index for index, month in enumerate(cohort_months)}

    cohorts["cohort_index"] = cohorts["cohort_month"].map(index_by_month)
    cohorts["months_observed"] = months_observed.astype("int64")
    cohorts["repeat_customers"] = (cohorts["total_orders"] >= 2).astype("int64")
    return cohorts.sort_values(["cohort_index", "customer_id"]).reset_index(drop=True)


def cohort_analysis(
    orders: pd.DataFrame, *, analysis_end_date: str | pd.Timestamp | None = None
) -> CohortAnalysis:
    """Full cohort analysis: sizes, retention (long + wide) and revenue."""
    require_columns(orders, ("customer_id", "order_month"), "cohort_analysis")
    frame = recognised(orders)
    if frame.empty:
        return CohortAnalysis(
            sizes=empty_frame(SIZE_COLUMNS),
            retention=empty_frame(RETENTION_COLUMNS),
            retention_matrix=pd.DataFrame(),
            revenue=empty_frame(REVENUE_COLUMNS),
        )

    frame = frame.copy()
    frame["order_month"] = pd.to_datetime(frame["order_month"]).dt.to_period("M").dt.to_timestamp()
    revenue_col = resolve_column(frame, (ORDER_REVENUE_COLUMN, "net_revenue"), "cohort_analysis")

    cohorts = customer_cohorts(orders, analysis_end_date=analysis_end_date)
    activity = frame.merge(
        cohorts[["customer_id", "cohort_month", "cohort_index", "months_observed"]],
        on="customer_id",
        how="inner",
    )
    activity["month_offset"] = _month_index(activity["order_month"]) - _month_index(
        activity["cohort_month"]
    )

    # Complete grid: every cohort x every observable offset.
    cohort_level = cohorts.groupby(["cohort_index", "cohort_month"], as_index=False).agg(
        months_observed=("months_observed", "max")
    )
    grid_rows = [
        {
            "cohort_index": int(row.cohort_index),
            "cohort_month": row.cohort_month,
            "month_offset": offset,
        }
        for row in cohort_level.itertuples()
        for offset in range(int(row.months_observed))
    ]
    grid = pd.DataFrame(grid_rows)
    sizes_by_cohort = cohorts.groupby("cohort_index").agg(
        cohort_size=("customer_id", "count"),
        total_revenue=("total_revenue", "sum"),
        repeat_customers=("repeat_customers", "sum"),
    )
    sizes_by_cohort["total_revenue"] = sizes_by_cohort["total_revenue"].round(2)
    sizes_by_cohort["revenue_per_customer"] = safe_divide(
        sizes_by_cohort["total_revenue"], sizes_by_cohort["cohort_size"]
    ).round(2)
    sizes_by_cohort["repeat_customer_rate"] = safe_divide(
        sizes_by_cohort["repeat_customers"], sizes_by_cohort["cohort_size"]
    ).round(4)

    activity_counts = (
        activity.groupby(["cohort_index", "month_offset"], as_index=False)
        .agg(
            retained_customers=("customer_id", "nunique"),
            revenue=(revenue_col, "sum"),
        )
    )

    retention = grid.merge(activity_counts, on=["cohort_index", "month_offset"], how="left")
    retention = retention.merge(
        sizes_by_cohort[["cohort_size"]], left_on="cohort_index", right_index=True, how="left"
    )
    retention["retained_customers"] = retention["retained_customers"].fillna(0).astype("int64")
    retention["revenue"] = retention["revenue"].fillna(0.0).round(2)
    retention["retention_rate"] = safe_divide(
        retention["retained_customers"], retention["cohort_size"]
    ).round(4)

    revenue = retention[
        ["cohort_index", "cohort_month", "month_offset", "cohort_size", "revenue"]
    ].copy()
    revenue["cumulative_revenue"] = (
        revenue.sort_values(["cohort_index", "month_offset"])
        .groupby("cohort_index")["revenue"]
        .cumsum()
        .round(2)
    )
    revenue["revenue_per_cohort_customer"] = safe_divide(
        revenue["revenue"], revenue["cohort_size"]
    ).round(2)

    sizes = (
        cohorts.groupby(["cohort_index", "cohort_month"], as_index=False)
        .agg(cohort_size=("customer_id", "count"), months_observed=("months_observed", "max"))
        .merge(
            sizes_by_cohort[["total_revenue", "revenue_per_customer", "repeat_customers", "repeat_customer_rate"]],
            left_on="cohort_index",
            right_index=True,
            how="left",
        )
    )
    sizes["cohort_month"] = pd.to_datetime(sizes["cohort_month"])

    retention_matrix = (
        retention.pivot(index="cohort_month", columns="month_offset", values="retention_rate")
        .sort_index()
    )
    retention_matrix.index.name = "cohort_month"
    retention_matrix.columns.name = "month_offset"

    return CohortAnalysis(
        sizes=sizes[list(SIZE_COLUMNS)].sort_values("cohort_index").reset_index(drop=True),
        retention=retention[list(RETENTION_COLUMNS)]
        .sort_values(["cohort_index", "month_offset"])
        .reset_index(drop=True),
        retention_matrix=retention_matrix,
        revenue=revenue[list(REVENUE_COLUMNS)]
        .sort_values(["cohort_index", "month_offset"])
        .reset_index(drop=True),
    )


def validate_retention(retention: pd.DataFrame, sizes: pd.DataFrame) -> None:
    """Raise when a retention table violates its mathematical invariants."""
    if retention.empty:
        return
    month_zero = retention.loc[retention["month_offset"] == 0, "retention_rate"]
    if not np.allclose(month_zero.to_numpy(), 1.0, atol=1e-9):
        raise ValueError("month 0 retention must equal 100% of the cohort")
    if retention["retention_rate"].gt(1.0 + 1e-9).any():
        raise ValueError("retention rate cannot exceed 100%")
    if retention["retained_customers"].lt(0).any():
        raise ValueError("retained customer counts cannot be negative")
    counts = retention.groupby("cohort_index")["cohort_size"].nunique()
    if (counts != 1).any():
        raise ValueError("cohort size must be constant within a cohort")

