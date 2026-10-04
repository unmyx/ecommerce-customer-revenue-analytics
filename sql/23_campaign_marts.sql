-- ===========================================================================
-- Campaign analysis preparation.
--
-- analytics.mart_campaign_customer_outcomes : one row per campaign x assigned customer
-- analytics.mart_campaign_performance       : one row per campaign, treatment vs holdout
--
-- Experimental design carried over from Milestone 1
--   * membership and arm come from raw.campaign_assignments (randomised holdout);
--   * 'treatment' rows are the intention-to-treat group. `is_exposed_treatment`
--     marks the subset that was actually exposed;
--   * attribution (orders.campaign_id) is only ever set for exposed treatment
--     customers inside the campaign window, so attributed orders are a subset of
--     treatment behaviour, never of the control group.
--
-- The ground truth used by the generator is deliberately NOT available here:
-- these views only contain observed behaviour. Significance testing belongs to
-- the Python statistics milestone; the lift columns below are raw, unadjusted
-- descriptive differences and must not be presented as causal effects.
--
-- Window definitions
--   pre-window  : the 90 days before the campaign start
--   window      : campaign start .. campaign end (inclusive)
--   post-window : the 30 days after the campaign end
--
-- Dependency order: requires 10/20.
-- ===========================================================================

DROP VIEW IF EXISTS analytics.mart_campaign_performance CASCADE;
DROP VIEW IF EXISTS analytics.mart_campaign_customer_outcomes CASCADE;

CREATE VIEW analytics.mart_campaign_customer_outcomes AS
WITH assignment_orders AS (
    SELECT
        a.campaign_id,
        a.campaign_name,
        a.channel,
        a.objective,
        a.target_audience,
        a.start_date,
        a.end_date,
        a.customer_id,
        a.arm,
        a.exposed,
        a.is_exposed_treatment,
        a.assigned_at,
        a.assigned_date,
        o.order_id,
        o.order_date,
        o.is_revenue_recognised,
        o.recognised_net_revenue,
        o.recognised_units,
        o.campaign_id AS attributed_campaign_id
    FROM analytics.stg_campaign_assignments AS a
    LEFT JOIN analytics.fct_orders AS o
      ON o.customer_id = a.customer_id
     AND o.order_date BETWEEN a.start_date - 90 AND a.end_date + 30
)
SELECT
    campaign_id,
    campaign_name,
    channel,
    objective,
    target_audience,
    start_date,
    end_date,
    customer_id,
    arm,
    exposed,
    is_exposed_treatment,
    assigned_at,
    assigned_date,
    count(*) FILTER (WHERE order_date < start_date AND is_revenue_recognised)::int AS pre_window_orders,
    round(coalesce(sum(recognised_net_revenue) FILTER (WHERE order_date < start_date), 0), 2) AS pre_window_revenue,
    count(*) FILTER (
        WHERE order_date BETWEEN start_date AND end_date AND is_revenue_recognised
    )::int                                                                        AS window_orders,
    round(coalesce(sum(recognised_net_revenue) FILTER (
        WHERE order_date BETWEEN start_date AND end_date
    ), 0), 2)                                                                     AS window_revenue,
    coalesce(sum(recognised_units) FILTER (
        WHERE order_date BETWEEN start_date AND end_date
    ), 0)::int                                                                    AS window_units,
    count(*) FILTER (
        WHERE order_date BETWEEN start_date AND end_date AND is_revenue_recognised
    ) > 0                                                                         AS ordered_in_window,
    count(*) FILTER (
        WHERE order_date BETWEEN start_date AND end_date
          AND attributed_campaign_id = campaign_id
    )::int                                                                        AS attributed_window_orders,
    count(*) FILTER (WHERE order_date > end_date AND is_revenue_recognised)::int  AS post_window_orders,
    round(coalesce(sum(recognised_net_revenue) FILTER (WHERE order_date > end_date), 0), 2) AS post_window_revenue
FROM assignment_orders
GROUP BY
    campaign_id,
    campaign_name,
    channel,
    objective,
    target_audience,
    start_date,
    end_date,
    customer_id,
    arm,
    exposed,
    is_exposed_treatment,
    assigned_at,
    assigned_date;

COMMENT ON VIEW analytics.mart_campaign_customer_outcomes IS
    'Customer-level campaign outcomes (one row per campaign x assigned customer) for treatment/holdout comparison. Revenue uses recognised orders only.';

