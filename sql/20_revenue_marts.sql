-- ===========================================================================
-- Revenue facts and time-series marts.
--
-- Published facts (consumed by every other mart, by Python analysis and by BI):
--   analytics.fct_orders      one row per order, order grain
--   analytics.fct_order_lines one row per order line, line grain
--
-- Revenue rule used by every mart in this layer (identical to Milestone 1):
--   revenue = recognised net merchandise revenue
--           = orders.net_revenue where order_status = 'completed'
--   shipping and VAT are tracked separately and never added to revenue.
--
--   gross_merchandise_amount = items_subtotal (before discounts)
--   net_revenue              = canonical amount for every order, any status
--   recognised_net_revenue   = net_revenue for completed orders, otherwise 0
--
-- Dependency order: requires 10_staging_views.sql.
-- ===========================================================================

DROP VIEW IF EXISTS analytics.mart_revenue_monthly CASCADE;
DROP VIEW IF EXISTS analytics.mart_revenue_daily CASCADE;
DROP VIEW IF EXISTS analytics.fct_order_lines CASCADE;
DROP VIEW IF EXISTS analytics.fct_orders CASCADE;

-- ---------------------------------------------------------------------------
-- fct_orders
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.fct_orders AS
WITH line_rollup AS (
    SELECT
        l.order_id,
        count(*)::int                        AS line_count,
        sum(l.quantity)::int                 AS total_units,
        round(sum(l.quantity * l.unit_price), 2) AS line_gross_amount,
        round(sum(l.line_net_amount), 2)     AS line_net_amount
    FROM analytics.stg_order_lines AS l
    GROUP BY l.order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_ts,
    o.order_date,
    o.order_month,
    o.order_status,
    (o.order_status = 'completed')            AS is_revenue_recognised,
    (o.order_status = 'refunded')             AS is_refunded,
    (o.order_status = 'cancelled')            AS is_cancelled,
    o.sales_channel,
    o.campaign_id,
    (o.campaign_id IS NOT NULL)               AS is_campaign_attributed,
    o.country_code,
    o.acquisition_channel,
    o.customer_signup_date,
    o.shipping_country_code,
    coalesce(r.line_count, 0)                 AS line_count,
    coalesce(r.total_units, 0)                AS total_units,
    o.items_subtotal                          AS gross_merchandise_amount,
    o.discount_amount,
    o.net_revenue,
    CASE WHEN o.order_status = 'completed'
         THEN o.net_revenue ELSE 0::numeric(12,2) END AS recognised_net_revenue,
    CASE WHEN o.order_status = 'completed'
         THEN coalesce(r.total_units, 0) ELSE 0 END   AS recognised_units,
    o.shipping_amount,
    o.tax_amount                              AS vat_amount,
    o.order_total,
    o.currency_code
FROM analytics.stg_orders AS o
LEFT JOIN line_rollup AS r
  ON r.order_id = o.order_id;

COMMENT ON VIEW analytics.fct_orders IS
    'Order-grain fact. net_revenue is the canonical Milestone 1 field for every order; recognised_net_revenue applies the completed-only revenue rule used by all marts.';

-- ---------------------------------------------------------------------------
-- fct_order_lines
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.fct_order_lines AS
SELECT
    l.order_item_id,
    l.order_id,
    l.order_ts,
    l.order_date,
    l.order_month,
    l.order_status,
    (l.order_status = 'completed')            AS is_revenue_recognised,
    l.sales_channel,
    l.campaign_id,
    l.customer_id,
    l.product_id,
    l.product_name,
    l.brand,
    l.category,
    l.subcategory,
    l.quantity,
    l.unit_price,
    l.unit_cost,
    l.line_discount,
    round(l.quantity * l.unit_price, 2)       AS line_gross_amount,
    l.line_net_amount                         AS line_net_revenue,
    round(l.quantity * l.unit_cost, 2)        AS line_cost,
    round(l.line_net_amount - l.quantity * l.unit_cost, 2) AS line_gross_profit,
    round(
        (l.line_net_amount - l.quantity * l.unit_cost) / nullif(l.line_net_amount, 0), 4
    )                                         AS line_margin_rate,
    CASE WHEN l.order_status = 'completed'
         THEN l.line_net_amount ELSE 0::numeric(12,2) END  AS recognised_line_net_revenue,
    CASE WHEN l.order_status = 'completed' THEN l.quantity ELSE 0 END AS recognised_units
FROM analytics.stg_order_lines AS l;

COMMENT ON VIEW analytics.fct_order_lines IS
    'Line-grain fact with cost, gross profit and recognised revenue per line.';

-- ---------------------------------------------------------------------------
-- mart_revenue_daily
-- Calendar-spined daily revenue series with 7-day and 30-day rolling metrics.
-- Days without orders are kept (zero values) so time series have no gaps.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.mart_revenue_daily AS
WITH daily AS (
    SELECT
        o.order_date,
        count(*)::int                                                  AS orders_placed,
        count(*) FILTER (WHERE o.is_revenue_recognised)::int            AS orders_recognised,
        count(*) FILTER (WHERE o.is_refunded)::int                      AS refunded_orders,
        count(*) FILTER (WHERE o.is_cancelled)::int                     AS cancelled_orders,
        count(DISTINCT o.customer_id) FILTER (WHERE o.is_revenue_recognised)::int AS purchasing_customers,
        coalesce(sum(o.recognised_units), 0)::int                       AS units,
        coalesce(sum(o.recognised_net_revenue), 0)                      AS revenue,
        coalesce(sum(o.gross_merchandise_amount) FILTER (WHERE o.is_revenue_recognised), 0) AS gross_merchandise_amount,
        coalesce(sum(o.discount_amount) FILTER (WHERE o.is_revenue_recognised), 0)          AS discount_amount,
        coalesce(sum(o.shipping_amount) FILTER (WHERE o.is_revenue_recognised), 0)          AS shipping_amount,
        coalesce(sum(o.vat_amount) FILTER (WHERE o.is_revenue_recognised), 0)               AS vat_amount
    FROM analytics.fct_orders AS o
    GROUP BY o.order_date
),
filled AS (
    SELECT
        d.date_key,
        d.year,
        d.quarter,
        d.month,
        d.year_month,
        d.iso_year_week,
        d.day_of_month,
        d.iso_day_of_week,
        d.day_name,
        d.is_weekend,
        coalesce(a.orders_placed, 0)            AS orders_placed,
        coalesce(a.orders_recognised, 0)        AS orders_recognised,
        coalesce(a.refunded_orders, 0)          AS refunded_orders,
        coalesce(a.cancelled_orders, 0)         AS cancelled_orders,
        coalesce(a.purchasing_customers, 0)     AS purchasing_customers,
        coalesce(a.units, 0)                    AS units,
        coalesce(a.revenue, 0)                  AS revenue,
        coalesce(a.gross_merchandise_amount, 0) AS gross_merchandise_amount,
        coalesce(a.discount_amount, 0)          AS discount_amount,
        coalesce(a.shipping_amount, 0)          AS shipping_amount,
        coalesce(a.vat_amount, 0)               AS vat_amount
    FROM analytics.dim_date AS d
    LEFT JOIN daily AS a
      ON a.order_date = d.date_key
),
rolling AS (
    SELECT
        f.*,
        sum(f.revenue) OVER w7            AS revenue_rolling_7d,
        sum(f.revenue) OVER w30           AS revenue_rolling_30d,
        sum(f.orders_recognised) OVER w7  AS orders_rolling_7d,
        sum(f.orders_recognised) OVER w30 AS orders_rolling_30d
    FROM filled AS f
    WINDOW
        w7  AS (ORDER BY f.date_key ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),
        w30 AS (ORDER BY f.date_key ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
)
SELECT
    r.date_key,
    r.year,
    r.quarter,
    r.month,
    r.year_month,
    r.iso_year_week,
    r.day_of_month,
    r.iso_day_of_week,
    r.day_name,
    r.is_weekend,
    r.orders_placed,
    r.orders_recognised,
    r.refunded_orders,
    r.cancelled_orders,
    r.purchasing_customers,
    r.units,
    round(r.revenue, 2)                                        AS revenue,
    round(r.gross_merchandise_amount, 2)                       AS gross_merchandise_amount,
    round(r.discount_amount, 2)                                AS discount_amount,
    round(r.shipping_amount, 2)                                AS shipping_amount,
    round(r.vat_amount, 2)                                     AS vat_amount,
    round(r.revenue / nullif(r.orders_recognised, 0), 2)       AS average_order_value,
    round(r.revenue / nullif(r.purchasing_customers, 0), 2)    AS revenue_per_customer,
    round(r.revenue_rolling_7d, 2)                             AS revenue_rolling_7d,
    round(r.revenue_rolling_30d, 2)                            AS revenue_rolling_30d,
    r.orders_rolling_7d::int                                   AS orders_rolling_7d,
    r.orders_rolling_30d::int                                  AS orders_rolling_30d
FROM rolling AS r;

COMMENT ON VIEW analytics.mart_revenue_daily IS
    'Daily revenue series on a complete calendar spine. revenue is recognised net merchandise revenue; rolling metrics are trailing windows including the current day.';

-- ---------------------------------------------------------------------------
-- mart_revenue_monthly
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.mart_revenue_monthly AS
WITH months AS (
    SELECT DISTINCT
        date_trunc('month', d.date_key)::date AS month_start,
        d.year_month,
        d.year,
        d.quarter,
        d.month,
        d.month_name
    FROM analytics.dim_date AS d
),
monthly AS (
    SELECT
        o.order_month,
        count(*)::int                                                  AS orders_placed,
        count(*) FILTER (WHERE o.is_revenue_recognised)::int            AS orders_recognised,
        count(*) FILTER (WHERE o.is_refunded)::int                      AS refunded_orders,
        count(*) FILTER (WHERE o.is_cancelled)::int                     AS cancelled_orders,
        count(DISTINCT o.customer_id) FILTER (WHERE o.is_revenue_recognised)::int AS purchasing_customers,
        coalesce(sum(o.recognised_units), 0)::int                       AS units,
        coalesce(sum(o.recognised_net_revenue), 0)                      AS revenue,
        coalesce(sum(o.gross_merchandise_amount) FILTER (WHERE o.is_revenue_recognised), 0) AS gross_merchandise_amount,
        coalesce(sum(o.discount_amount) FILTER (WHERE o.is_revenue_recognised), 0)          AS discount_amount
    FROM analytics.fct_orders AS o
    GROUP BY o.order_month
)
SELECT
    m.month_start,
    m.year_month,
    m.year,
    m.quarter,
    m.month,
    m.month_name,
    coalesce(a.orders_placed, 0)         AS orders_placed,
    coalesce(a.orders_recognised, 0)     AS orders_recognised,
    coalesce(a.refunded_orders, 0)       AS refunded_orders,
    coalesce(a.cancelled_orders, 0)      AS cancelled_orders,
    coalesce(a.purchasing_customers, 0)  AS purchasing_customers,
    coalesce(a.units, 0)                 AS units,
    round(coalesce(a.revenue, 0), 2)     AS revenue,
    round(coalesce(a.gross_merchandise_amount, 0), 2) AS gross_merchandise_amount,
    round(coalesce(a.discount_amount, 0), 2)          AS discount_amount,
    round(coalesce(a.revenue, 0) / nullif(a.orders_recognised, 0), 2)      AS average_order_value,
    round(coalesce(a.revenue, 0) / nullif(a.purchasing_customers, 0), 2)   AS revenue_per_customer
FROM months AS m
LEFT JOIN monthly AS a
  ON a.order_month = m.month_start;

COMMENT ON VIEW analytics.mart_revenue_monthly IS
    'Monthly revenue mart on a calendar spine. Same revenue rule as mart_revenue_daily.';

