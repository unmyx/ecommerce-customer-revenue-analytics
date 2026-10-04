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
                                │  analytical SQL (later milestone)
┌───────────────────────────────▼──────────────────────────────────────────┐
│ 3. Analytics layer                  schema analytics                      │
│    staging views -> customer features -> RFM, cohorts, campaign tests     │
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
| `novacart.analysis` *(later)* | Reusable revenue, customer, RFM, cohort and product analytics |
| `novacart.statistics` *(later)* | Hypothesis tests, effect sizes, multiple-comparison correction |
| `novacart.visualization` *(later)* | Chart builders with a consistent business style |

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
never loaded into PostgreSQL so the analysis cannot accidentally use it.

**SQL is organised by analytical purpose.** `sql/01_schemas.sql` and `sql/02_raw_tables.sql`
define the warehouse; `sql/checks/verify_raw.sql` contains runnable data-quality checks. The
staging views and marts arrive in the next milestone as `sql/10_*.sql`, `sql/20_*.sql`.

**No heavy frameworks.** pandas, numpy, SQLAlchemy and psycopg are enough for ingestion and
analysis; pytest covers the tests; docker compose runs PostgreSQL. dbt, Airflow and friends
would hide the SQL that this project is meant to demonstrate.

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
```

## Environments and reproducibility

* PostgreSQL 16 in Docker, host port `5433` (5432 is commonly taken by other local projects).
* Python 3.12+; developed and verified on 3.14 with pandas 3 and numpy 2.
* Configuration lives in `.env` (git-ignored); `.env.example` documents every variable.
* Generated artefacts are git-ignored and rebuildable: `data/raw/*` and
  `data/generation_metadata/*`.

## Extension points

* **Scale** – `GenerationConfig` accepts customer, product, campaign and order targets, so a
  full run or a fast test dataset use exactly the same code path.
* **Behaviour** – the reference tables in `novacart.synthetic.reference` hold every
  distributional assumption (channels, categories, prices, VAT, seasonality) in one place.
* **Analytics** – new analysis functions belong in `novacart.analysis`; notebooks should call
  them rather than re-implement them.

