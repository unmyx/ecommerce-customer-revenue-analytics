"""Integration tests for the analytical SQL layer.

They verify that the staging views, facts and marts agree with the raw layer that
produced them. Every assertion is written as raw-versus-analytics reconciliation,
so the tests hold for the full dataset and for the reduced test dataset alike.

Skipped unless ``NOVACART_RUN_DB_TESTS=1`` because they require PostgreSQL with
the raw layer already loaded.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

import pytest
from psycopg import Connection

from novacart.db import connect
from novacart.settings import ConfigurationError, DatabaseSettings, load_database_settings
from novacart.warehouse import build_analytics_layer, fetch_reconciliation

pytestmark = pytest.mark.integration

MONEY_TOLERANCE = 0.01


def _integration_enabled() -> bool:
    return os.getenv("NOVACART_RUN_DB_TESTS", "").lower() in {"1", "true", "yes"}


def _settings_or_skip() -> DatabaseSettings:
    if not _integration_enabled():
        pytest.skip("set NOVACART_RUN_DB_TESTS=1 to run database integration tests")
    try:
        return load_database_settings()
    except ConfigurationError as exc:  # pragma: no cover - environment issue
        pytest.skip(f"database configuration unavailable: {exc}")


@pytest.fixture(scope="module")
def db() -> DatabaseSettings:
    settings = _settings_or_skip()
    with connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM raw.orders")
        row = cursor.fetchone()
        if not row or row[0] == 0:
            pytest.skip("raw layer is empty; run scripts/load_raw.py first")
    build_analytics_layer(settings)
    return settings


def _scalar(connection: Connection, sql: str, params: Sequence[object] | None = None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        row = cursor.fetchone()
    return row[0] if row else None


def _rows(connection: Connection, sql: str) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return cursor.fetchall()


def _mismatch_count(connection: Connection, sql: str) -> int:
    value = _scalar(connection, sql)
    return int(value or 0)


# ---------------------------------------------------------------------------
# reconciliation
# ---------------------------------------------------------------------------
def test_reconciliation_view_passes_for_every_check(db: DatabaseSettings) -> None:
    checks = fetch_reconciliation(db)
    assert len(checks) >= 20
    failures = [check for check in checks if not check["passed"]]
    assert failures == []


def test_order_revenue_matches_canonical_raw_revenue(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        per_order = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.fct_orders AS f
              JOIN raw.orders AS r ON r.order_id = f.order_id
             WHERE f.net_revenue <> r.net_revenue
            """,
        )
        assert per_order == 0

        difference = _scalar(
            connection,
            """
            SELECT abs(
                (SELECT sum(net_revenue) FROM raw.orders)
              - (SELECT sum(net_revenue) FROM analytics.fct_orders)
            )
            """,
        )
        assert float(difference) <= MONEY_TOLERANCE

        recognised = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.fct_orders
             WHERE is_revenue_recognised <> (order_status = 'completed')
                OR recognised_net_revenue <> CASE WHEN order_status = 'completed'
                                                  THEN net_revenue ELSE 0 END
            """,
        )
        assert recognised == 0


def test_order_line_revenue_rolls_up_to_order_revenue(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        mismatches = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM (
                    SELECT order_id, round(sum(line_net_revenue), 2) AS line_revenue
                      FROM analytics.fct_order_lines
                     GROUP BY order_id
                   ) AS lines
              JOIN analytics.fct_orders AS orders ON orders.order_id = lines.order_id
             WHERE lines.line_revenue <> orders.net_revenue
            """,
        )
        assert mismatches == 0


