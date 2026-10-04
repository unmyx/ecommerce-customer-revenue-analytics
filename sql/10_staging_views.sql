-- ===========================================================================
-- Staging layer: cleaned, renamed and lightly enriched views on the raw schema.
--
-- Purpose
--   * give every downstream model one stable vocabulary (order_date, net_revenue,
--     list_price, ...) instead of raw source names;
--   * resolve foreign keys once (customer attributes on orders, product
--     attributes on order lines) so marts do not repeat the same joins;
--   * keep business-rule logic out of staging: recognition flags, margins and
--     aggregations belong to the fact/mart layer.
--
-- Revenue vocabulary (must not drift from Milestone 1):
--   net_revenue  = raw.orders.net_revenue  = items_subtotal - discount_amount
--                  (canonical, database-generated merchandise revenue; all order
--                   statuses)
--   recognised   = the order status is 'completed'. Shipping and VAT are never
--                  part of revenue.
--
-- Dependency order: this file must run before 20/21/22/23/90.
-- The analytics layer is rebuilt as a unit, so views are dropped with CASCADE
-- and recreated by the later files in the same run.
-- ===========================================================================

DROP VIEW IF EXISTS analytics.stg_campaign_assignments CASCADE;
DROP VIEW IF EXISTS analytics.stg_campaigns CASCADE;
DROP VIEW IF EXISTS analytics.stg_order_lines CASCADE;
DROP VIEW IF EXISTS analytics.stg_orders CASCADE;
DROP VIEW IF EXISTS analytics.stg_products CASCADE;
DROP VIEW IF EXISTS analytics.stg_customers CASCADE;
DROP VIEW IF EXISTS analytics.dim_date CASCADE;
DROP VIEW IF EXISTS analytics.analysis_window CASCADE;

-- ---------------------------------------------------------------------------
-- analysis_window: the reporting window implied by the loaded data.
-- Single source of truth for "as of" calculations such as customer recency.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.analysis_window AS
SELECT
    min(order_ts)::date                            AS first_order_date,
    max(order_ts)::date                            AS analysis_end_date,
    (max(order_ts)::date - min(order_ts)::date + 1) AS window_days,
    count(*)::bigint                               AS total_orders
FROM raw.orders;

COMMENT ON VIEW analytics.analysis_window IS
    'One row describing the loaded order window. analysis_end_date is the as-of date used for recency metrics.';

-- ---------------------------------------------------------------------------
-- dim_date: calendar spine covering every day with at least one order.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.dim_date AS
WITH bounds AS (
    SELECT first_order_date, analysis_end_date
    FROM analytics.analysis_window
),
days AS (
    SELECT
        generated::date                              AS date_key,
        bounds.analysis_end_date,
        extract(year FROM generated)::int            AS year,
        extract(quarter FROM generated)::int         AS quarter,
        extract(month FROM generated)::int           AS month,
        to_char(generated, 'YYYY-MM')                AS year_month,
        trim(to_char(generated, 'Month'))            AS month_name,
        date_trunc('week', generated)::date          AS week_start,
        to_char(generated, 'IYYY-"W"IW')             AS iso_year_week,
        extract(day FROM generated)::int             AS day_of_month,
        extract(isodow FROM generated)::int          AS iso_day_of_week,
        trim(to_char(generated, 'Day'))              AS day_name,
        extract(isodow FROM generated) >= 6          AS is_weekend
    FROM bounds
    CROSS JOIN LATERAL generate_series(
        bounds.first_order_date::timestamp,
        bounds.analysis_end_date::timestamp,
        interval '1 day'
    ) AS generated
)
SELECT
    date_key,
    analysis_end_date,
    year,
    quarter,
    month,
    year_month,
    month_name,
    week_start,
    iso_year_week,
    day_of_month,
    iso_day_of_week,
    day_name,
    is_weekend
FROM days;

COMMENT ON VIEW analytics.dim_date IS
    'Daily calendar for the loaded order window, including an is_weekend flag and ISO week/month labels.';

-- ---------------------------------------------------------------------------
-- stg_customers
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.stg_customers AS
SELECT
    c.customer_id,
    c.first_name || ' ' || c.last_name          AS customer_name,
    c.country_code,
    c.city,
    c.acquisition_channel,
    c.signup_date,
    to_char(c.signup_date, 'YYYY-MM')           AS signup_month,
    c.created_at
FROM raw.customers AS c;

COMMENT ON VIEW analytics.stg_customers IS
    'Cleaned customer records. Email is intentionally excluded from the analytical layer.';

