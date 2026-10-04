# E-commerce Customer & Revenue Analytics

A production-shaped analytics project that turns a synthetic e-commerce dataset into revenue,
customer, retention and marketing insight — built with Python, SQL and PostgreSQL, and
finished with statistics, business visualisation and a BI dashboard.

> **Portfolio project.** The company ("NovaCart"), its customers and every order are
> synthetic, generated from documented statistical assumptions with a fixed random seed.
> Nothing here is client work or real customer data.

## Business problem

An e-commerce retailer knows its revenue is growing but cannot answer basic commercial
questions with confidence: which categories and customers actually drive revenue, whether
recent cohorts retain, which campaigns created value rather than noise, and where a retention
or reactivation effort would pay back.

This project builds the data platform and the analysis to answer those questions:

| # | Question | Where it is answered |
| --- | --- | --- |
| 1 | How is revenue changing over time? | ✅ Revenue analysis (milestone 3) |
| 2 | Which products and categories drive revenue? | ✅ Product analysis (milestone 3) |
| 3 | What is average order value and how does it move? | ✅ Revenue analysis (milestone 3) |
| 4 | Which customers contribute the most revenue? | ✅ Customer value analysis (milestone 3) |
| 5 | What is retention by acquisition cohort? | ✅ Cohort retention (milestone 4) |
| 6 | What RFM segments exist? | ✅ RFM segmentation (milestone 4) |
| 7 | Which segments generate revenue and retain best? | ✅ Segment value + cohort retention (milestone 4) |
| 8 | Which campaigns are associated with higher customer value? | ✅ Campaign analysis (milestone 4) |
| 9 | Are those campaign differences statistically meaningful? | ✅ Statistical testing with FDR control (milestone 4) |
| 10 | What business actions follow? | Executive summary (milestone 9) |

## Architecture

```
synthetic generator → CSV + manifest → PostgreSQL raw layer → analytical SQL
      → Python analysis → statistics → visualisation → BI dashboard
```

* **Generator** – deterministic, seeded, with a documented ground truth
  (`src/novacart/synthetic`).
* **Warehouse** – PostgreSQL 16 with `raw`, `analytics` and `meta` schemas; constraints,
  generated money columns and indexes defined in `sql/`.
* **Analytical layer** – reusable SQL views: staging → order/line facts → revenue, customer,
  product, category and campaign marts, with raw-versus-analytics reconciliation checks
  (`sql/10..90_*.sql`, built by `novacart.warehouse`).
* **Analysis** – reusable Python over SQL (`src/novacart/analysis`, milestones 3–6).
* **Evidence** – pytest for transformations and calculations; SQL checks for the loaded data.

Full detail: [docs/architecture.md](docs/architecture.md) ·
[docs/data_model.md](docs/data_model.md) · [docs/data_generation.md](docs/data_generation.md) ·
[docs/testing.md](docs/testing.md).

## Dataset

24 months of trading (2024-10-01 → 2026-09-30) from a fictional mixed-category European
retailer. Default run with seed `20261004`:

| Table | Rows | Grain |
| --- | ---: | --- |
| `customers` | 15,000 | customer |
| `products` | 1,200 | product |
| `marketing_campaigns` | 20 | campaign (randomised treatment/control holdout) |
| `campaign_assignments` | 44,090 | customer × campaign |
| `orders` | 84,263 | order header |
| `order_items` | 207,374 | order line |
| `payments` | 84,263 | payment per order |

Headline characteristics: €15.9m net revenue, €188 average order value, 2.46 items per order,
52% of registered customers purchase, 57% of them buy again, strong Black Friday/Christmas
seasonality, and a category mix led by Electronics (31%), Home & Kitchen (23%) and Fashion
(20%).

## Tech stack

Python 3.12+ · PostgreSQL 16 · SQL · pandas · NumPy · SciPy/statsmodels · Matplotlib ·
pytest · Power BI (final dashboard) · docker compose · `pyproject.toml`

## Quickstart

```bash
# 1. configuration
cp .env.example .env                     # PowerShell: Copy-Item .env.example .env

# 2. PostgreSQL
docker compose up -d                     # PostgreSQL on localhost:5433

# 3. environment
python -m venv .venv
. .venv/Scripts/activate                 # Windows PowerShell
python -m pip install -e ".[dev]"

# 4. generate the synthetic dataset (deterministic, ~6 seconds)
python scripts/generate_data.py

# 5. load it into PostgreSQL (~15 seconds)
python scripts/load_raw.py

# 6. verify the loaded data
python scripts/check_raw_data.py

# 7. build the analytical SQL layer and reconcile it against the raw layer
python scripts/build_analytics_layer.py
python scripts/run_reconciliation.py

# 8. business + advanced analysis: KPI, product, customer, RFM, cohort and campaign tables and figures
python scripts/build_business_analysis.py

# 9. notebooks (optional; they re-run the analysis and embed the figures)
jupyter nbconvert --to notebook --execute --inplace notebooks/0*.ipynb

# 10. tests
python -m pytest -q
```