CREATE VIEW analytics.mart_campaign_performance AS
WITH arm_metrics AS (
    SELECT
        o.campaign_id,
        count(*)::int                                                        AS assigned_customers,
        count(*) FILTER (WHERE o.arm = 'treatment')::int                      AS treatment_assigned,
        count(*) FILTER (WHERE o.arm = 'control')::int                        AS control_assigned,
        count(*) FILTER (WHERE o.is_exposed_treatment)::int                    AS treatment_exposed,
        count(*) FILTER (WHERE o.arm = 'treatment' AND o.ordered_in_window)::int AS treatment_buyers,
        count(*) FILTER (WHERE o.arm = 'control' AND o.ordered_in_window)::int   AS control_buyers,
        coalesce(sum(o.window_orders) FILTER (WHERE o.arm = 'treatment'), 0)::int AS treatment_window_orders,
        coalesce(sum(o.window_orders) FILTER (WHERE o.arm = 'control'), 0)::int   AS control_window_orders,
        round(coalesce(sum(o.window_revenue) FILTER (WHERE o.arm = 'treatment'), 0), 2) AS treatment_window_revenue,
        round(coalesce(sum(o.window_revenue) FILTER (WHERE o.arm = 'control'), 0), 2)   AS control_window_revenue,
        round(coalesce(sum(o.pre_window_revenue) FILTER (WHERE o.arm = 'treatment'), 0), 2) AS treatment_pre_window_revenue,
        round(coalesce(sum(o.pre_window_revenue) FILTER (WHERE o.arm = 'control'), 0), 2)   AS control_pre_window_revenue
    FROM analytics.mart_campaign_customer_outcomes AS o
    GROUP BY o.campaign_id
)
SELECT
    c.campaign_id,
    c.campaign_name,
    c.channel,
    c.objective,
    c.target_audience,
    c.start_date,
    c.end_date,
    c.duration_days,
    c.budget_eur,
    coalesce(a.assigned_customers, 0)        AS assigned_customers,
    coalesce(a.treatment_assigned, 0)        AS treatment_assigned,
    coalesce(a.control_assigned, 0)          AS control_assigned,
    coalesce(a.treatment_exposed, 0)         AS treatment_exposed,
    round(
        coalesce(a.treatment_exposed, 0)::numeric / nullif(a.treatment_assigned, 0), 4
    )                                        AS treatment_exposure_rate,
    coalesce(a.treatment_buyers, 0)          AS treatment_buyers,
    coalesce(a.control_buyers, 0)            AS control_buyers,
    coalesce(a.treatment_window_orders, 0)   AS treatment_window_orders,
    coalesce(a.control_window_orders, 0)     AS control_window_orders,
    coalesce(a.treatment_window_revenue, 0)  AS treatment_window_revenue,
    coalesce(a.control_window_revenue, 0)    AS control_window_revenue,
    round(coalesce(a.treatment_window_orders, 0)::numeric / nullif(a.treatment_assigned, 0), 4)  AS treatment_orders_per_customer,
    round(coalesce(a.control_window_orders, 0)::numeric / nullif(a.control_assigned, 0), 4)      AS control_orders_per_customer,
    round(coalesce(a.treatment_window_revenue, 0) / nullif(a.treatment_assigned, 0), 2)          AS treatment_revenue_per_customer,
    round(coalesce(a.control_window_revenue, 0) / nullif(a.control_assigned, 0), 2)              AS control_revenue_per_customer,
    round(coalesce(a.treatment_buyers, 0)::numeric / nullif(a.treatment_assigned, 0), 4)         AS treatment_buyer_rate,
    round(coalesce(a.control_buyers, 0)::numeric / nullif(a.control_assigned, 0), 4)             AS control_buyer_rate,
    round(coalesce(a.treatment_pre_window_revenue, 0) / nullif(a.treatment_assigned, 0), 2)      AS treatment_pre_window_revenue_per_customer,
    round(coalesce(a.control_pre_window_revenue, 0) / nullif(a.control_assigned, 0), 2)          AS control_pre_window_revenue_per_customer,
    round(
        (coalesce(a.treatment_window_revenue, 0) / nullif(a.treatment_assigned, 0))
        - (coalesce(a.control_window_revenue, 0) / nullif(a.control_assigned, 0)), 2
    )                                        AS unadjusted_lift_revenue_per_customer,
    round(
        (coalesce(a.treatment_window_orders, 0)::numeric / nullif(a.treatment_assigned, 0))
        - (coalesce(a.control_window_orders, 0)::numeric / nullif(a.control_assigned, 0)), 4
    )                                        AS unadjusted_lift_orders_per_customer
FROM analytics.stg_campaigns AS c
LEFT JOIN arm_metrics AS a
  ON a.campaign_id = c.campaign_id;

COMMENT ON VIEW analytics.mart_campaign_performance IS
    'Campaign-level treatment/holdout summary. Lift columns are raw unadjusted differences (intention-to-treat), not statistically tested effects.';

