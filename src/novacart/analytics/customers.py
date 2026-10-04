"""Customer analytics by country, segment and value (Milestone 3, part D)."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from novacart.analytics.common import (
    AnalyticsError,
    empty_frame,
    require_columns,
    safe_divide,
)

COUNTRY_COLUMNS = (
    "country_code",
    "registered_customers",
    "purchasing_customers",
    "orders",
    "revenue",
    "average_customer_revenue",
    "revenue_share_pct",
)

SEGMENT_COLUMNS = (
    "segment",
    "customers",
    "orders",
    "revenue",
    "average_customer_revenue",
    "average_orders_per_customer",
    "revenue_share_pct",
)

DECILE_COLUMNS = (
    "revenue_decile",
    "customers",
    "revenue",
    "revenue_share_pct",
    "cumulative_revenue_share_pct",
    "average_customer_revenue",
    "min_customer_revenue",
    "max_customer_revenue",
)

CONCENTRATION_COLUMNS = (
    "purchasing_customers",
    "total_revenue",
    "top_1pct_revenue_share_pct",
    "top_10pct_revenue_share_pct",
    "bottom_50pct_revenue_share_pct",
)


def _purchasing(customers: pd.DataFrame, purpose: str) -> pd.DataFrame:
    require_columns(customers, ("customer_id", "has_purchased", "total_revenue"), purpose)
    return customers.loc[customers["has_purchased"].fillna(False).astype(bool)].copy()


def country_summary(customers: pd.DataFrame) -> pd.DataFrame:
    """Registered customers, purchasing customers, orders and revenue by country."""
    require_columns(
        customers,
        ("customer_id", "country_code", "has_purchased", "total_orders", "total_revenue"),
        "country_summary",
    )
    if customers.empty:
        return empty_frame(COUNTRY_COLUMNS)

    frame = customers.copy()
    frame["has_purchased"] = frame["has_purchased"].fillna(False).astype(bool)
    grouped = frame.groupby("country_code", as_index=False).agg(
        registered_customers=("customer_id", "count"),
        purchasing_customers=("has_purchased", "sum"),
        orders=("total_orders", "sum"),
        revenue=("total_revenue", "sum"),
    )
    grouped["purchasing_customers"] = grouped["purchasing_customers"].astype("int64")
    grouped["orders"] = grouped["orders"].astype("int64")
    grouped["revenue"] = grouped["revenue"].round(2)
    grouped["average_customer_revenue"] = safe_divide(
        grouped["revenue"], grouped["purchasing_customers"]
    ).round(2)
    grouped["revenue_share_pct"] = (
        safe_divide(grouped["revenue"], float(grouped["revenue"].sum())) * 100
    ).round(4)
    return grouped[list(COUNTRY_COLUMNS)].sort_values(
        ["revenue", "country_code"], ascending=[False, True]
    ).reset_index(drop=True)


def customer_segment_summary(customers: pd.DataFrame) -> pd.DataFrame:
    """Never-purchased, one-time and repeat customer segments."""
    require_columns(
        customers, ("customer_id", "has_purchased", "total_orders", "total_revenue"),
        "customer_segment_summary",
    )
    if customers.empty:
        return empty_frame(SEGMENT_COLUMNS)

    frame = customers.copy()
    frame["has_purchased"] = frame["has_purchased"].fillna(False).astype(bool)
    frame["segment"] = "never_purchased"
    frame.loc[frame["has_purchased"] & (frame["total_orders"] == 1), "segment"] = "one_time"
    frame.loc[frame["has_purchased"] & (frame["total_orders"] >= 2), "segment"] = "repeat"

    grouped = frame.groupby("segment", as_index=False).agg(
        customers=("customer_id", "count"),
        orders=("total_orders", "sum"),
        revenue=("total_revenue", "sum"),
    )
    total_revenue = float(grouped["revenue"].sum())
    grouped["revenue"] = grouped["revenue"].round(2)
    grouped["average_customer_revenue"] = safe_divide(
        grouped["revenue"], grouped["customers"]
    ).round(2)
    grouped["average_orders_per_customer"] = safe_divide(
        grouped["orders"], grouped["customers"]
    ).round(2)
    grouped["revenue_share_pct"] = (
        safe_divide(grouped["revenue"], total_revenue) * 100
    ).round(4)
    order = {"never_purchased": 0, "one_time": 1, "repeat": 2}
    grouped["_order"] = grouped["segment"].map(order).fillna(99)
    return grouped.sort_values("_order")[list(SEGMENT_COLUMNS)].reset_index(drop=True)


def revenue_deciles(customers: pd.DataFrame) -> pd.DataFrame:
    """Revenue by customer decile (decile 1 = lowest spending purchasing customer)."""
    purchasing = _purchasing(customers, "revenue_deciles")
    purchasing = purchasing.loc[purchasing["total_revenue"] > 0]
    if purchasing.empty:
        return empty_frame(DECILE_COLUMNS)

    ordered = purchasing.sort_values(
        ["total_revenue", "customer_id"], ascending=[True, True]
    ).reset_index(drop=True)
    # Equal-count deciles that stay well defined for any sample size: the lowest
    # 10% of purchasing customers form decile 1, the highest 10% form decile 10.
    ranks = ordered["total_revenue"].rank(method="first")
    ordered["revenue_decile"] = np.minimum(10, np.ceil(ranks * 10 / len(ordered)).astype(int))

    deciles = ordered.groupby("revenue_decile", as_index=False).agg(
        customers=("customer_id", "count"),
        revenue=("total_revenue", "sum"),
        min_customer_revenue=("total_revenue", "min"),
        max_customer_revenue=("total_revenue", "max"),
    )
    total_revenue = float(deciles["revenue"].sum())
    deciles["revenue"] = deciles["revenue"].round(2)
    deciles["revenue_share_pct"] = (
        safe_divide(deciles["revenue"], total_revenue) * 100
    ).round(4)
    deciles["cumulative_revenue_share_pct"] = deciles["revenue_share_pct"].cumsum().round(4)
    deciles["average_customer_revenue"] = safe_divide(
        deciles["revenue"], deciles["customers"]
    ).round(2)
    return deciles[list(DECILE_COLUMNS)]


def _share_of_revenue(purchasing: pd.DataFrame, fraction: float, *, from_top: bool) -> float:
    ordered = purchasing.sort_values(
        ["total_revenue", "customer_id"], ascending=[False, True]
    )
    count = max(1, math.ceil(len(ordered) * fraction))
    selected = ordered.head(count) if from_top else ordered.tail(count)
    return float(safe_divide(selected["total_revenue"].sum(), ordered["total_revenue"].sum()))


def revenue_concentration(customers: pd.DataFrame) -> pd.DataFrame:
    """Revenue concentration: shares held by the top 1%, top 10% and bottom 50%."""
    purchasing = _purchasing(customers, "revenue_concentration")
    purchasing = purchasing.loc[purchasing["total_revenue"] > 0]
    if purchasing.empty:
        return empty_frame(CONCENTRATION_COLUMNS)

    total_revenue = float(purchasing["total_revenue"].sum())
    return pd.DataFrame(
        [
            {
                "purchasing_customers": len(purchasing),
                "total_revenue": round(total_revenue, 2),
                "top_1pct_revenue_share_pct": round(
                    _share_of_revenue(purchasing, 0.01, from_top=True) * 100, 4
                ),
                "top_10pct_revenue_share_pct": round(
                    _share_of_revenue(purchasing, 0.10, from_top=True) * 100, 4
                ),
                "bottom_50pct_revenue_share_pct": round(
                    _share_of_revenue(purchasing, 0.50, from_top=False) * 100, 4
                ),
            }
        ]
    )[list(CONCENTRATION_COLUMNS)]


def top_customers_by_revenue(customers: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top ``n`` customers by recognised revenue, with the metric fully exposed."""
    selected_columns = [
        "customer_id",
        "customer_name",
        "country_code",
        "acquisition_channel",
        "total_orders",
        "total_units",
        "total_revenue",
        "average_order_value",
        "days_since_last_order",
        "revenue_share_pct",
    ]
    require_columns(
        customers,
        tuple(column for column in selected_columns if column != "revenue_share_pct"),
        "top_customers_by_revenue",
    )
    if n <= 0:
        raise AnalyticsError("n must be positive")
    purchasing = _purchasing(customers, "top_customers_by_revenue")
    if purchasing.empty:
        return empty_frame(selected_columns)

    total_revenue = float(purchasing["total_revenue"].sum())
    frame = purchasing.copy()
    frame["revenue_share_pct"] = (
        safe_divide(frame["total_revenue"], total_revenue) * 100
    ).round(4)
    return (
        frame.sort_values(["total_revenue", "customer_id"], ascending=[False, True])
        .head(n)[selected_columns]
        .reset_index(drop=True)
    )