-- ---------------------------------------------------------------------------
-- stg_products
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.stg_products AS
SELECT
    p.product_id,
    p.sku,
    p.product_name,
    p.brand,
    p.category,
    p.subcategory,
    p.unit_price                                                        AS list_price,
    p.unit_cost                                                         AS list_cost,
    round(p.unit_price - p.unit_cost, 2)                                AS list_gross_margin,
    round((p.unit_price - p.unit_cost) / nullif(p.unit_price, 0), 4)    AS list_margin_rate,
    p.launch_date,
    p.is_active
FROM raw.products AS p;

COMMENT ON VIEW analytics.stg_products IS
    'Cleaned catalogue with list-level margin. list_price is the end-of-window snapshot price.';

-- ---------------------------------------------------------------------------
-- stg_orders: one row per order with customer attributes resolved.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.stg_orders AS
SELECT
    o.order_id,
    o.customer_id,
    o.order_ts,
    o.order_ts::date                              AS order_date,
    date_trunc('month', o.order_ts)::date         AS order_month,
    o.order_status,
    o.sales_channel,
    o.campaign_id,
    c.country_code,
    c.acquisition_channel,
    c.signup_date                                 AS customer_signup_date,
    o.items_subtotal,
    o.discount_amount,
    o.net_revenue,
    o.shipping_amount,
    o.tax_amount,
    o.order_total,
    o.currency_code,
    o.shipping_country_code
FROM raw.orders AS o
JOIN raw.customers AS c
  ON c.customer_id = o.customer_id;

COMMENT ON VIEW analytics.stg_orders IS
    'Order headers with customer attributes resolved. net_revenue is the canonical Milestone 1 revenue field; recognition is decided in fct_orders.';

-- ---------------------------------------------------------------------------
-- stg_order_lines: one row per order line with order and product context.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.stg_order_lines AS
SELECT
    i.order_item_id,
    i.order_id,
    o.order_ts,
    o.order_ts::date                              AS order_date,
    date_trunc('month', o.order_ts)::date         AS order_month,
    o.order_status,
    o.sales_channel,
    o.campaign_id,
    o.customer_id,
    i.product_id,
    p.product_name,
    p.brand,
    p.category,
    p.subcategory,
    i.quantity,
    i.unit_price,
    i.unit_cost,
    i.line_discount,
    i.line_net_amount
FROM raw.order_items AS i
JOIN raw.orders AS o
  ON o.order_id = i.order_id
JOIN raw.products AS p
  ON p.product_id = i.product_id;

COMMENT ON VIEW analytics.stg_order_lines IS
    'Order lines with order context and product attributes. line_net_amount is the canonical database-generated line revenue.';

-- ---------------------------------------------------------------------------
-- stg_campaigns
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.stg_campaigns AS
SELECT
    c.campaign_id,
    c.campaign_name,
    c.channel,
    c.objective,
    c.target_audience,
    c.start_date,
    c.end_date,
    (c.end_date - c.start_date)                                 AS duration_days,
    round(c.budget_eur / nullif((c.end_date - c.start_date + 1), 0), 2) AS daily_budget_eur,
    c.budget_eur,
    c.created_at
FROM raw.marketing_campaigns AS c;

COMMENT ON VIEW analytics.stg_campaigns IS
    'Cleaned campaign master data. duration_days is the number of days between start and end.';

-- ---------------------------------------------------------------------------
-- stg_campaign_assignments
--
-- Randomised experiment membership. is_exposed_treatment is the flag that the
-- campaign analysis treats as "actually received the campaign"; control members
-- can never be exposed, which is enforced in the raw layer.
-- ---------------------------------------------------------------------------
CREATE VIEW analytics.stg_campaign_assignments AS
SELECT
    a.assignment_id,
    a.campaign_id,
    c.campaign_name,
    c.channel,
    c.objective,
    c.target_audience,
    c.start_date,
    c.end_date,
    a.customer_id,
    a.arm,
    a.exposed,
    (a.arm = 'treatment' AND a.exposed) AS is_exposed_treatment,
    a.assigned_at,
    a.assigned_at::date                 AS assigned_date,
    a.assignment_method
FROM raw.campaign_assignments AS a
JOIN raw.marketing_campaigns AS c
  ON c.campaign_id = a.campaign_id;

COMMENT ON VIEW analytics.stg_campaign_assignments IS
    'Campaign experiment membership with campaign attributes resolved.';

