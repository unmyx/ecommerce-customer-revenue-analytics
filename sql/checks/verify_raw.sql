-- Data-quality checks for the raw layer. Every query returns the number of rows
-- that violate the rule; a passing dataset returns 0 for all rows.
-- Run standalone with:
--   psql -f sql/checks/verify_raw.sql
-- or via: python scripts/check_raw_data.py

WITH checks AS (
    SELECT 'orders_orphan_customer' AS check_id,
           'Orders must reference an existing customer' AS description,
           (SELECT count(*) FROM raw.orders o
             LEFT JOIN raw.customers c ON c.customer_id = o.customer_id
             WHERE c.customer_id IS NULL) AS failing_rows

    UNION ALL
    SELECT 'order_items_orphan_order',
           'Order items must reference an existing order',
           (SELECT count(*) FROM raw.order_items i
             LEFT JOIN raw.orders o ON o.order_id = i.order_id
             WHERE o.order_id IS NULL)

    UNION ALL
    SELECT 'order_items_orphan_product',
           'Order items must reference an existing product',
           (SELECT count(*) FROM raw.order_items i
             LEFT JOIN raw.products p ON p.product_id = i.product_id
             WHERE p.product_id IS NULL)

    UNION ALL
    SELECT 'orders_without_payment',
           'Every order has exactly one payment',
           (SELECT count(*) FROM raw.orders o
             LEFT JOIN raw.payments p ON p.order_id = o.order_id
             WHERE p.payment_id IS NULL)

    UNION ALL
    SELECT 'orders_subtotal_mismatch',
           'Order items_subtotal must equal the sum of its line gross amounts',
           (SELECT count(*) FROM (
                SELECT o.order_id
                  FROM raw.orders o
                  JOIN raw.order_items i ON i.order_id = o.order_id
                 GROUP BY o.order_id, o.items_subtotal
                HAVING round(sum(i.quantity * i.unit_price), 2) <> o.items_subtotal
            ) mismatches)

    UNION ALL
    SELECT 'orders_discount_mismatch',
           'Order discount_amount must equal the sum of its line discounts',
           (SELECT count(*) FROM (
                SELECT o.order_id
                  FROM raw.orders o
                  JOIN raw.order_items i ON i.order_id = o.order_id
                 GROUP BY o.order_id, o.discount_amount
                HAVING round(sum(i.line_discount), 2) <> o.discount_amount
            ) mismatches)

    UNION ALL
    SELECT 'orders_in_future',
           'Order timestamps must not be in the future',
           (SELECT count(*) FROM raw.orders WHERE order_ts > now())

    UNION ALL
    SELECT 'orders_before_signup',
           'Customers cannot order before they registered',
           (SELECT count(*) FROM raw.orders o
              JOIN raw.customers c ON c.customer_id = o.customer_id
             WHERE o.order_ts::date < c.signup_date)

    UNION ALL
    SELECT 'order_items_before_launch',
           'Products cannot be sold before their launch date',
           (SELECT count(*) FROM raw.order_items i
              JOIN raw.orders o   ON o.order_id = i.order_id
              JOIN raw.products p ON p.product_id = i.product_id
             WHERE p.launch_date > o.order_ts::date)

    UNION ALL
    SELECT 'control_group_exposed',
           'Control-arm assignments must never be flagged as exposed',
           (SELECT count(*) FROM raw.campaign_assignments
             WHERE arm = 'control' AND exposed)

    UNION ALL
    SELECT 'campaign_orders_not_assigned',
           'Attributed orders must belong to an exposed (treatment) customer of that campaign',
           (SELECT count(*) FROM raw.orders o
             WHERE o.campaign_id IS NOT NULL
               AND NOT EXISTS (
                    SELECT 1 FROM raw.campaign_assignments a
                     WHERE a.campaign_id = o.campaign_id
                       AND a.customer_id = o.customer_id
                       AND a.arm = 'treatment'
                       AND a.exposed))

    UNION ALL
    SELECT 'campaign_orders_outside_window',
           'Attributed orders must fall inside the campaign window',
           (SELECT count(*) FROM raw.orders o
              JOIN raw.marketing_campaigns c ON c.campaign_id = o.campaign_id
             WHERE o.order_ts::date < c.start_date
                OR o.order_ts::date > c.end_date)

    UNION ALL
    SELECT 'payments_amount_mismatch',
           'Payment amount must equal the order total',
           (SELECT count(*) FROM raw.payments p
              JOIN raw.orders o ON o.order_id = p.order_id
             WHERE p.amount <> o.order_total)

    UNION ALL
    SELECT 'payment_status_mismatch',
           'Payment status must be consistent with the order status',
           (SELECT count(*) FROM raw.payments p
              JOIN raw.orders o ON o.order_id = p.order_id
             WHERE (o.order_status = 'completed' AND p.payment_status <> 'captured')
                OR (o.order_status = 'refunded'  AND p.payment_status <> 'refunded')
                OR (o.order_status = 'cancelled' AND p.payment_status <> 'voided'))

    UNION ALL
    SELECT 'duplicate_customer_email',
           'Customer emails are unique',
           (SELECT count(*) FROM (
                SELECT email FROM raw.customers GROUP BY email HAVING count(*) > 1
            ) duplicates)
)
SELECT check_id, description, failing_rows,
       CASE WHEN failing_rows = 0 THEN 'PASS' ELSE 'FAIL' END AS result
  FROM checks
 ORDER BY result DESC, check_id;

