# Architecture

## Purpose

NovaCart is a portfolio-scale but production-shaped analytics platform. It shows how a
synthetic-but-realistic e-commerce dataset moves from generation, through a PostgreSQL
warehouse, into analysis, statistics and business reporting.

Two rules shape every decision in this repository:

1. **The database and Python library are the source of truth**, not notebooks and not
   hand-maintained spreadsheets. Notebooks and dashboards consume results; they do not own
   calculation logic.
2. **Every number must be reproducible from a fresh clone** with a documented seed.

## Layers

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 1. Synthetic source system          src/novacart/synthetic/               │
│    deterministic generator -> CSV files in data/raw/                      │
│    manifest + checksums in data/generation_metadata/                      │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  COPY (psycopg)
┌───────────────────────────────▼──────────────────────────────────────────┐
│ 2. PostgreSQL raw layer             sql/02_raw_tables.sql                 │
│    schema raw  : customers, products, orders, order_items, payments,      │
│                  marketing_campaigns, campaign_assignments                │
│    schema meta : ingestion runs, data-quality results                     │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  analytical SQL (views)
┌───────────────────────────────▼──────────────────────────────────────────┐
│ 3. Analytics layer                  sql/10..90_*.sql                      │
│    stg_* (cleaned) -> fct_* (order/line facts) -> mart_* (revenue,        │
│    customer, product, category, campaign) -> reconciliation checks        │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │  pandas / statsmodels
┌───────────────────────────────▼──────────────────────────────────────────┐
│ 4. Analysis, statistics, visualisation, BI                                │
│    notebooks (findings), outputs/ (charts, tables), powerbi/ (dashboard)   │
└──────────────────────────────────────────────────────────────────────────┘
```

## Python package layout

| Module | Responsibility |
| --- | --- |
| `novacart.settings` | Environment-driven configuration (`.env`), project paths |
| `novacart.db` | PostgreSQL helpers: engine, transactions, SQL file runner, COPY |
| `novacart.logging_config` | One logging configuration for every CLI |
| `novacart.synthetic` | The generator: reference data, entity builders, validation, writer, CLI |
| `novacart.ingestion` | Applies the DDL and bulk-loads generated CSVs into `raw` |
| `novacart.warehouse` | Builds the analytical SQL layer in dependency order; reconciliation reader |
| `novacart.analytics` | Analytics over the marts: data access, revenue, KPIs, trends, products, customers, RFM, cohorts, campaigns, statistics, plots, report |
| `novacart.statistics` *(later)* | Hypothesis tests, effect sizes, multiple-comparison correction |
| `novacart.visualization` *(later)* | Dashboard-oriented visual polish on top of `analytics.plots` |

Planned milestones and their entry points are listed in the README.

## Key design decisions

**The raw layer holds source-shaped tables only.** No RFM score, cohort index or margin
percentage is stored in `raw`. Those are derived, and deriving them in SQL keeps a single
definition for every metric.

**Derived money columns are generated columns.** `orders.net_revenue`, `orders.order_total`
and `order_items.line_net_amount` are computed by PostgreSQL, so a revenue definition cannot
drift between Python, SQL and BI.

**Exposure is a first-class table.** The brief asks whether campaign differences are
statistically meaningful, which is only answerable with a comparison group. Each campaign
therefore has a randomised `treatment` / `control` assignment (`raw.campaign_assignments`),
and order-level attribution is restricted to exposed treatment customers inside the campaign
window.

**The ground truth stays out of the warehouse.** The generator knows the true lift of every
campaign. That information is written to `data/generation_metadata/generation_manifest.json`
so tests can verify that the analysis recovers the designed effects, and it is deliberately
never loaded into PostgreSQL so the analysis cannot accidentally use it. A test asserts that
no analytics view references it.

**SQL is organised by analytical purpose.** Schema and raw tables live in `01_schemas.sql`
and `02_raw_tables.sql`; `sql/checks/` holds runnable data-quality checks; the analytical
layer is split into `10_staging_views.sql`, `20_revenue_marts.sql`, `21_customer_marts.sql`,
`22_product_marts.sql`, `23_campaign_marts.sql` and `90_reconciliation_checks.sql`.

**No heavy frameworks.** pandas, numpy, SQLAlchemy and psycopg are enough for ingestion and
analysis; pytest covers the tests; docker compose runs PostgreSQL. dbt, Airflow and friends
would hide the SQL that this project is meant to demonstrate.

## Analytical SQL layer (Milestone 2)

The analytics schema is a set of **views**, rebuilt as a unit in dependency order by
`scripts/build_analytics_layer.py` (`novacart.warehouse`). Views keep the layer always current
with the raw data, and the build is idempotent: every file drops its own objects (with
`CASCADE`) and recreates them.

```
raw → staging → facts → marts → Python / BI
```

| Layer | Objects | Grain / purpose |
| --- | --- | --- |
| Support | `analysis_window`, `dim_date` | reporting window and daily calendar |
| Staging | `stg_customers`, `stg_products`, `stg_orders`, `stg_order_lines`, `stg_campaigns`, `stg_campaign_assignments` | cleaned, renamed, foreign keys resolved; no aggregation |
| Facts | `fct_orders`, `fct_order_lines` | published order-grain and line-grain facts with recognition flags, units, cost and margin |
| Revenue marts | `mart_revenue_daily`, `mart_revenue_monthly` | calendar-spined revenue series with 7/30-day rolling metrics |
| Customer mart | `mart_customer_features` | one row per registered customer, including non-purchasers |
| Product marts | `mart_product_performance`, `mart_category_performance` | units, orders, customers, realised price, margin, ranks and revenue share |
| Campaign marts | `mart_campaign_customer_outcomes`, `mart_campaign_performance` | treatment/holdout outcomes per customer and per campaign |
| Checks | `reconciliation_checks` | 20 raw-versus-analytics reconciliation tests |

### Revenue rule (single definition, unchanged since Milestone 1)

* `raw.orders.net_revenue` is the canonical order-level revenue amount
  (`items_subtotal - discount_amount`, all order statuses).
* **Revenue** in every fact and mart means *recognised net merchandise revenue*:
  `net_revenue` for orders with `order_status = 'completed'`, otherwise zero.
* Shipping and VAT are carried as separate columns and are never part of revenue.
* No file introduces an alternative revenue formula; marts aggregate
  `fct_orders.recognised_net_revenue` / `fct_order_lines.recognised_line_net_revenue`.

### Campaign rules carried over from the experiment design

* Membership and arm come from `raw.campaign_assignments`; `control` is the randomised holdout.
* `is_exposed_treatment` marks treatment members who were actually exposed.
* `orders.campaign_id` is only ever set for exposed treatment customers inside the campaign
  window, so attributed orders are a subset of treatment behaviour and never of control.
* `mart_campaign_customer_outcomes` reports pre-window (90 days), in-window and post-window
  (30 days) behaviour per assigned customer — the input for the later statistical tests.
* The `unadjusted_lift_*` columns are raw descriptive differences, explicitly not causal
  estimates; significance testing belongs to the statistics milestone.

## Python analytics layer (Milestone 3)

The Python layer is deliberately thin and testable:

```
PostgreSQL marts  →  novacart.analytics.common (loading)  →  pure calculation functions
                  →  clean DataFrames  →  tables (CSV) + figures (PNG) + notebook
