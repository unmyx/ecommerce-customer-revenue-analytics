"""Building and inspecting the analytical SQL layer.

The analytics schema is a set of SQL views, rebuilt as a unit in dependency
order. This module owns that order so the CLI, the tests and the notebook layer
cannot disagree about it.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from psycopg.rows import dict_row

from novacart.db import apply_sql_files, connect
from novacart.logging_config import configure_logging
from novacart.settings import SQL_DIR, ConfigurationError, DatabaseSettings, load_database_settings

logger = logging.getLogger(__name__)

#: Applied before the analytics views so the build also works on a fresh database.
BOOTSTRAP_FILES: tuple[Path, ...] = (SQL_DIR / "01_schemas.sql",)

#: Analytics layer, in dependency order. Staging -> facts/marts -> checks.
ANALYTICS_SQL_FILES: tuple[Path, ...] = (
    SQL_DIR / "10_staging_views.sql",
    SQL_DIR / "20_revenue_marts.sql",
    SQL_DIR / "21_customer_marts.sql",
    SQL_DIR / "22_product_marts.sql",
    SQL_DIR / "23_campaign_marts.sql",
    SQL_DIR / "90_reconciliation_checks.sql",
)

#: Published analytical relations, grouped by layer for documentation and reporting.
ANALYTICAL_OBJECTS: dict[str, tuple[str, ...]] = {
    "staging": (
        "analytics.analysis_window",
        "analytics.dim_date",
        "analytics.stg_customers",
        "analytics.stg_products",
        "analytics.stg_orders",
        "analytics.stg_order_lines",
        "analytics.stg_campaigns",
        "analytics.stg_campaign_assignments",
    ),
    "facts": (
        "analytics.fct_orders",
        "analytics.fct_order_lines",
    ),
    "marts": (
        "analytics.mart_revenue_daily",
        "analytics.mart_revenue_monthly",
        "analytics.mart_customer_features",
        "analytics.mart_product_performance",
        "analytics.mart_category_performance",
        "analytics.mart_campaign_customer_outcomes",
        "analytics.mart_campaign_performance",
    ),
    "checks": ("analytics.reconciliation_checks",),
}


def build_analytics_layer(
    settings: DatabaseSettings,
    files: tuple[Path, ...] = ANALYTICS_SQL_FILES,
    *,
    bootstrap: bool = True,
) -> dict[str, int]:
    """(Re)create every analytical view and return the statement count per file."""
    paths = (BOOTSTRAP_FILES + files) if bootstrap else files
    with connect(settings) as connection:
        applied = apply_sql_files(connection, paths)
    logger.info("Rebuilt analytical layer from %d SQL files", len(files))
    return applied


def list_analytical_views(settings: DatabaseSettings) -> dict[str, tuple[str, ...]]:
    """Return the views that currently exist in the analytics schema, by layer."""
    with connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT viewname
              FROM pg_catalog.pg_views
             WHERE schemaname = 'analytics'
             ORDER BY viewname
            """
        )
        existing = {row[0] for row in cursor.fetchall()}

    return {
        layer: tuple(name.split(".", 1)[1] for name in names if name.split(".", 1)[1] in existing)
        for layer, names in ANALYTICAL_OBJECTS.items()
    }


def fetch_reconciliation(settings: DatabaseSettings) -> list[dict[str, object]]:
    """Read analytics.reconciliation_checks as a list of dictionaries."""
    with connect(settings) as connection, connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT check_id, description, expected_value, actual_value,
                   difference, passed
              FROM analytics.reconciliation_checks
             ORDER BY passed, check_id
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def _print_reconciliation(rows: list[dict[str, object]]) -> None:
    if not rows:
        print("No reconciliation checks found. Build the analytics layer first.")
        return
    width = max(len(str(row["check_id"])) for row in rows)
    print(f"{'check_id':<{width}}  {'result':<4}  {'expected':>16}  {'actual':>16}  {'diff':>10}")
    for row in rows:
        result = "PASS" if row["passed"] else "FAIL"
        print(
            f"{row['check_id']:<{width}}  {result:<4}  "
            f"{float(row['expected_value']):>16,.2f}  {float(row['actual_value']):>16,.2f}  "
            f"{float(row['difference']):>10,.2f}"
        )


def build_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="novacart-build-analytics",
        description="(Re)build the analytical SQL layer on top of the raw schema.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(logging.WARNING if args.quiet else logging.INFO)

    try:
        settings = load_database_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        applied = build_analytics_layer(settings)
        views = list_analytical_views(settings)
    except FileNotFoundError as exc:
        print(f"Missing SQL file: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator
        print(f"Building the analytical layer failed: {exc}", file=sys.stderr)
        return 1

    total = sum(applied.values())
    for name, count in applied.items():
        print(f"{name:<32} {count:>3} statements")
    print(f"{'total':<32} {total:>3} statements")
    for layer, names in views.items():
        print(f"{layer:<10}: {len(names)} views")
    return 0


def reconcile_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="novacart-reconcile",
        description="Reconcile the analytical layer against the raw layer.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(logging.WARNING if args.quiet else logging.INFO)

    try:
        settings = load_database_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        rows = fetch_reconciliation(settings)
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator
        print(f"Reconciliation failed: {exc}", file=sys.stderr)
        return 1

    _print_reconciliation(rows)
    failures = [row for row in rows if not row["passed"]]
    print()
    print(f"{len(rows)} checks executed, {len(failures)} failing")
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(build_main())

