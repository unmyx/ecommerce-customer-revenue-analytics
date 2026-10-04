"""Revenue, order and company-level aggregates (Milestone 3, part A)."""

from __future__ import annotations

import pandas as pd

from novacart.analytics.common import (
    ORDER_REVENUE_COLUMN,
    ORDER_UNITS_COLUMN,
    recognised,
    require_columns,
    resolve_column,
    safe_divide,
)

SUMMARY_COLUMNS = (
    "period_start",
    "period_end",
    "total_revenue",
    "total_orders",
    "total_units",
    "unique_customers",
    "average_order_value",
    "average_units_per_order",
    "orders_per_customer",
    "repeat_customers",
    "one_time_customers",
    "repeat_customer_rate",
    "revenue_per_customer",
)


def revenue_summary(orders: pd.DataFrame) -> pd.DataFrame:
    """One-row revenue and order summary for a set of orders.

    All metrics use revenue-recognised orders only (``is_revenue_recognised``),
    which is the Milestone 1/2 revenue rule. Definitions:

    * total_revenue          sum of recognised net merchandise revenue
    * average_order_value    total_revenue / total_orders
    * average_units_per_order total_units / total_orders
    * repeat_customer_rate   customers with >= 2 recognised orders / purchasing customers
    * revenue_per_customer   total_revenue / purchasing customers
    """
    require_columns(orders, ("customer_id",), "revenue_summary")
    recognised_orders = recognised(orders)
    revenue_col = resolve_column(
        recognised_orders, (ORDER_REVENUE_COLUMN, "net_revenue"), "revenue_summary"
    )
    units_col = resolve_column(
        recognised_orders, (ORDER_UNITS_COLUMN, "total_units"), "revenue_summary"
    )
    date_col = resolve_column(
        recognised_orders, ("order_date", "order_month", "order_ts"), "revenue_summary"
    )

    if recognised_orders.empty:
        return _empty_summary()

    dates = pd.to_datetime(recognised_orders[date_col])
    revenue = float(recognised_orders[revenue_col].sum())
    units = int(recognised_orders[units_col].sum())
    total_orders = len(recognised_orders)
    unique_customers = int(recognised_orders["customer_id"].nunique())

    orders_per_customer = recognised_orders.groupby("customer_id").size()
    repeat_customers = int((orders_per_customer >= 2).sum())
    one_time_customers = int((orders_per_customer == 1).sum())

    return pd.DataFrame(
        [
            {
                "period_start": dates.min().date(),
                "period_end": dates.max().date(),
                "total_revenue": round(revenue, 2),
                "total_orders": total_orders,
                "total_units": units,
                "unique_customers": unique_customers,
                "average_order_value": round(safe_divide(revenue, total_orders), 2),
                "average_units_per_order": round(safe_divide(units, total_orders), 2),
                "orders_per_customer": round(safe_divide(total_orders, unique_customers), 2),
                "repeat_customers": repeat_customers,
                "one_time_customers": one_time_customers,
                "repeat_customer_rate": round(
                    safe_divide(repeat_customers, unique_customers), 4
                ),
                "revenue_per_customer": round(safe_divide(revenue, unique_customers), 2),
            }
        ]
    )


def _empty_summary() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "period_start": pd.NaT,
                "period_end": pd.NaT,
                "total_revenue": 0.0,
                "total_orders": 0,
                "total_units": 0,
                "unique_customers": 0,
                "average_order_value": float("nan"),
                "average_units_per_order": float("nan"),
                "orders_per_customer": float("nan"),
                "repeat_customers": 0,
                "one_time_customers": 0,
                "repeat_customer_rate": float("nan"),
                "revenue_per_customer": float("nan"),
            }
        ]
    )[list(SUMMARY_COLUMNS)]


def revenue_by_dimension(orders: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Revenue, orders, customers, units and AOV grouped by one order attribute.

    Typical dimensions: ``sales_channel``, ``country_code``, ``acquisition_channel``.
    """
    require_columns(orders, ("customer_id", dimension), "revenue_by_dimension")
    recognised_orders = recognised(orders)
    revenue_col = resolve_column(
        recognised_orders, (ORDER_REVENUE_COLUMN, "net_revenue"), "revenue_by_dimension"
    )
    units_col = resolve_column(
        recognised_orders, (ORDER_UNITS_COLUMN, "total_units"), "revenue_by_dimension"
    )
    if recognised_orders.empty:
        return pd.DataFrame(
            {
                dimension: pd.Series(dtype="object"),
                "orders": pd.Series(dtype="int64"),
                "customers": pd.Series(dtype="int64"),
                "units": pd.Series(dtype="int64"),
                "revenue": pd.Series(dtype="float64"),
                "average_order_value": pd.Series(dtype="float64"),
                "revenue_share_pct": pd.Series(dtype="float64"),
            }
        )

    grouped = (
        recognised_orders.groupby(dimension, as_index=False)
        .agg(
            orders=("order_id", "nunique") if "order_id" in recognised_orders.columns else (dimension, "size"),
            customers=("customer_id", "nunique"),
            units=(units_col, "sum"),
            revenue=(revenue_col, "sum"),
        )
    )
    total_revenue = float(grouped["revenue"].sum())
    grouped["average_order_value"] = (
        safe_divide(grouped["revenue"], grouped["orders"]).round(2)
    )
    grouped["revenue_share_pct"] = (
        safe_divide(grouped["revenue"], total_revenue) * 100
    ).round(4)
    grouped["revenue"] = grouped["revenue"].round(2)
    return grouped.sort_values(["revenue", dimension], ascending=[False, True]).reset_index(
        drop=True
    )

