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