```

| Module | Responsibility |
| --- | --- |
| `analytics/common.py` | loads published relations, applies the recognition filter, and provides `safe_divide`, `percentage_change`, `rolling_sum` and formatting helpers |
| `analytics/revenue.py` | revenue/order summary and revenue by dimension |
| `analytics/kpis.py` | the canonical one-row business KPI snapshot |
| `analytics/trends.py` | daily/weekly/monthly series, rolling windows, month-over-month change |
| `analytics/products.py` | category and product performance, top-N by revenue and units, declining products |
| `analytics/customers.py` | country summary, customer segments, revenue deciles, concentration, top customers |
| `analytics/plots.py` | reusable business charts; deterministic filenames in `outputs/figures/` |
| `analytics/report.py` | orchestration (`novacart-analyze`) that writes `outputs/tables/` and `outputs/figures/` |

### Advanced analytics (Milestone 4)

| Module | Responsibility |
| --- | --- |
| `analytics/rfm.py` | quintile RFM scores with deterministic tie-breaking and priority-ordered segments (`segment_for_scores` is the single source of truth for the rules) |
| `analytics/cohorts.py` | monthly cohorts by first purchase month, retention by month offset on an observability-aware grid, cumulative cohort revenue, and invariant validation |
| `analytics/statistics.py` | Welch t-test, confidence intervals, percentile bootstrap, Hedges' g, Benjamini-Hochberg adjustment and effect-size labels |
| `analytics/campaigns.py` | customer-level intention-to-treat comparison, campaign results table, significance flags, business interpretation and the significance overview |

The Milestone 4 calculations follow three rules:

1. **The unit of analysis is the customer**, not the order, for every campaign statistic.
2. **The decision rules are pre-specified in code** (test, alpha, FDR level, practical
   thresholds) so they cannot be chosen after seeing the results.
3. **The generator's ground truth is never read** by the package: the true lift lives outside
   PostgreSQL and is used only by a clearly-marked post-hoc validation cell in
   `notebooks/04_campaign_analysis.ipynb` plus tests that assert the package never references it.

Method detail lives in [analytics_methods.md](analytics_methods.md).

Design rules:

* **Calculations are pure functions over DataFrames.** Only `common.load_*` touches the
  database, which is what makes the metric tests fast and database-free.
* **Fallbacks exist for tests, not for production.** A frame without
  `is_revenue_recognised` is treated as fully recognised and `net_revenue`/`total_units` are
  accepted when the `recognised_*` columns are absent. Production always passes the facts.
* **Calendars are explicit.** Daily, weekly and monthly series are filled onto complete
  calendars bounded by the loaded order period, so rolling windows and month-over-month
  comparisons stay correct when a period has no recognised revenue.
* **The Python layer is verified against SQL.** `tests/test_analytics_integration.py` compares
  category, product, monthly and 7/30-day rolling aggregates with the corresponding marts.

## Data flow (current milestone)

```
novacart-generate                      scripts/generate_data.py
  reference.validate_reference_data()
  generate_customers  ─┐
  generate_products    │  five independent RNG streams
  generate_campaigns   │  spawned from one root seed
  generate_orders      │
  generate_payments   ─┘
  validate_dataset()   -> in-memory integrity report (59 checks)
  write_tables()       -> data/raw/*.csv
  write_manifest()     -> data/generation_metadata/generation_manifest.json

novacart-load                          scripts/load_raw.py
  sql/01_schemas.sql, sql/02_raw_tables.sql   (idempotent)
  TRUNCATE raw.* CASCADE
  COPY each CSV into raw.<table>
  INSERT meta.ingestion_run (row counts + file checksums)

scripts/check_raw_data.py
  sql/checks/verify_raw.sql -> 15 SQL checks -> meta.data_quality_result

novacart-build-analytics               scripts/build_analytics_layer.py
  sql/10_staging_views.sql          -> staging views, calendar, analysis window
  sql/20_revenue_marts.sql          -> fct_orders, fct_order_lines, revenue marts
  sql/21_customer_marts.sql         -> mart_customer_features
  sql/22_product_marts.sql          -> product and category marts
  sql/23_campaign_marts.sql         -> campaign outcomes and performance marts
  sql/90_reconciliation_checks.sql  -> analytics.reconciliation_checks

novacart-reconcile                     scripts/run_reconciliation.py
  20 raw-versus-analytics checks; exits non-zero if any fail

novacart-analyze                       scripts/build_business_analysis.py
  load_analysis_inputs()      -> fct_orders, fct_order_lines, customer/product/category marts
  analyse()                   -> KPI snapshot, daily/weekly/monthly trends, product and
                                 customer tables, declining products, RFM segments,
                                 cohort retention, campaign statistics
  write tables                -> outputs/tables/*.csv          (25 deterministic names)
  render figures              -> outputs/figures/*.png         (16 deterministic names)

notebooks/01_business_analysis.ipynb      business KPIs, trends, products, customers
notebooks/02_customer_segmentation.ipynb  RFM methodology, segments, figures
notebooks/03_cohort_analysis.ipynb        retention matrix, heatmap, cohort revenue
notebooks/04_campaign_analysis.ipynb      campaign statistics, intervals, limitations
```

## Environments and reproducibility

* PostgreSQL 16 in Docker, host port `5433` (5432 is commonly taken by other local projects).
* `shm_size: 512mb` for the database container: analytical queries use parallel workers and
  the Docker default of 64 MB shared memory is too small.
* Python 3.12+; developed and verified on 3.14 with pandas 3 and numpy 2.
* Configuration lives in `.env` (git-ignored); `.env.example` documents every variable.
* Generated artefacts are git-ignored and rebuildable: `data/raw/*` and
  `data/generation_metadata/*`.

## Extension points

* **Scale** – `GenerationConfig` accepts customer, product, campaign and order targets, so a
  full run or a fast test dataset use exactly the same code path.
* **Behaviour** – the reference tables in `novacart.synthetic.reference` hold every
  distributional assumption (channels, categories, prices, VAT, seasonality) in one place.
* **Analytics** – new analysis functions belong in `novacart.analysis` and read the marts;
  notebooks should call them rather than re-implement them.
* **Reporting** – BI tools connect to the `analytics` schema only; the raw schema stays an
  implementation detail.