Expected outcome: 15,000 customers / 84,263 orders / 207,374 order lines loaded, 59 in-memory
validation checks, 15 SQL data-quality checks and 20 analytical reconciliation checks with
zero failures, 25 analysis tables and 16 figures written to `outputs/`.

### Command line entry points

```bash
novacart-generate --customers 2000 --products 300 --campaigns 8 --orders 9000
novacart-generate --no-write                 # validate in memory only
novacart-load --data-dir data/raw --keep-existing
novacart-build-analytics                     # (re)create the analytics views
novacart-reconcile                            # reconcile analytics against raw
novacart-analyze                              # KPI tables, product/customer analysis, figures
```

## Business analytics (Milestone 3)

The Python analytical layer reads the published SQL facts and marts (never the raw tables),
applies descriptive analysis, and writes business tables and figures. Reusable logic lives in
`src/novacart/analytics/`; the notebook only presents results.

```bash
python scripts/build_business_analysis.py                 # tables + figures + console KPIs
jupyter nbconvert --to notebook --execute --inplace notebooks/01_business_analysis.ipynb
```

Outputs: 15 CSV tables in `outputs/tables/` and 7 figures in `outputs/figures/`
(monthly revenue, monthly orders, monthly AOV, revenue by category, top 10 products by revenue,
customer revenue distribution, revenue by country).

| Module | Responsibility |
| --- | --- |
| `analytics/common.py` | marts loader, recognition filter, safe division, % change, rolling sums |
| `analytics/revenue.py` | revenue/order summary, revenue by dimension |
| `analytics/kpis.py` | the canonical business KPI snapshot |
| `analytics/trends.py` | daily/weekly/monthly series, rolling windows, month-over-month |
| `analytics/products.py` | category and product performance, top-N, declining products |
| `analytics/customers.py` | country, segments, revenue deciles, concentration, top customers |
| `analytics/plots.py` | reusable business charts with deterministic filenames |
| `analytics/report.py` | orchestration and the `novacart-analyze` command |

### Metric definitions

Every number derives from the analytical SQL layer, so these definitions are the same ones the
dashboard will use.

| Metric | Definition |
| --- | --- |
| Revenue | recognised net merchandise revenue: `items_subtotal - discount_amount` on `completed` orders. Refunds and cancellations excluded; shipping and VAT excluded |
| Total orders | count of revenue-recognised orders |
| Units | units on revenue-recognised order lines |
| Unique customers | customers with at least one recognised order |
| Average order value (AOV) | revenue / recognised orders |
| Average units per order | units / recognised orders |
| Repeat customer | a customer with **two or more** recognised orders |
| Repeat customer rate | repeat customers / purchasing customers |
| Revenue per customer | revenue / purchasing customers. `revenue_per_registered_customer` (all 15,000 registered customers) is reported separately rather than blended |
| Rolling revenue | trailing sum including the current day over a complete daily calendar: `revenue_rolling_7d`, `revenue_rolling_30d` |
| Month-over-month change | absolute difference and percentage change versus the immediately preceding calendar month, on a gap-free monthly calendar. A zero or missing base month reports `n/a` (NaN) instead of infinite growth |
| Product ranking | recognised revenue (ties broken by product id). A separate ranking by recognised units is always shown, because the two lists differ |
| Declining product | prior-window recognised units ≥ 10 **and** unit change ≤ −30% between two adjacent 90-day windows ending on the last order date in the data (never the wall clock) |
| Customer revenue decile | equal-count deciles over purchasing customers, decile 1 = lowest revenue, decile 10 = highest |

## Advanced analytics (Milestone 4)

RFM segmentation, cohort retention and campaign evaluation with statistical testing. The same
`novacart-analyze` command produces the tables and figures; three notebooks present the findings.

```bash
python scripts/build_business_analysis.py                 # 25 tables and 16 figures
jupyter nbconvert --to notebook --execute --inplace notebooks/02_customer_segmentation.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/03_cohort_analysis.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/04_campaign_analysis.ipynb
```

| Component | Method | Outputs |
| --- | --- | --- |
| RFM | quintile scores (ties broken by customer id) with priority-ordered segment rules | `rfm_customers`, `rfm_segments`, `rfm_segment_scores` + 3 figures |
| Cohorts | monthly cohorts by first purchase month, retention by month offset, cumulative revenue | `cohort_sizes`, `cohort_retention`, `cohort_retention_matrix`, `cohort_revenue` + 3 figures |
| Campaigns | customer-level intention-to-treat comparison, Welch t-test, 95% CI, bootstrap and rank checks, Hedges' g, Benjamini-Hochberg FDR | `campaign_comparison`, `campaign_statistics`, `campaign_significance_overview` + 3 figures |

