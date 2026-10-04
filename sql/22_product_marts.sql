-- ===========================================================================
-- Product and category analytical marts.
--
-- analytics.mart_product_performance  : one row per catalogue product
-- analytics.mart_category_performance : one row per category
--
-- Rules
--   * Revenue and units use recognised orders only (same rule as the revenue layer).
--   * Products that never sold are still present, with zero metrics, so slow movers
--     and declining products are visible.
--   * average_selling_price is the realised price: recognised revenue / units sold
--     (after line discounts), not the catalogue list price.
--
-- Dependency order: requires 10_staging_views.sql and 20_revenue_marts.sql.
-- ===========================================================================

DROP VIEW IF EXISTS analytics.mart_category_performance CASCADE;
DROP VIEW IF EXISTS analytics.mart_product_performance CASCADE;

CREATE VIEW analytics.mart_product_performance AS
WITH line_agg AS (
    SELECT
        l.product_id,
        sum(l.recognised_units)::int                                   AS units_sold,
        count(DISTINCT l.order_id) FILTER (WHERE l.is_revenue_recognised)::int AS order_count,
        count(DISTINCT l.customer_id) FILTER (WHERE l.is_revenue_recognised)::int AS unique_customers,
        coalesce(sum(l.recognised_line_net_revenue), 0)                AS revenue,
        coalesce(sum(l.line_discount) FILTER (WHERE l.is_revenue_recognised), 0) AS discount_amount,
        coalesce(sum(l.line_gross_profit) FILTER (WHERE l.is_revenue_recognised), 0) AS gross_profit,
        min(l.order_date) FILTER (WHERE l.is_revenue_recognised)       AS first_sold_date,
        max(l.order_date) FILTER (WHERE l.is_revenue_recognised)       AS last_sold_date
    FROM analytics.fct_order_lines AS l
    GROUP BY l.product_id
),
joined AS (
    SELECT
        p.product_id,
        p.sku,
        p.product_name,
        p.brand,
        p.category,
        p.subcategory,
        p.list_price,
        p.list_cost,
        p.list_margin_rate,
        p.launch_date,
        p.is_active,
        coalesce(a.units_sold, 0)          AS units_sold,
        coalesce(a.order_count, 0)         AS order_count,
        coalesce(a.unique_customers, 0)    AS unique_customers,
        round(coalesce(a.revenue, 0), 2)   AS revenue,
        round(coalesce(a.discount_amount, 0), 2) AS discount_amount,
        round(coalesce(a.gross_profit, 0), 2)    AS gross_profit,
        round(coalesce(a.revenue, 0) / nullif(a.units_sold, 0), 2) AS average_selling_price,
        round(coalesce(a.gross_profit, 0) / nullif(a.revenue, 0), 4) AS gross_margin_rate,
        a.first_sold_date,
        a.last_sold_date
    FROM analytics.stg_products AS p
    LEFT JOIN line_agg AS a
      ON a.product_id = p.product_id
),
ranked AS (
    SELECT
        j.*,
        rank() OVER (ORDER BY j.revenue DESC, j.product_id)             AS revenue_rank,
        rank() OVER (PARTITION BY j.category ORDER BY j.revenue DESC, j.product_id) AS revenue_rank_in_category,
        round(100 * j.revenue / nullif(sum(j.revenue) OVER (), 0), 4)   AS revenue_share_pct
    FROM joined AS j
)
SELECT
    product_id,
    sku,
    product_name,
    brand,
    category,
    subcategory,
    list_price,
    list_cost,
    list_margin_rate,
    launch_date,
    is_active,
    units_sold,
    order_count,
    unique_customers,
    revenue,
    discount_amount,
    gross_profit,
    average_selling_price,
    gross_margin_rate,
    revenue_rank,
    revenue_rank_in_category,
    revenue_share_pct,
    first_sold_date,
    last_sold_date
FROM ranked;

COMMENT ON VIEW analytics.mart_product_performance IS
    'Product performance on recognised orders. average_selling_price is revenue per unit sold, after discounts.';

CREATE VIEW analytics.mart_category_performance AS
WITH category_agg AS (
    SELECT
        l.category,
        sum(l.recognised_units)::int                                   AS units_sold,
        count(DISTINCT l.order_id) FILTER (WHERE l.is_revenue_recognised)::int AS order_count,
        count(DISTINCT l.customer_id) FILTER (WHERE l.is_revenue_recognised)::int AS unique_customers,
        coalesce(sum(l.recognised_line_net_revenue), 0)                AS revenue,
        coalesce(sum(l.line_gross_profit) FILTER (WHERE l.is_revenue_recognised), 0) AS gross_profit
    FROM analytics.fct_order_lines AS l
    GROUP BY l.category
),
product_counts AS (
    SELECT
        p.category,
        count(*)::int                                   AS product_count,
        count(*) FILTER (WHERE p.is_active)::int        AS active_product_count
    FROM analytics.stg_products AS p
    GROUP BY p.category
)
SELECT
    pc.category,
    pc.product_count,
    pc.active_product_count,
    coalesce(a.units_sold, 0)        AS units_sold,
    coalesce(a.order_count, 0)       AS order_count,
    coalesce(a.unique_customers, 0)  AS unique_customers,
    round(coalesce(a.revenue, 0), 2) AS revenue,
    round(coalesce(a.gross_profit, 0), 2) AS gross_profit,
    round(coalesce(a.revenue, 0) / nullif(a.units_sold, 0), 2) AS average_selling_price,
    round(coalesce(a.gross_profit, 0) / nullif(a.revenue, 0), 4) AS gross_margin_rate,
    rank() OVER (ORDER BY coalesce(a.revenue, 0) DESC, pc.category) AS revenue_rank,
    round(100 * coalesce(a.revenue, 0) / nullif(sum(coalesce(a.revenue, 0)) OVER (), 0), 4) AS revenue_share_pct
FROM product_counts AS pc
LEFT JOIN category_agg AS a
  ON a.category = pc.category;

COMMENT ON VIEW analytics.mart_category_performance IS
    'Category rollup: revenue, units, realised price and margin, with revenue rank and share.';

