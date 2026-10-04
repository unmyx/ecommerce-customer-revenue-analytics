-- Raw layer for the NovaCart e-commerce dataset.
--
-- Design notes
--   * Business keys are stable, human-readable text identifiers (the source system owns them).
--   * Money is stored in EUR with numeric(12,2); no floating point is used for currency.
--   * Derived amounts (net revenue, order total, line net) are generated columns so the
--     database - not the pipeline - is the single source of truth for those definitions.
--   * Revenue definitions used across the project:
--       items_subtotal  = gross merchandise value of the order lines (before any discount)
--       discount_amount = total line-level discount granted on the order
--       net_revenue     = items_subtotal - discount_amount          (recognised merchandise revenue)
--       order_total     = net_revenue + shipping_amount + tax_amount (what the customer pays)
--     Taxes and shipping are tracked but excluded from revenue metrics.

-- ---------------------------------------------------------------------------
-- customers
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.customers (
    customer_id         text        PRIMARY KEY,
    email               text        NOT NULL UNIQUE,
    first_name          text        NOT NULL,
    last_name           text        NOT NULL,
    country_code        char(2)     NOT NULL,
    city                text        NOT NULL,
    signup_date         date        NOT NULL,
    acquisition_channel text        NOT NULL,
    created_at          timestamptz NOT NULL,
    CONSTRAINT customers_email_format_chk CHECK (email LIKE '%_@_%._%'),
    CONSTRAINT customers_country_code_chk CHECK (country_code ~ '^[A-Z]{2}$'),
    CONSTRAINT customers_acquisition_channel_chk CHECK (
        acquisition_channel IN (
            'organic_search', 'paid_search', 'paid_social', 'email',
            'referral', 'direct', 'affiliate', 'display'
        )
    )
);

COMMENT ON TABLE raw.customers IS 'One row per registered customer. Signup date defines acquisition cohorts.';
COMMENT ON COLUMN raw.customers.acquisition_channel IS 'First-touch channel reported by the marketing platform.';

-- ---------------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.products (
    product_id   text          PRIMARY KEY,
    sku          text          NOT NULL UNIQUE,
    product_name text          NOT NULL,
    category     text          NOT NULL,
    subcategory  text          NOT NULL,
    brand        text          NOT NULL,
    unit_price   numeric(12,2) NOT NULL,
    unit_cost    numeric(12,2) NOT NULL,
    launch_date  date          NOT NULL,
    is_active    boolean       NOT NULL,
    CONSTRAINT products_unit_price_chk CHECK (unit_price > 0),
    CONSTRAINT products_unit_cost_chk CHECK (unit_cost >= 0 AND unit_cost <= unit_price)
);

COMMENT ON TABLE raw.products IS 'Product catalogue. unit_price is the list price valid at the end of the analysis window.';

-- ---------------------------------------------------------------------------
-- marketing_campaigns
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.marketing_campaigns (
    campaign_id    text          PRIMARY KEY,
    campaign_name  text          NOT NULL,
    channel        text          NOT NULL,
    objective      text          NOT NULL,
    target_audience text         NOT NULL,
    start_date     date          NOT NULL,
    end_date       date          NOT NULL,
    budget_eur     numeric(12,2) NOT NULL,
    created_at     timestamptz   NOT NULL,
    CONSTRAINT campaigns_dates_chk CHECK (end_date >= start_date),
    CONSTRAINT campaigns_budget_chk CHECK (budget_eur > 0),
    CONSTRAINT campaigns_channel_chk CHECK (
        channel IN ('email', 'paid_search', 'paid_social', 'display', 'affiliate', 'influencer')
    ),
    CONSTRAINT campaigns_objective_chk CHECK (
        objective IN ('acquisition', 'retention', 'reactivation', 'cross_sell', 'brand')
    )
);

COMMENT ON TABLE raw.marketing_campaigns IS 'Marketing campaign master data (~20 campaigns over the analysis window).';

