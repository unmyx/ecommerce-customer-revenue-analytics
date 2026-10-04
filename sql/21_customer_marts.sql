-- ===========================================================================
-- Customer-level analytical mart.
--
-- analytics.mart_customer_features : one row per registered customer
--
-- Scope and rules
--   * Every registered customer is present, including non-purchasers, so the
--     inactive-customer analysis needs no separate universe.
--   * Frequency, units and revenue count only revenue-recognised orders
--     (order_status = 'completed'), matching the revenue rule of the layer.
--   * recency metrics are measured against analytics.analysis_window.analysis_end_date,
--     never against the wall clock, so results are reproducible.
--   * A customer is a repeat customer when they have two or more recognised orders.
--
-- Dependency order: requires 10_staging_views.sql and 20_revenue_marts.sql.
-- ===========================================================================

DROP VIEW IF EXISTS analytics.mart_customer_features CASCADE;

CREATE VIEW analytics.mart_customer_features AS
WITH bounds AS (
    SELECT analysis_end_date
    FROM analytics.analysis_window
),
recognised_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.order_date,
        o.order_month,
        o.recognised_units,
        o.recognised_net_revenue
    FROM analytics.fct_orders AS o
    WHERE o.is_revenue_recognised
),
customer_orders AS (
    SELECT
        r.customer_id,
        count(*)::int                              AS total_orders,
        min(r.order_date)                          AS first_order_date,
        max(r.order_date)                          AS last_order_date,
        count(DISTINCT r.order_month)::int         AS active_months,
        sum(r.recognised_units)::int               AS total_units,
        round(sum(r.recognised_net_revenue), 2)    AS total_revenue
    FROM recognised_orders AS r
    GROUP BY r.customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    c.country_code,
    c.city,
    c.acquisition_channel,
    c.signup_date,
    c.signup_month,
    (co.customer_id IS NOT NULL)                       AS has_purchased,
    co.first_order_date,
    co.last_order_date,
    to_char(co.first_order_date, 'YYYY-MM')            AS first_purchase_month,
    coalesce(co.total_orders, 0)                       AS total_orders,
    coalesce(co.total_units, 0)                        AS total_units,
    coalesce(co.total_revenue, 0::numeric)             AS total_revenue,
    round(coalesce(co.total_revenue, 0) / nullif(co.total_orders, 0), 2) AS average_order_value,
    (coalesce(co.total_orders, 0) > 1)                 AS repeat_customer,
    coalesce(co.active_months, 0)                      AS active_months,
    (co.last_order_date - co.first_order_date)         AS customer_lifetime_days,
    CASE
        WHEN co.total_orders > 1
        THEN round((co.last_order_date - co.first_order_date)::numeric / (co.total_orders - 1), 2)
    END                                                AS average_days_between_orders,
    (b.analysis_end_date - co.first_order_date)        AS days_since_first_order,
    (b.analysis_end_date - co.last_order_date)         AS days_since_last_order,
    b.analysis_end_date                                AS analysis_end_date
FROM analytics.stg_customers AS c
CROSS JOIN bounds AS b
LEFT JOIN customer_orders AS co
  ON co.customer_id = c.customer_id;

COMMENT ON VIEW analytics.mart_customer_features IS
    'One row per registered customer. total_orders/total_units/total_revenue use recognised orders only; non-purchasers keep NULL dates and zero metrics.';

