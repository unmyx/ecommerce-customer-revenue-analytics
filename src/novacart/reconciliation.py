"""End-to-end reconciliation: raw schema -> analytical layer -> dashboard exports.

The project already reconciles raw against analytics (``analytics.reconciliation_checks``)
and analytics against the dashboard exports (``tests/test_dashboard_exports.py``).
This module produces the single report that spans all three layers and states the
expected difference for every metric.

Expectation
    Every metric below must be **identical** across the three layers, because each
    layer only aggregates or copies canonical columns:

    * money metrics are compared with a 0.01 EUR rounding tolerance;
    * count metrics must match exactly.

    Two revenue figures are reported deliberately, because they answer different
    questions and differ by design:

    * ``revenue_canonical`` covers **every order status** (refunded and cancelled
      orders included) and is the amount stored on the order;
    * ``revenue_recognised`` covers **completed orders only** and is the revenue
      definition used by every KPI, chart, statistical test and dashboard visual.

    The gap between them is the refunded plus cancelled merchandise value, which is
    reported as context rather than treated as a reconciliation failure.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from novacart.analytics.common import AnalyticsError
from novacart.db import connect
from novacart.settings import OUTPUT_DIR, DatabaseSettings, load_database_settings

logger = logging.getLogger(__name__)

RECONCILIATION_DIR = OUTPUT_DIR / "reconciliation"
TABLE_NAME = "end_to_end_reconciliation.csv"
SUMMARY_NAME = "end_to_end_reconciliation.json"

MONEY_TOLERANCE = 0.01

#: metric key -> (label, definition, kind)
METRICS: dict[str, tuple[str, str, str]] = {
    "revenue_canonical": (
        "Revenue, all order statuses",
        "sum of items_subtotal - discount_amount for every order (refunds and cancellations included)",
        "money",
    ),
    "revenue_recognised": (
        "Recognised revenue",
        "net revenue of completed orders - the definition used by every KPI and chart",
        "money",
    ),
    "orders_all": ("Orders, all statuses", "row count of orders", "count"),
    "orders_recognised": ("Recognised orders", "count of completed orders", "count"),
    "units_all": ("Units, all order statuses", "sum of order line quantities", "count"),
    "units_recognised": ("Recognised units", "units on completed orders", "count"),
    "customers_registered": ("Registered customers", "row count of the customer table", "count"),
    "customers_purchasing": (
        "Purchasing customers",
        "distinct customers with at least one completed order",
        "count",
    ),
    "customer_revenue_total": (
        "Customer revenue total",
        "recognised revenue aggregated at customer grain (must equal recognised revenue)",
        "money",
    ),
    "product_revenue_total": (
        "Product revenue total",
        "recognised revenue aggregated at product grain (must equal recognised revenue)",
        "money",
    ),
    "attributed_orders": (
        "Attributed orders",
        "orders carrying a campaign attribution",
        "count",
    ),
    "campaign_assigned_customers": (
        "Campaign assignments",
        "campaign x customer assignment rows",
        "count",
    ),
}

RAW_QUERIES: dict[str, str] = {
    "revenue_canonical": "SELECT coalesce(sum(net_revenue), 0) FROM raw.orders",
    "revenue_recognised": (
        "SELECT coalesce(sum(net_revenue), 0) FROM raw.orders WHERE order_status = 'completed'"
    ),
    "orders_all": "SELECT count(*) FROM raw.orders",
    "orders_recognised": "SELECT count(*) FROM raw.orders WHERE order_status = 'completed'",
    "units_all": "SELECT coalesce(sum(quantity), 0) FROM raw.order_items",
    "units_recognised": (
        "SELECT coalesce(sum(i.quantity), 0) FROM raw.order_items AS i "
        "JOIN raw.orders AS o ON o.order_id = i.order_id WHERE o.order_status = 'completed'"
    ),
    "customers_registered": "SELECT count(*) FROM raw.customers",
    "customers_purchasing": (
        "SELECT count(DISTINCT customer_id) FROM raw.orders WHERE order_status = 'completed'"
    ),
    "customer_revenue_total": (
        "SELECT coalesce(sum(o.net_revenue), 0) FROM raw.orders AS o "
        "JOIN raw.customers AS c ON c.customer_id = o.customer_id "
        "WHERE o.order_status = 'completed'"
    ),
    "product_revenue_total": (
        "SELECT coalesce(sum(i.line_net_amount), 0) FROM raw.order_items AS i "
        "JOIN raw.orders AS o ON o.order_id = i.order_id WHERE o.order_status = 'completed'"
    ),
    "attributed_orders": "SELECT count(*) FROM raw.orders WHERE campaign_id IS NOT NULL",
    "campaign_assigned_customers": "SELECT count(*) FROM raw.campaign_assignments",
}

ANALYTICAL_QUERIES: dict[str, str] = {
    "revenue_canonical": "SELECT coalesce(sum(net_revenue), 0) FROM analytics.fct_orders",
    "revenue_recognised": (
        "SELECT coalesce(sum(recognised_net_revenue), 0) FROM analytics.fct_orders"
    ),
    "orders_all": "SELECT count(*) FROM analytics.fct_orders",
    "orders_recognised": (
        "SELECT count(*) FROM analytics.fct_orders WHERE is_revenue_recognised"
    ),
    "units_all": "SELECT coalesce(sum(quantity), 0) FROM analytics.fct_order_lines",
    "units_recognised": (
        "SELECT coalesce(sum(recognised_units), 0) FROM analytics.fct_order_lines"
    ),
    "customers_registered": "SELECT count(*) FROM analytics.mart_customer_features",
    "customers_purchasing": (
        "SELECT count(*) FROM analytics.mart_customer_features WHERE has_purchased"
    ),
    "customer_revenue_total": (
        "SELECT coalesce(sum(total_revenue), 0) FROM analytics.mart_customer_features"
    ),
    "product_revenue_total": (
        "SELECT coalesce(sum(revenue), 0) FROM analytics.mart_product_performance"
    ),
    "attributed_orders": (
        "SELECT count(*) FROM analytics.fct_orders WHERE is_campaign_attributed"
    ),
    "campaign_assigned_customers": (
        "SELECT count(*) FROM analytics.mart_campaign_customer_outcomes"
    ),
}


@dataclass
class EndToEndReconciliation:
    """Reconciliation table plus its summary and written paths."""

    table: pd.DataFrame
    summary: dict[str, object]
    paths: dict[str, Path] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.summary.get("ok", False))


def _as_float(value: object) -> float:
    return float(value) if value is not None else float("nan")


def assemble_reconciliation(
    raw: dict[str, float], analytical: dict[str, float], exported: dict[str, float]
) -> pd.DataFrame:
    """Compare the three layers metric by metric (pure function)."""
    missing = [
        f"{layer}:{key}"
        for layer, values in (("raw", raw), ("analytical", analytical), ("exported", exported))
        for key in METRICS
        if key not in values
    ]
    if missing:
        raise AnalyticsError(
            "Reconciliation is missing value(s): " + ", ".join(sorted(missing))
        )

    rows: list[dict[str, object]] = []
    for key, (label, definition, kind) in METRICS.items():
        raw_value = _as_float(raw[key])
        analytical_value = _as_float(analytical[key])
        exported_value = _as_float(exported[key])
        tolerance = MONEY_TOLERANCE if kind == "money" else 0.0
        raw_analytical = raw_value - analytical_value
        analytical_exported = analytical_value - exported_value
        rows.append(
            {
                "metric": label,
                "metric_key": key,
                "kind": kind,
                "definition": definition,
                "raw": round(raw_value, 2) if kind == "money" else int(raw_value),
                "analytical": round(analytical_value, 2)
                if kind == "money"
                else int(analytical_value),
                "exported": round(exported_value, 2) if kind == "money" else int(exported_value),
                "raw_minus_analytical": round(raw_analytical, 2),
                "analytical_minus_exported": round(analytical_exported, 2),
                "tolerance": tolerance,
                "expectation": "must equal",
                "passed": abs(raw_analytical) <= tolerance
                and abs(analytical_exported) <= tolerance,
            }
        )
    return pd.DataFrame(rows)


def _query_totals(settings: DatabaseSettings, queries: dict[str, str]) -> dict[str, float]:
    totals: dict[str, float] = {}
    with connect(settings) as connection, connection.cursor() as cursor:
        for key, sql in queries.items():
            cursor.execute(sql)
            row = cursor.fetchone()
            totals[key] = float(row[0]) if row and row[0] is not None else 0.0
    return totals


def _exported_totals(exports_dir: Path) -> dict[str, float]:
    def load(name: str, **kwargs) -> pd.DataFrame:
        path = exports_dir / f"{name}.csv"
        if not path.is_file():
            raise AnalyticsError(
                f"Dashboard export {name!r} not found in {exports_dir}; "
                "run scripts/build_dashboard.py first"
            )
        return pd.read_csv(path, **kwargs)

    orders = load("fact_orders", low_memory=False)
    lines = load("fact_order_lines", low_memory=False)
    customers = load("customer_rfm")
    products = load("product_performance")
    campaign_comparison = load("campaign_comparison")

    return {
        "revenue_canonical": float(
            (orders["gross_merchandise_amount"] - orders["discount_amount"]).sum()
        ),
        "revenue_recognised": float(orders["revenue"].sum()),
        "orders_all": float(len(orders)),
        "orders_recognised": float(orders["recognised_orders"].sum()),
        "units_all": float(lines["quantity"].sum()),
        "units_recognised": float(lines["units"].sum()),
        "customers_registered": float(len(customers)),
        "customers_purchasing": float(customers["has_purchased"].fillna(False).astype(bool).sum()),
        "customer_revenue_total": float(customers["monetary_revenue"].sum()),
        "product_revenue_total": float(products["revenue"].sum()),
        "attributed_orders": float(orders["is_campaign_attributed"].fillna(False).astype(bool).sum()),
        "campaign_assigned_customers": float(campaign_comparison["assigned_customers"].sum()),
    }


def summarise(table: pd.DataFrame) -> dict[str, object]:
    """Headline summary of a reconciliation table (pure function)."""
    money = table.loc[table["kind"] == "money"]
    counts = table.loc[table["kind"] == "count"]
    failures = table.loc[~table["passed"]]
    return {
        "metrics": len(table),
        "passed": int(table["passed"].sum()),
        "failed": len(failures),
        "max_money_difference": float(
            money[["raw_minus_analytical", "analytical_minus_exported"]].abs().to_numpy().max()
        )
        if not money.empty
        else 0.0,
        "max_count_difference": float(
            counts[["raw_minus_analytical", "analytical_minus_exported"]].abs().to_numpy().max()
        )
        if not counts.empty
        else 0.0,
        "failed_metrics": failures["metric"].tolist(),
        "ok": bool(len(failures) == 0),
        "tolerance_money": MONEY_TOLERANCE,
    }


def build_end_to_end_reconciliation(
    *,
    settings: DatabaseSettings | None = None,
    exports_dir: Path | None = None,
    output_dir: Path | None = None,
    write: bool = True,
) -> EndToEndReconciliation:
    """Compare raw, analytical and exported totals and write the report."""
    from novacart.dashboard.exports import CSV_DIR

    resolved_settings = settings or load_database_settings()
    raw = _query_totals(resolved_settings, RAW_QUERIES)
    analytical = _query_totals(resolved_settings, ANALYTICAL_QUERIES)
    exported = _exported_totals(exports_dir or CSV_DIR)

    table = assemble_reconciliation(raw, analytical, exported)
    summary = summarise(table)
    summary["generated_at_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    summary["refunded_and_cancelled_revenue"] = round(
        float(raw["revenue_canonical"]) - float(raw["revenue_recognised"]), 2
    )

    result = EndToEndReconciliation(table=table, summary=summary)
    if write:
        target = output_dir or RECONCILIATION_DIR
        target.mkdir(parents=True, exist_ok=True)
        table_path = target / TABLE_NAME
        summary_path = target / SUMMARY_NAME
        table.to_csv(table_path, index=False, lineterminator="\n")
        summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        result.paths = {"table": table_path, "summary": summary_path}
    return result

