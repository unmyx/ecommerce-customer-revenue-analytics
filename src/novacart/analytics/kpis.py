"""The canonical business KPI snapshot (Milestone 3, part E)."""

from __future__ import annotations

import pandas as pd

from novacart.analytics.common import (
    format_compact_currency,
    format_count,
    format_percent,
    require_columns,
    safe_divide,
)
from novacart.analytics.revenue import revenue_summary

KPI_COLUMNS = (
    "period_start",
    "period_end",
    "days_in_period",
    "total_revenue",
    "total_orders",
    "total_units",
    "unique_customers",
    "average_order_value",
    "average_units_per_order",
    "revenue_per_customer",
    "repeat_customers",
    "one_time_customers",
    "repeat_customer_rate",
    "registered_customers",
    "revenue_per_registered_customer",
)


def business_kpi_snapshot(orders: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """One-row KPI table for the loaded analysis window.

    Definitions (see README):

    * revenue and order metrics come from revenue-recognised orders;
    * ``unique_customers`` counts customers with at least one recognised order;
    * ``repeat_customer_rate`` is repeat customers / purchasing customers, taken
      from ``mart_customer_features`` where available so the dashboard, the
      notebook and SQL all quote the same number;
    * ``revenue_per_customer`` uses purchasing customers, while
      ``revenue_per_registered_customer`` uses every registered customer
      (including those who never bought) - both are exposed rather than blended.
    """
    summary = revenue_summary(orders).iloc[0]

    registered_customers = len(customers)
    purchasing_customers = int(summary["unique_customers"])
    repeat_customers = int(summary["repeat_customers"])
    one_time_customers = int(summary["one_time_customers"])

    if not customers.empty:
        require_columns(customers, ("has_purchased", "repeat_customer"), "business_kpi_snapshot")
        purchasing_customers = int(customers["has_purchased"].fillna(False).astype(bool).sum())
        repeat_customers = int(customers["repeat_customer"].fillna(False).astype(bool).sum())
        one_time_customers = max(purchasing_customers - repeat_customers, 0)

    total_revenue = float(summary["total_revenue"])
    period_start = summary["period_start"]
    period_end = summary["period_end"]
    days_in_period = (
        int((pd.Timestamp(period_end) - pd.Timestamp(period_start)).days) + 1
        if pd.notna(period_start) and pd.notna(period_end)
        else 0
    )

    snapshot = {
        "period_start": period_start,
        "period_end": period_end,
        "days_in_period": days_in_period,
        "total_revenue": round(total_revenue, 2),
        "total_orders": int(summary["total_orders"]),
        "total_units": int(summary["total_units"]),
        "unique_customers": purchasing_customers,
        "average_order_value": summary["average_order_value"],
        "average_units_per_order": summary["average_units_per_order"],
        "revenue_per_customer": round(safe_divide(total_revenue, purchasing_customers), 2),
        "repeat_customers": repeat_customers,
        "one_time_customers": one_time_customers,
        "repeat_customer_rate": round(safe_divide(repeat_customers, purchasing_customers), 4),
        "registered_customers": registered_customers,
        "revenue_per_registered_customer": round(
            safe_divide(total_revenue, registered_customers), 2
        ),
    }
    return pd.DataFrame([snapshot])[list(KPI_COLUMNS)]


def kpi_display(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Human-readable long form of the KPI snapshot, for reports and notebooks."""
    if snapshot.empty:
        return pd.DataFrame(columns=["metric", "value"])
    row = snapshot.iloc[0]
    rows = [
        ("Analysis window", f"{row['period_start']} to {row['period_end']}"),
        ("Days in window", format_count(row["days_in_period"])),
        ("Total revenue", format_compact_currency(row["total_revenue"])),
        ("Total orders", format_count(row["total_orders"])),
        ("Total units", format_count(row["total_units"])),
        ("Purchasing customers", format_count(row["unique_customers"])),
        ("Registered customers", format_count(row["registered_customers"])),
        ("Average order value", format_compact_currency(row["average_order_value"])),
        ("Average units per order", f"{row['average_units_per_order']:.2f}"),
        ("Revenue per purchasing customer", format_compact_currency(row["revenue_per_customer"])),
        (
            "Revenue per registered customer",
            format_compact_currency(row["revenue_per_registered_customer"]),
        ),
        ("Repeat customers", format_count(row["repeat_customers"])),
        ("One-time customers", format_count(row["one_time_customers"])),
        ("Repeat customer rate", format_percent(row["repeat_customer_rate"])),
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])