def test_customer_mart_reconciles_to_order_level_totals(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        difference = _scalar(
            connection,
            """
            SELECT abs(
                (SELECT coalesce(sum(recognised_net_revenue), 0) FROM analytics.fct_orders)
              - (SELECT coalesce(sum(total_revenue), 0) FROM analytics.mart_customer_features)
            )
            """,
        )
        assert float(difference) <= MONEY_TOLERANCE

        orders_difference = _scalar(
            connection,
            """
            SELECT (SELECT count(*) FROM analytics.fct_orders WHERE is_revenue_recognised)
                 - (SELECT coalesce(sum(total_orders), 0) FROM analytics.mart_customer_features)
            """,
        )
        assert int(orders_difference) == 0


def test_product_and_category_marts_reconcile_to_order_lines(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        for relation in ("analytics.mart_product_performance", "analytics.mart_category_performance"):
            difference = _scalar(
                connection,
                f"""
                SELECT abs(
                    (SELECT coalesce(sum(recognised_line_net_revenue), 0)
                       FROM analytics.fct_order_lines)
                  - (SELECT coalesce(sum(revenue), 0) FROM {relation})
                )
                """,
            )
            assert float(difference) <= MONEY_TOLERANCE, relation

            units_difference = _scalar(
                connection,
                f"""
                SELECT (SELECT coalesce(sum(recognised_units), 0) FROM analytics.fct_order_lines)
                     - (SELECT coalesce(sum(units_sold), 0) FROM {relation})
                """,
            )
            assert int(units_difference) == 0, relation


def test_daily_and_monthly_marts_reconcile_to_each_other(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        difference = _scalar(
            connection,
            """
            SELECT abs(
                (SELECT coalesce(sum(revenue), 0) FROM analytics.mart_revenue_daily)
              - (SELECT coalesce(sum(revenue), 0) FROM analytics.mart_revenue_monthly)
            )
            """,
        )
        assert float(difference) <= MONEY_TOLERANCE


def test_row_counts_reconcile_with_raw(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        pairs = (
            ("raw.orders", "analytics.fct_orders"),
            ("raw.order_items", "analytics.fct_order_lines"),
            ("raw.customers", "analytics.mart_customer_features"),
            ("raw.products", "analytics.mart_product_performance"),
            ("raw.campaign_assignments", "analytics.mart_campaign_customer_outcomes"),
        )
        for raw_relation, analytics_relation in pairs:
            difference = _scalar(
                connection,
                f"SELECT (SELECT count(*) FROM {raw_relation})"
                f"     - (SELECT count(*) FROM {analytics_relation})",
            )
            assert int(difference) == 0, f"{raw_relation} vs {analytics_relation}"


# ---------------------------------------------------------------------------
# keys and structure
# ---------------------------------------------------------------------------
def test_analytical_outputs_have_no_duplicate_keys(db: DatabaseSettings) -> None:
    keyed_relations = (
        ("analytics.fct_orders", "order_id"),
        ("analytics.fct_order_lines", "order_item_id"),
        ("analytics.mart_customer_features", "customer_id"),
        ("analytics.mart_product_performance", "product_id"),
        ("analytics.mart_category_performance", "category"),
        ("analytics.mart_revenue_daily", "date_key"),
        ("analytics.mart_revenue_monthly", "month_start"),
        ("analytics.mart_campaign_performance", "campaign_id"),
    )
    with connect(db) as connection:
        for relation, key in keyed_relations:
            duplicates = _mismatch_count(
                connection,
                f"SELECT count(*) - count(DISTINCT {key}) FROM {relation}",
            )
            assert duplicates == 0, f"{relation}.{key}"

        duplicates = _mismatch_count(
            connection,
            """
            SELECT count(*) - count(DISTINCT (campaign_id, customer_id))
              FROM analytics.mart_campaign_customer_outcomes
            """,
        )
        assert duplicates == 0


def test_campaign_outcomes_cover_every_assignment(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        orphaned = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM raw.campaign_assignments AS a
              LEFT JOIN analytics.mart_campaign_customer_outcomes AS o
                ON o.campaign_id = a.campaign_id
               AND o.customer_id = a.customer_id
             WHERE o.customer_id IS NULL
            """,
        )
        assert orphaned == 0


# ---------------------------------------------------------------------------
# customer logic
# ---------------------------------------------------------------------------
def test_customer_date_and_lifetime_logic(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        violations = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.mart_customer_features
             WHERE first_order_date > last_order_date
                OR (has_purchased AND days_since_last_order <> analysis_end_date - last_order_date)
                OR (has_purchased AND customer_lifetime_days <> last_order_date - first_order_date)
                OR (
                     total_orders > 1
                     AND average_days_between_orders <>
                         round((last_order_date - first_order_date)::numeric / (total_orders - 1), 2)
                   )
                OR (
                     NOT has_purchased
                     AND (first_order_date IS NOT NULL OR total_orders <> 0
                          OR total_revenue <> 0 OR days_since_last_order IS NOT NULL)
                   )
            """,
        )
        assert violations == 0


def test_repeat_customer_flag_matches_independent_calculation(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        mismatches = _mismatch_count(
            connection,
            """
            WITH independent AS (
                SELECT customer_id, count(*) AS recognised_orders
                  FROM raw.orders
                 WHERE order_status = 'completed'
                 GROUP BY customer_id
            )
            SELECT count(*)
              FROM analytics.mart_customer_features AS m
              LEFT JOIN independent AS i ON i.customer_id = m.customer_id
             WHERE m.repeat_customer <> (coalesce(i.recognised_orders, 0) > 1)
            """,
        )
        assert mismatches == 0


def test_customer_average_order_value_definition(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        mismatches = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.mart_customer_features
             WHERE total_orders > 0
               AND average_order_value <> round(total_revenue / total_orders, 2)
            """,
        )
        assert mismatches == 0


# ---------------------------------------------------------------------------
# date logic
# ---------------------------------------------------------------------------
def test_order_date_and_month_logic(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        mismatches = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.fct_orders
             WHERE order_date <> order_ts::date
                OR order_month <> date_trunc('month', order_ts)::date
            """,
        )
        assert mismatches == 0


def test_daily_mart_is_a_complete_calendar(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        row = _rows(
            connection,
            """
            WITH bounds AS (SELECT first_order_date, analysis_end_date, window_days
                              FROM analytics.analysis_window)
            SELECT (SELECT count(*) FROM analytics.mart_revenue_daily) AS rows,
                   w.window_days,
                   (SELECT min(date_key) FROM analytics.mart_revenue_daily) AS first_date,
                   (SELECT max(date_key) FROM analytics.mart_revenue_daily) AS last_date,
                   w.first_order_date,
                   w.analysis_end_date
              FROM bounds AS w
            """,
        )[0]
        rows, window_days, first_date, last_date, first_order, last_order = row
        assert rows == window_days
        assert first_date == first_order and last_date == last_order

        invalid_calendar = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.mart_revenue_daily
             WHERE iso_day_of_week NOT BETWEEN 1 AND 7
                OR is_weekend <> (iso_day_of_week >= 6)
                OR extract(day FROM date_key)::int <> day_of_month
            """,
        )
        assert invalid_calendar == 0


def test_rolling_windows_are_correct(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        for days in (7, 30):
            mismatches = _mismatch_count(
                connection,
                f"""
                WITH expected AS (
                    SELECT date_key,
                           sum(revenue) OVER (
                               ORDER BY date_key ROWS BETWEEN {days - 1} PRECEDING AND CURRENT ROW
                           ) AS expected_revenue
                      FROM analytics.mart_revenue_daily
                )
                SELECT count(*)
                  FROM analytics.mart_revenue_daily AS d
                  JOIN expected AS e ON e.date_key = d.date_key
                 WHERE round(e.expected_revenue, 2) <> d.revenue_rolling_{days}d
                """,
            )
            assert mismatches == 0, f"{days}-day rolling revenue"

        first_day_mismatch = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.mart_revenue_daily
             WHERE date_key = (SELECT min(date_key) FROM analytics.mart_revenue_daily)
               AND revenue_rolling_7d <> revenue
            """,
        )
        assert first_day_mismatch == 0


# ---------------------------------------------------------------------------
# campaign rules
# ---------------------------------------------------------------------------
def test_campaign_attribution_follows_exposure_and_window_rules(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        unattributable = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.fct_orders AS o
             WHERE o.is_campaign_attributed
               AND NOT EXISTS (
                    SELECT 1
                      FROM analytics.stg_campaign_assignments AS a
                     WHERE a.campaign_id = o.campaign_id
                       AND a.customer_id = o.customer_id
                       AND a.is_exposed_treatment
               )
            """,
        )
        assert unattributable == 0

        outside_window = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.fct_orders AS o
              JOIN analytics.stg_campaigns AS c ON c.campaign_id = o.campaign_id
             WHERE o.is_campaign_attributed
               AND (o.order_date < c.start_date OR o.order_date > c.end_date)
            """,
        )
        assert outside_window == 0

        control_attributed = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.fct_orders AS o
              JOIN analytics.stg_campaign_assignments AS a
                ON a.campaign_id = o.campaign_id
               AND a.customer_id = o.customer_id
             WHERE o.is_campaign_attributed AND a.arm = 'control'
            """,
        )
        assert control_attributed == 0


def test_campaign_outcome_window_logic(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        mismatches = _mismatch_count(
            connection,
            """
            WITH independent AS (
                SELECT a.campaign_id,
                       a.customer_id,
                       count(*) FILTER (
                           WHERE o.order_status = 'completed'
                             AND o.order_ts::date BETWEEN c.start_date AND c.end_date
                       ) AS window_orders
                  FROM raw.campaign_assignments AS a
                  JOIN raw.marketing_campaigns AS c ON c.campaign_id = a.campaign_id
                  LEFT JOIN raw.orders AS o ON o.customer_id = a.customer_id
                 GROUP BY a.campaign_id, a.customer_id
            )
            SELECT count(*)
              FROM analytics.mart_campaign_customer_outcomes AS m
              JOIN independent AS i
                ON i.campaign_id = m.campaign_id
               AND i.customer_id = m.customer_id
             WHERE m.window_orders <> i.window_orders
            """,
        )
        assert mismatches == 0

        control_attributed = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.mart_campaign_customer_outcomes
             WHERE arm = 'control' AND attributed_window_orders <> 0
            """,
        )
        assert control_attributed == 0

        not_exposed_but_attributed = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM analytics.mart_campaign_customer_outcomes
             WHERE NOT is_exposed_treatment AND attributed_window_orders <> 0
            """,
        )
        assert not_exposed_but_attributed == 0


def test_campaign_performance_summarises_the_member_mart(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        mismatches = _mismatch_count(
            connection,
            """
            WITH expected AS (
                SELECT campaign_id,
                       count(*) FILTER (WHERE arm = 'treatment') AS treatment_assigned,
                       count(*) FILTER (WHERE arm = 'control') AS control_assigned,
                       sum(window_orders) FILTER (WHERE arm = 'treatment') AS treatment_orders,
                       sum(window_orders) FILTER (WHERE arm = 'control') AS control_orders
                  FROM analytics.mart_campaign_customer_outcomes
                 GROUP BY campaign_id
            )
            SELECT count(*)
              FROM analytics.mart_campaign_performance AS p
              JOIN expected AS e ON e.campaign_id = p.campaign_id
             WHERE p.treatment_assigned <> e.treatment_assigned
                OR p.control_assigned <> e.control_assigned
                OR p.treatment_window_orders <> e.treatment_orders
                OR p.control_window_orders <> e.control_orders
            """,
        )
        assert mismatches == 0

        exposure_rows = _rows(
            connection,
            """
            SELECT treatment_assigned, treatment_exposed
              FROM analytics.mart_campaign_performance
            """,
        )
        for assigned, exposed in exposure_rows:
            assert 0 < exposed <= assigned


def test_no_generator_ground_truth_leaks_into_the_analytics_schema(db: DatabaseSettings) -> None:
    with connect(db) as connection:
        leaked_views = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM pg_catalog.pg_views
             WHERE schemaname = 'analytics'
               AND (definition ILIKE '%placebo%'
                    OR definition ILIKE '%true_purchase_lift%'
                    OR definition ILIKE '%true_aov_lift%'
                    OR definition ILIKE '%generation_metadata%'
                    OR definition ILIKE '%manifest%')
            """,
        )
        assert leaked_views == 0

        leaked_columns = _mismatch_count(
            connection,
            """
            SELECT count(*)
              FROM information_schema.columns
             WHERE table_schema = 'analytics'
               AND (column_name ILIKE '%placebo%' OR column_name ILIKE 'true_%')
            """,
        )
        assert leaked_columns == 0