-- ---------------------------------------------------------------------------
-- campaign_assignments
--
-- The campaign analysis in this project compares an exposed (treatment) group
-- with a randomised holdout (control) group, so exposure has to be a first-class
-- table rather than an implicit attribute of orders.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.campaign_assignments (
    assignment_id     text        PRIMARY KEY,
    campaign_id       text        NOT NULL REFERENCES raw.marketing_campaigns (campaign_id),
    customer_id       text        NOT NULL REFERENCES raw.customers (customer_id),
    assigned_at       timestamptz NOT NULL,
    arm               text        NOT NULL,
    exposed           boolean     NOT NULL,
    assignment_method text        NOT NULL,
    CONSTRAINT assignments_arm_chk CHECK (arm IN ('treatment', 'control')),
    CONSTRAINT assignments_control_not_exposed_chk CHECK (NOT (arm = 'control' AND exposed)),
    CONSTRAINT assignments_method_chk CHECK (assignment_method IN ('randomized_holdout')),
    CONSTRAINT assignments_unique_member_chk UNIQUE (campaign_id, customer_id)
);

COMMENT ON TABLE raw.campaign_assignments IS
    'Randomised treatment/control assignment per campaign. Control rows are the comparison group.';

-- ---------------------------------------------------------------------------
-- orders
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.orders (
    order_id              text          PRIMARY KEY,
    customer_id           text          NOT NULL REFERENCES raw.customers (customer_id),
    order_ts              timestamptz   NOT NULL,
    order_status          text          NOT NULL,
    sales_channel         text          NOT NULL,
    campaign_id           text          REFERENCES raw.marketing_campaigns (campaign_id),
    items_subtotal        numeric(12,2) NOT NULL,
    discount_amount       numeric(12,2) NOT NULL DEFAULT 0,
    shipping_amount       numeric(12,2) NOT NULL DEFAULT 0,
    tax_amount            numeric(12,2) NOT NULL DEFAULT 0,
    net_revenue           numeric(12,2)
        GENERATED ALWAYS AS (items_subtotal - discount_amount) STORED,
    order_total           numeric(12,2)
        GENERATED ALWAYS AS (items_subtotal - discount_amount + shipping_amount + tax_amount) STORED,
    currency_code         char(3)       NOT NULL DEFAULT 'EUR',
    shipping_country_code char(2)       NOT NULL,
    CONSTRAINT orders_status_chk CHECK (order_status IN ('completed', 'refunded', 'cancelled')),
    CONSTRAINT orders_sales_channel_chk CHECK (
        sales_channel IN ('web', 'mobile_app', 'marketplace', 'phone')
    ),
    CONSTRAINT orders_amounts_chk CHECK (
        items_subtotal >= 0
        AND discount_amount >= 0
        AND discount_amount <= items_subtotal
        AND shipping_amount >= 0
        AND tax_amount >= 0
    ),
    CONSTRAINT orders_currency_chk CHECK (currency_code = 'EUR')
);

COMMENT ON TABLE raw.orders IS
    'Order headers. order_status = completed is the revenue-recognised baseline; refunded and cancelled orders are excluded from revenue metrics.';
COMMENT ON COLUMN raw.orders.campaign_id IS
    'Campaign attributed to the order. Only set for customers exposed to the campaign and only inside the campaign window.';

-- ---------------------------------------------------------------------------
-- order_items
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.order_items (
    order_item_id  text          PRIMARY KEY,
    order_id       text          NOT NULL REFERENCES raw.orders (order_id),
    product_id     text          NOT NULL REFERENCES raw.products (product_id),
    quantity       integer       NOT NULL,
    unit_price     numeric(12,2) NOT NULL,
    unit_cost      numeric(12,2) NOT NULL,
    line_discount  numeric(12,2) NOT NULL DEFAULT 0,
    line_net_amount numeric(12,2)
        GENERATED ALWAYS AS (quantity * unit_price - line_discount) STORED,
    CONSTRAINT order_items_quantity_chk CHECK (quantity > 0),
    CONSTRAINT order_items_unit_price_chk CHECK (unit_price > 0),
    CONSTRAINT order_items_unit_cost_chk CHECK (unit_cost >= 0),
    CONSTRAINT order_items_discount_chk CHECK (
        line_discount >= 0 AND line_discount <= quantity * unit_price
    ),
    CONSTRAINT order_items_unique_line_chk UNIQUE (order_id, product_id)
);

