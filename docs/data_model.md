# Data model

## Grain

| Table | Grain | Rows (default run) |
| --- | --- | --- |
| `raw.customers` | one registered customer | 15,000 |
| `raw.products` | one catalogue product | 1,200 |
| `raw.marketing_campaigns` | one campaign | 20 |
| `raw.campaign_assignments` | one customer × campaign assignment | ~44,000 |
| `raw.orders` | one order header | ~84,000 |
| `raw.order_items` | one product line within an order | ~207,000 |
| `raw.payments` | one payment settlement per order | ~84,000 |

```
customers 1 ──── n orders 1 ──── n order_items n ──── 1 products
    │                 │
    │                 └──── 1 payments
    │
    └──── n campaign_assignments n ──── 1 marketing_campaigns
                          ▲
                          └── orders.campaign_id (attribution, nullable)
```

## Tables

### raw.customers

| Column | Type | Notes |
| --- | --- | --- |
| `customer_id` | text | PK, `CUST-000001` |
| `email` | text | unique, synthetic `@mail.novacart.example` domain |
| `first_name`, `last_name` | text | |
| `country_code` | char(2) | ISO code; drives VAT rate and shipping country |
| `city` | text | consistent with `country_code` |
| `signup_date` | date | acquisition date; cohorts can precede the order window |
| `acquisition_channel` | text | first-touch channel (8 values) |
| `created_at` | timestamptz | signup timestamp |

### raw.products

| Column | Type | Notes |
| --- | --- | --- |
| `product_id` | text | PK, `PRD-00001` |
| `sku` | text | unique, `NC-<CAT>-00001` |
| `product_name`, `brand`, `category`, `subcategory` | text | 8 categories |
| `unit_price` | numeric(12,2) | list price at the end of the analysis window |
| `unit_cost` | numeric(12,2) | purchase cost; `unit_cost <= unit_price` |
| `launch_date` | date | products are never sold before launch |
| `is_active` | boolean | discontinued products keep their history |

### raw.marketing_campaigns

| Column | Type | Notes |
| --- | --- | --- |
| `campaign_id` | text | PK, `CMP-001` |
| `campaign_name`, `channel`, `objective`, `target_audience` | text | |
| `start_date`, `end_date` | date | inside the analysis window |
| `budget_eur` | numeric(12,2) | planned spend |
| `created_at` | timestamptz | campaign setup timestamp |

### raw.campaign_assignments

| Column | Type | Notes |
| --- | --- | --- |
| `assignment_id` | text | PK, `ASG-0000001` |
| `campaign_id`, `customer_id` | text | FKs; unique together |
| `assigned_at` | timestamptz | assignment timestamp |
| `arm` | text | `treatment` or `control` |
| `exposed` | boolean | treatment customers may still be unexposed; control is never exposed |
| `assignment_method` | text | `randomized_holdout` |

### raw.orders

| Column | Type | Notes |
| --- | --- | --- |
| `order_id` | text | PK, `ORD-0000001`, chronological |
| `customer_id` | text | FK |
| `order_ts` | timestamptz | inside the analysis window, never before signup |
| `order_status` | text | `completed`, `refunded`, `cancelled` |
| `sales_channel` | text | `web`, `mobile_app`, `marketplace`, `phone` |
| `campaign_id` | text | FK, nullable; set only for exposed treatment customers inside the window |
| `items_subtotal` | numeric(12,2) | gross merchandise value of the lines |
| `discount_amount` | numeric(12,2) | sum of line discounts; `<= items_subtotal` |
| `shipping_amount`, `tax_amount` | numeric(12,2) | not part of revenue |
| `net_revenue` | numeric(12,2) | **generated**: `items_subtotal - discount_amount` |
| `order_total` | numeric(12,2) | **generated**: `net_revenue + shipping_amount + tax_amount` |
| `currency_code` | char(3) | always `EUR` |
| `shipping_country_code` | char(2) | customer country at purchase time |

### raw.order_items

| Column | Type | Notes |
| --- | --- | --- |
| `order_item_id` | text | PK, `OIT-00000001` |
| `order_id`, `product_id` | text | FKs; unique together (no duplicate line for a product) |
| `quantity` | integer | `> 0` |
| `unit_price` | numeric(12,2) | historical price paid, including inflation and promo |
| `unit_cost` | numeric(12,2) | historical cost, used for margin analysis |
| `line_discount` | numeric(12,2) | `0 <= line_discount <= quantity * unit_price` |
| `line_net_amount` | numeric(12,2) | **generated**: `quantity * unit_price - line_discount` |

### raw.payments

| Column | Type | Notes |
| --- | --- | --- |
| `payment_id` | text | PK, `PMT-0000001` |
| `order_id` | text | unique FK: one settlement per order |
| `payment_method` | text | card, paypal, wallet, klarna, sepa_debit, gift_card, bank_transfer |
| `payment_status` | text | `captured` (completed), `refunded`, `voided` (cancelled) |
| `amount` | numeric(12,2) | equals `orders.order_total` |
| `refunded_amount` | numeric(12,2) | `> 0` exactly when the status is `refunded` |
| `paid_at` | timestamptz | after `order_ts` |
| `provider_reference` | text | unique provider id |

