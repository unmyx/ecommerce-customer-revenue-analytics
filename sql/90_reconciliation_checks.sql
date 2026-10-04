-- ===========================================================================
-- Reconciliation checks for the analytical layer.
--
-- Every row of analytics.reconciliation_checks compares an analytical total with
-- the raw-layer total it must equal. A correct build returns passed = true for
-- every check. Run scripts/run_reconciliation.py for a readable report.
--
-- Tolerances: 0 for row counts, 0.01 EUR for money (numeric(12,2) rounding).
--
-- Dependency order: run last, after 20/21/22/23.
-- ===========================================================================

DROP VIEW IF EXISTS analytics.reconciliation_checks CASCADE;

CREATE VIEW analytics.reconciliation_checks AS
WITH expected AS (
    SELECT
        (SELECT count(*) FROM raw.orders)                                              AS raw_orders,
        (SELECT count(*) FROM raw.order_items)                                         AS raw_order_lines,
        (SELECT count(*) FROM raw.customers)                                           AS raw_customers,
        (SELECT count(*) FROM raw.products)                                            AS raw_products,
        (SELECT count(*) FROM raw.campaign_assignments)                                AS raw_assignments,
        (SELECT count(*) FROM raw.orders WHERE campaign_id IS NOT NULL)                AS raw_attributed_orders,
        (SELECT coalesce(sum(net_revenue), 0) FROM raw.orders)                         AS raw_net_revenue_all,
        (SELECT coalesce(sum(net_revenue), 0) FROM raw.orders
          WHERE order_status = 'completed')                                            AS raw_net_revenue_recognised,
        (SELECT coalesce(sum(line_net_amount), 0) FROM raw.order_items)                AS raw_line_net_revenue,
        (SELECT coalesce(sum(i.quantity), 0) FROM raw.order_items AS i
           JOIN raw.orders AS o ON o.order_id = i.order_id
          WHERE o.order_status = 'completed')                                          AS raw_recognised_units,
        (SELECT count(*) FROM raw.orders WHERE order_status = 'completed')             AS raw_recognised_orders
),
actual AS (
    SELECT
        (SELECT count(*) FROM analytics.fct_orders)                                    AS fct_orders,
        (SELECT count(DISTINCT order_id) FROM analytics.fct_orders)                    AS fct_orders_distinct,
        (SELECT count(*) FROM analytics.fct_order_lines)                               AS fct_order_lines,
        (SELECT count(DISTINCT order_item_id) FROM analytics.fct_order_lines)          AS fct_order_lines_distinct,
        (SELECT coalesce(sum(net_revenue), 0) FROM analytics.fct_orders)               AS fct_net_revenue_all,
        (SELECT coalesce(sum(recognised_net_revenue), 0) FROM analytics.fct_orders)     AS fct_net_revenue_recognised,
        (SELECT coalesce(sum(line_net_revenue), 0) FROM analytics.fct_order_lines)      AS fct_line_net_revenue,
        (SELECT coalesce(sum(recognised_units), 0) FROM analytics.fct_orders)           AS fct_recognised_units,
        (SELECT count(*) FROM analytics.fct_orders WHERE is_campaign_attributed)       AS fct_attributed_orders,
        (SELECT count(*) FROM analytics.mart_customer_features)                        AS customer_mart_rows,
        (SELECT coalesce(sum(total_revenue), 0) FROM analytics.mart_customer_features)  AS customer_mart_revenue,
        (SELECT coalesce(sum(total_orders), 0) FROM analytics.mart_customer_features)   AS customer_mart_orders,
        (SELECT coalesce(sum(total_units), 0) FROM analytics.mart_customer_features)    AS customer_mart_units,
        (SELECT count(*) FROM analytics.mart_product_performance)                      AS product_mart_rows,
        (SELECT coalesce(sum(revenue), 0) FROM analytics.mart_product_performance)      AS product_mart_revenue,
        (SELECT coalesce(sum(units_sold), 0) FROM analytics.mart_product_performance)   AS product_mart_units,
        (SELECT coalesce(sum(revenue), 0) FROM analytics.mart_category_performance)     AS category_mart_revenue,
        (SELECT coalesce(sum(revenue), 0) FROM analytics.mart_revenue_daily)            AS daily_mart_revenue,
        (SELECT coalesce(sum(revenue), 0) FROM analytics.mart_revenue_monthly)          AS monthly_mart_revenue,
        (SELECT count(*) FROM analytics.mart_campaign_customer_outcomes)               AS campaign_outcome_rows
),
checks AS (
    SELECT 'fct_orders_row_count'::text AS check_id,
           'analytics.fct_orders has one row per raw order'::text AS description,
           e.raw_orders::numeric AS expected_value, a.fct_orders::numeric AS actual_value, 0::numeric AS tolerance
    FROM expected e, actual a

    UNION ALL
    SELECT 'fct_orders_unique_key',
           'fct_orders has no duplicate order_id',
           a.fct_orders::numeric, a.fct_orders_distinct::numeric, 0
    FROM actual a

    UNION ALL
    SELECT 'fct_order_lines_row_count',
           'analytics.fct_order_lines has one row per raw order line',
           e.raw_order_lines::numeric, a.fct_order_lines::numeric, 0
    FROM expected e, actual a

    UNION ALL
    SELECT 'fct_order_lines_unique_key',
           'fct_order_lines has no duplicate order_item_id',
           a.fct_order_lines::numeric, a.fct_order_lines_distinct::numeric, 0
    FROM actual a

    UNION ALL
    SELECT 'order_net_revenue_all_statuses',
           'fct_orders.net_revenue sums to raw.orders.net_revenue for every order status',
           e.raw_net_revenue_all, a.fct_net_revenue_all, 0.01
    FROM expected e, actual a

    UNION ALL
    SELECT 'order_net_revenue_recognised',
           'recognised revenue equals raw net revenue of completed orders',
           e.raw_net_revenue_recognised, a.fct_net_revenue_recognised, 0.01
    FROM expected e, actual a

    UNION ALL
    SELECT 'order_line_revenue_rollup',
           'raw order-line revenue rolls up to raw order net revenue',
           e.raw_net_revenue_all, e.raw_line_net_revenue, 0.01
    FROM expected e

    UNION ALL
    SELECT 'fct_line_revenue_rollup',
           'analytical line revenue rolls up to analytical order net revenue',
           a.fct_net_revenue_all, a.fct_line_net_revenue, 0.01
    FROM actual a

    UNION ALL
    SELECT 'customer_mart_row_count',
           'customer mart has one row per raw customer',
           e.raw_customers::numeric, a.customer_mart_rows::numeric, 0
    FROM expected e, actual a

    UNION ALL
    SELECT 'customer_mart_revenue',
           'customer total revenue reconciles to recognised order revenue',
           e.raw_net_revenue_recognised, a.customer_mart_revenue, 0.01
    FROM expected e, actual a

    UNION ALL
    SELECT 'customer_mart_orders',
           'customer order counts reconcile to recognised orders',
           e.raw_recognised_orders::numeric, a.customer_mart_orders, 0
    FROM expected e, actual a

    UNION ALL
    SELECT 'customer_mart_units',
           'customer units reconcile to recognised units',
           e.raw_recognised_units::numeric, a.customer_mart_units, 0
    FROM expected e, actual a

    UNION ALL
    SELECT 'product_mart_row_count',
           'product mart has one row per raw product',
           e.raw_products::numeric, a.product_mart_rows::numeric, 0
    FROM expected e, actual a

    UNION ALL
    SELECT 'product_mart_revenue',
           'product revenue reconciles to recognised line revenue',
           e.raw_net_revenue_recognised, a.product_mart_revenue, 0.01
    FROM expected e, actual a

    UNION ALL
    SELECT 'product_mart_units',
           'product units reconcile to recognised units',
           e.raw_recognised_units::numeric, a.product_mart_units::numeric, 0
    FROM expected e, actual a

    UNION ALL
    SELECT 'category_mart_revenue',
           'category rollup revenue equals recognised line revenue',
           e.raw_net_revenue_recognised, a.category_mart_revenue, 0.01
    FROM expected e, actual a

    UNION ALL
    SELECT 'daily_mart_revenue',
           'daily mart revenue equals recognised order revenue',
           e.raw_net_revenue_recognised, a.daily_mart_revenue, 0.01
    FROM expected e, actual a

    UNION ALL
    SELECT 'monthly_mart_revenue',
           'monthly mart revenue equals recognised order revenue',
           e.raw_net_revenue_recognised, a.monthly_mart_revenue, 0.01
    FROM expected e, actual a

    UNION ALL
    SELECT 'campaign_outcome_row_count',
           'campaign outcome mart has one row per raw assignment',
           e.raw_assignments::numeric, a.campaign_outcome_rows::numeric, 0
    FROM expected e, actual a

    UNION ALL
    SELECT 'campaign_attributed_order_count',
           'attributed orders in the fact table match the raw layer',
           e.raw_attributed_orders::numeric, a.fct_attributed_orders::numeric, 0
    FROM expected e, actual a
)
SELECT
    check_id,
    description,
    expected_value,
    actual_value,
    tolerance,
    round(actual_value - expected_value, 2) AS difference,
    (abs(actual_value - expected_value) <= tolerance) AS passed
FROM checks;

COMMENT ON VIEW analytics.reconciliation_checks IS
    'Analytical-layer reconciliation: each row compares an analytical total with the raw total it must equal.';

