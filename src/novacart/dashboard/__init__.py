"""Business presentation layer: dashboard exports, previews and the executive summary.

Nothing in this package recalculates business metrics. It reshapes the canonical
analytical outputs (PostgreSQL marts plus :mod:`novacart.analytics`) into
dashboard-ready files with stable schemas, then renders the executive summary and
the static page previews.
"""

from novacart.dashboard.exports import (
    EXPORT_SPECS,
    DashboardExports,
    build_dashboard_exports,
)
from novacart.dashboard.summary import ExecutiveSummary, build_executive_summary

__all__ = [
    "EXPORT_SPECS",
    "DashboardExports",
    "ExecutiveSummary",
    "build_dashboard_exports",
    "build_executive_summary",
]