## Metric definitions

| Metric | Definition | Notes |
| --- | --- | --- |
| Gross merchandise value | `orders.items_subtotal` | before discounts |
| Net revenue | `orders.net_revenue` | recognised merchandise revenue |
| Recognised revenue | net revenue on `order_status = 'completed'` | refunded/cancelled orders are excluded |
| Average order value | recognised net revenue / completed orders | |
| Units sold | `sum(order_items.quantity)` | |
| Gross margin | `line_net_amount - quantity * unit_cost` | per line, then aggregated |
| Repeat purchase rate | share of purchasing customers with ≥ 2 orders | |
| Cohort | month of a customer's first order | all first orders fall inside the analysis window |
| Retention month *n* | share of a cohort ordering again in month *n* after acquisition | |
| RFM score | recency, frequency, monetary quintiles (1–5) | rules defined with the segmentation milestone |

## Integrity rules enforced by the database

Primary keys and foreign keys, plus:

* amounts are non-negative and discounts never exceed the value of the line or the order;
* `unit_cost <= unit_price` on products and order lines;
* campaign windows, budgets, order statuses, payment methods and channels are constrained by
  `CHECK` constraints;
* control-arm assignments can never be flagged as exposed;
* a campaign assignment is unique per customer and campaign.

Rules that span tables (for example "order subtotal equals the sum of its lines") cannot be
expressed as a simple `CHECK`. They are enforced twice instead: in Python before anything is
written (`validate_dataset`) and in SQL after loading (`sql/checks/verify_raw.sql`).

## Analytical layer (analytics schema)

The analytical layer is a set of views rebuilt by `scripts/build_analytics_layer.py`
(`novacart.warehouse`). It follows one lineage:

```
raw → staging (stg_*) → facts (fct_*) → marts (mart_*) → Python / BI
```

| Object | Grain | Notes |
| --- | --- | --- |
| `analytics.analysis_window` | one row | first order date, `analysis_end_date`, window length, order count |
| `analytics.dim_date` | one row per day | calendar spine for the loaded window; ISO week, month, weekend flag |
| `analytics.stg_customers` | customer | cleaned customer attributes (email excluded) |
| `analytics.stg_products` | product | catalogue with list price, cost and list margin |
| `analytics.stg_orders` | order | raw order amounts plus resolved customer attributes |
| `analytics.stg_order_lines` | order line | line amounts plus order context and product attributes |
| `analytics.stg_campaigns` | campaign | campaign master with duration and daily budget |
| `analytics.stg_campaign_assignments` | customer × campaign | arm, exposure flag (`is_exposed_treatment`) and campaign attributes |
| `analytics.fct_orders` | order | recognition flags, line count, units, gross merchandise amount, canonical and recognised revenue |
| `analytics.fct_order_lines` | order line | cost, gross profit, margin and recognised line revenue |
| `analytics.mart_revenue_daily` | day | calendar-spined revenue with 7-day and 30-day rolling metrics |
| `analytics.mart_revenue_monthly` | month | revenue, orders, customers, units, AOV |
| `analytics.mart_customer_features` | customer | first/last order, frequency, revenue, units, AOV, repeat flag, recency and lifetime |
| `analytics.mart_product_performance` | product | units, orders, unique customers, revenue, realised price, margin, ranks and revenue share |
| `analytics.mart_category_performance` | category | category rollup with share and rank |
| `analytics.mart_campaign_customer_outcomes` | campaign × customer | pre-window, in-window and post-window orders and revenue by arm |
| `analytics.mart_campaign_performance` | campaign | treatment/holdout summary with unadjusted descriptive lifts |
| `analytics.reconciliation_checks` | check | raw-versus-analytics reconciliation, one row per check |

### Analytical metric definitions

These definitions extend the metric table above and are the ones every later milestone must
reuse:

| Metric | Analytical definition |
| --- | --- |
| Revenue (all facts and marts) | `fct_orders.recognised_net_revenue` / `fct_order_lines.recognised_line_net_revenue`, i.e. net revenue of completed orders |
| Average order value | revenue / recognised orders (daily, monthly, customer or campaign grain) |
| Units | `recognised_units`, i.e. units on completed orders |
| Repeat customer | at least two recognised orders (`mart_customer_features.repeat_customer`) |
| Days since last order | `analysis_window.analysis_end_date - last_order_date` |
| Customer lifetime days | `last_order_date - first_order_date` |
| Average days between orders | `(last_order_date - first_order_date) / (total_orders - 1)` for customers with two or more orders |
| Realised selling price | recognised product revenue / units sold (after line discounts) |
| Gross margin | recognised line revenue − line cost (`quantity × unit_cost`) |
| Campaign exposure | `stg_campaign_assignments.is_exposed_treatment` (treatment arm and exposed) |
| Campaign window outcome | recognised orders and revenue between `campaign.start_date` and `campaign.end_date` for an assigned customer |

The layer is verified by 20 reconciliation checks (`analytics.reconciliation_checks`) plus
the pytest suite in `tests/test_analytics_layer.py`.