Full method detail, including the segment rules, the statistical test rationale and the known
limitations: [docs/analytics_methods.md](docs/analytics_methods.md).

> **Real-world limitation.** The dataset simulates randomised campaign assignment, while real
> client data often contains confounding, selection bias, targeting effects, and non-random
> exposure. The campaign effect estimates demonstrate the method and are not a transferable
> client result.

### Headline results (default dataset)

| Finding | Value |
| --- | --- |
| Champions segment | 2,201 customers (14.7% of customers) generating 84.7% of revenue |
| Segments with no repeat buyers yet | Potential Loyalists, New Customers, Needs Attention, Dormant, Never Purchased |
| Cohort retention | 24 monthly cohorts; median month-1 activity retention 21.3%. The 2024-10 cohort (73%) is left-censored - customers already active before the window - and should be excluded from benchmarks |
| Campaigns tested | 20, of which 8 are statistically significant at FDR 5% and 11 clear the practical thresholds |
| Largest measured lift | +51.7% revenue per assigned customer (CMP-005, FDR-adjusted p < 0.001) |
| Directionally positive but inconclusive | 3 campaigns have practical-sized point estimates with intervals crossing zero |
| Post-hoc generator check | 8 of 11 genuinely-lifted campaigns detected, 0 of 9 placebo campaigns flagged |

## Repository layout

```
├── docker-compose.yml          PostgreSQL 16 for local development
├── pyproject.toml              dependencies, console scripts, pytest/ruff config
├── data/
│   ├── raw/                    generated CSVs (git-ignored, rebuildable)
│   └── generation_metadata/    manifest: seed, checksums, validation, ground truth
├── docs/                       architecture, data model, generation, testing, methods
├── notebooks/
│   ├── 01_business_analysis.ipynb     KPIs, trends, products, customers
│   ├── 02_customer_segmentation.ipynb RFM scoring, segments, figures
│   ├── 03_cohort_analysis.ipynb       retention matrix, heatmap, cohort revenue
│   └── 04_campaign_analysis.ipynb     campaign comparison and statistics
├── outputs/                    generated analysis artefacts (git-ignored)
│   ├── figures/                16 business charts
│   └── tables/                 25 CSV result tables
├── scripts/                    thin CLI wrappers (generate, load, checks, build analytics)
├── sql/
│   ├── 01_schemas.sql           raw / analytics / meta schemas
│   ├── 02_raw_tables.sql        tables, constraints, generated columns, indexes
│   ├── 10_staging_views.sql     cleaned staging views, calendar, analysis window
│   ├── 20_revenue_marts.sql     order/line facts, daily and monthly revenue marts
│   ├── 21_customer_marts.sql    customer features (one row per customer)
│   ├── 22_product_marts.sql     product and category performance
│   ├── 23_campaign_marts.sql    treatment/holdout campaign preparation
│   ├── 90_reconciliation_checks.sql  raw-versus-analytics reconciliations
│   └── checks/verify_raw.sql    cross-table data-quality checks
├── src/novacart/
│   ├── settings.py, db.py, logging_config.py
│   ├── synthetic/               generator (reference, entities, order simulation, writer)
│   ├── ingestion/               DDL application and COPY loading
│   ├── warehouse.py             builds the analytical SQL layer, reads reconciliation
│   └── analytics/               revenue, KPIs, trends, products, customers, RFM,
│                                cohorts, campaigns, statistics, plots, report
└── tests/                       unit, rule-injection and integration tests
```

## Reproducibility

* One seed drives every random draw through independent `SeedSequence` streams.
* `data/generation_metadata/generation_manifest.json` records the resolved configuration,
  row counts, SHA-256 checksums for every CSV, the validation report, library versions and the
  **campaign ground truth** (used by tests, never loaded into the warehouse).
* `meta.ingestion_run` records every load with row counts and checksums.
* Rebuilding from a fresh clone reproduces the same dataset and the same file hashes.

## Project status

| Milestone | Status |
| --- | --- |
| 1. Architecture, schema, project structure, synthetic data engine | ✅ complete |
| 2. Analytical SQL layer (staging views, facts, revenue/customer/product/campaign marts, reconciliation) | ✅ complete |
| 3. Business analytics in Python (revenue, trends, products, customers, KPIs, figures, notebook) | ✅ complete |
| 4. RFM segmentation, cohort retention, campaign evaluation, statistical testing | ✅ complete |
| 5. Power BI dashboard over the analytics schema | ⏳ next |
| 6. Executive summary, README findings and final polish | ⏳ |

## Licence and data notice

Code is provided for portfolio and educational use. All data is synthetic and any resemblance
to real customers, orders or companies is coincidental.

