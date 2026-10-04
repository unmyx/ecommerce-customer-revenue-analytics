"""Reusable business analytics on top of the PostgreSQL analytical layer.

The package is deliberately split by business question:

    common      data access + shared metric helpers
    revenue     revenue, order and company-level aggregates
    kpis        the canonical business KPI snapshot
    trends      daily / weekly / monthly series, rolling windows, month-over-month
    products    product, category and declining-product analysis
    customers   country, segment and customer-value distribution analysis
    plots       reusable business charts
    report      orchestration that writes tables and figures

Every calculation is a pure function over DataFrames so it can be unit tested
without a database; the ``load_*`` helpers in :mod:`novacart.analytics.common`
are the only database-aware code.
"""

from novacart.analytics.customers import (
    country_summary,
    customer_segment_summary,
    revenue_concentration,
    revenue_deciles,
    top_customers_by_revenue,
)
from novacart.analytics.kpis import business_kpi_snapshot
from novacart.analytics.products import (
    category_summary,
    declining_products,
    product_summary,
    top_products_by_revenue,
    top_products_by_units,
)
from novacart.analytics.revenue import revenue_by_dimension, revenue_summary
from novacart.analytics.trends import (
    add_month_over_month,
    add_rolling_metrics,
    daily_metrics,
    monthly_metrics,
    weekly_metrics,
)

__all__ = [
    "add_month_over_month",
    "add_rolling_metrics",
    "business_kpi_snapshot",
    "category_summary",
    "country_summary",
    "customer_segment_summary",
    "daily_metrics",
    "declining_products",
    "monthly_metrics",
    "product_summary",
    "revenue_by_dimension",
    "revenue_concentration",
    "revenue_deciles",
    "revenue_summary",
    "top_customers_by_revenue",
    "top_products_by_revenue",
    "top_products_by_units",
    "weekly_metrics",
]

