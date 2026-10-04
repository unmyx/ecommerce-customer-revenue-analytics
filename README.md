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
| 1 | How is revenue changing over time? | Revenue analysis (milestone 3) |
| 2 | Which products and categories drive revenue? | Product analysis (milestone 3) |
| 3 | What is average order value and how does it move? | Revenue analysis (milestone 3) |
| 4 | Which customers contribute the most revenue? | Customer analysis (milestone 4) |
| 5 | What is retention by acquisition cohort? | Cohort analysis (milestone 5) |
| 6 | What RFM segments exist? | RFM segmentation (milestone 4) |
| 7 | Which segments generate revenue and retain best? | Segmentation × cohort (milestones 4–5) |
| 8 | Which campaigns are associated with higher customer value? | Marketing analysis (milestone 6) |
| 9 | Are those campaign differences statistically meaningful? | Statistical testing (milestone 6) |
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

# 8. tests
python -m pytest -q
```

Expected outcome: 15,000 customers / 84,263 orders / 207,374 order lines loaded, 59 in-memory
validation checks, 15 SQL data-quality checks and 20 analytical reconciliation checks with
zero failures.

### Command line entry points

```bash
novacart-generate --customers 2000 --products 300 --campaigns 8 --orders 9000
novacart-generate --no-write                 # validate in memory only
novacart-load --data-dir data/raw --keep-existing
novacart-build-analytics                     # (re)create the analytics views
novacart-reconcile                            # reconcile analytics against raw
```

## Repository layout

```
├── docker-compose.yml          PostgreSQL 16 for local development
├── pyproject.toml              dependencies, console scripts, pytest/ruff config
├── data/
│   ├── raw/                    generated CSVs (git-ignored, rebuildable)
│   └── generation_metadata/    manifest: seed, checksums, validation, ground truth
├── docs/                       architecture, data model, generation, testing
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
│   └── warehouse.py             builds the analytical SQL layer, reads reconciliation
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
| 3. Revenue and product analysis | ⏳ next |
| 4. Customer analytics and RFM segmentation | ⏳ |
| 5. Cohort retention analysis | ⏳ |
| 6. Marketing evaluation with statistical testing | ⏳ |
| 7. Business visualisation library and findings notebooks | ⏳ |
| 8. Power BI dashboard | ⏳ |
| 9. Executive summary and README findings | ⏳ |

## Licence and data notice

Code is provided for portfolio and educational use. All data is synthetic and any resemblance
to real customers, orders or companies is coincidental.

