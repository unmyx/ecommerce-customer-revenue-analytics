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

from novacart.analytics.campaigns import (
    campaign_comparison,
    campaign_customer_outcomes,
    campaign_statistics,
    significance_overview,
)
from novacart.analytics.cohorts import CohortAnalysis, cohort_analysis, customer_cohorts
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
from novacart.analytics.rfm import rfm_table, segment_score_profile, segment_summary
from novacart.analytics.statistics import (
    benjamini_hochberg_adjusted,
    bootstrap_mean_difference_ci,
    welch_mean_difference,
)
from novacart.analytics.trends import (
    add_month_over_month,
    add_rolling_metrics,
    daily_metrics,
    monthly_metrics,
    weekly_metrics,
)

__all__ = [
    "CohortAnalysis",
    "add_month_over_month",
    "add_rolling_metrics",
    "benjamini_hochberg_adjusted",
    "bootstrap_mean_difference_ci",
    "business_kpi_snapshot",
    "campaign_comparison",
    "campaign_customer_outcomes",
    "campaign_statistics",
    "category_summary",
    "cohort_analysis",
    "country_summary",
    "customer_cohorts",
    "customer_segment_summary",
    "daily_metrics",
    "declining_products",
    "monthly_metrics",
    "product_summary",
    "revenue_by_dimension",
    "revenue_concentration",
    "revenue_deciles",
    "revenue_summary",
    "rfm_table",
    "segment_score_profile",
    "segment_summary",
    "significance_overview",
    "top_customers_by_revenue",
    "top_products_by_revenue",
    "top_products_by_units",
    "weekly_metrics",
    "welch_mean_difference",
]