COMMENT ON TABLE raw.order_items IS
    'Order lines. unit_price/unit_cost are the historical values at purchase time, not the current catalogue values.';

-- ---------------------------------------------------------------------------
-- payments
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.payments (
    payment_id         text          PRIMARY KEY,
    order_id           text          NOT NULL UNIQUE REFERENCES raw.orders (order_id),
    payment_method     text          NOT NULL,
    payment_status     text          NOT NULL,
    amount             numeric(12,2) NOT NULL,
    refunded_amount    numeric(12,2) NOT NULL DEFAULT 0,
    paid_at            timestamptz   NOT NULL,
    provider_reference text          NOT NULL UNIQUE,
    CONSTRAINT payments_method_chk CHECK (
        payment_method IN ('card', 'paypal', 'wallet', 'klarna', 'sepa_debit', 'gift_card', 'bank_transfer')
    ),
    CONSTRAINT payments_status_chk CHECK (
        payment_status IN ('captured', 'refunded', 'voided', 'failed')
    ),
    CONSTRAINT payments_amount_chk CHECK (amount >= 0 AND refunded_amount >= 0 AND refunded_amount <= amount),
    CONSTRAINT payments_status_consistency_chk CHECK (
        (payment_status = 'refunded' AND refunded_amount > 0)
        OR (payment_status <> 'refunded' AND refunded_amount = 0)
    )
);

COMMENT ON TABLE raw.payments IS
    'One payment record per order (the source system settles each order in a single transaction).';

-- ---------------------------------------------------------------------------
-- indexes supporting the analytical queries
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS orders_customer_id_idx      ON raw.orders (customer_id);
CREATE INDEX IF NOT EXISTS orders_order_ts_idx         ON raw.orders (order_ts);
CREATE INDEX IF NOT EXISTS orders_campaign_id_idx      ON raw.orders (campaign_id);
CREATE INDEX IF NOT EXISTS orders_status_ts_idx        ON raw.orders (order_status, order_ts);
CREATE INDEX IF NOT EXISTS order_items_order_id_idx    ON raw.order_items (order_id);
CREATE INDEX IF NOT EXISTS order_items_product_id_idx  ON raw.order_items (product_id);
CREATE INDEX IF NOT EXISTS products_category_idx       ON raw.products (category);
CREATE INDEX IF NOT EXISTS customers_signup_date_idx   ON raw.customers (signup_date);
CREATE INDEX IF NOT EXISTS assignments_customer_idx    ON raw.campaign_assignments (customer_id);
CREATE INDEX IF NOT EXISTS assignments_campaign_idx    ON raw.campaign_assignments (campaign_id, arm);

-- ---------------------------------------------------------------------------
-- ingestion bookkeeping
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta.ingestion_run (
    run_id            bigserial   PRIMARY KEY,
    started_at        timestamptz NOT NULL,
    finished_at       timestamptz NOT NULL,
    status            text        NOT NULL,
    generator_seed    bigint,
    rows_loaded       jsonb       NOT NULL,
    source_checksums  jsonb       NOT NULL,
    notes             text,
    CONSTRAINT ingestion_run_status_chk CHECK (status IN ('success', 'failed'))
);

COMMENT ON TABLE meta.ingestion_run IS
    'One row per raw-layer load, including row counts and source file checksums for reproducibility.';

CREATE TABLE IF NOT EXISTS meta.data_quality_result (
    check_id     text        PRIMARY KEY,
    check_group  text        NOT NULL,
    description  text        NOT NULL,
    passed       boolean     NOT NULL,
    failing_rows bigint      NOT NULL,
    executed_at  timestamptz NOT NULL
);

COMMENT ON TABLE meta.data_quality_result IS
    'Outcome of the SQL data-quality checks in sql/checks/. Populated by scripts/check_raw_data.py.';

