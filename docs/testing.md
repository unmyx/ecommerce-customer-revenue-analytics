# Testing strategy

## Principles

* Test the **rules that protect the analysis**: keys, referential integrity, date logic, money
  arithmetic, determinism and the guard rails around generation parameters.
* Test **both sides of every SQL rule**: the same invariant is checked in Python before writing
  and in SQL after loading, so a bug in one layer is caught by the other.
* Keep the default test run fast. The suite runs against a reduced dataset (800 customers,
  120 products, 6 campaigns, 2,500 orders) with exactly the same code path as the full scale.

## Layers

| Layer | Files | What it proves |
| --- | --- | --- |
| Reference data | `tests/test_reference_data.py` | probability tables sum to 1, categories/channels are well formed |
| Sampling utilities | `tests/test_sampling.py` | weighted draws respect weights, deterministic for a seed, boundaries behave |
| SQL utilities | `tests/test_sql_utils.py` | the statement splitter handles comments, literals and dollar quotes |
| Generation | `tests/test_generation.py` | row counts, schema column order, determinism, key/amount hygiene, window logic, seasonality, plausible KPIs |
| Validation rules | `tests/test_validation_rules.py` | injected faults (duplicate key, orphan FK, over-discount, payment mismatch, duplicate line, exposed control) are detected |
| Database integration | `tests/test_database_integration.py` | DDL applies idempotently, COPY loads, the SQL checks all pass |

## Running the tests

```bash
python -m pytest -q                 # fast suite, database tests skipped
python -m pytest -q -m "not slow"   # same thing, explicit
python -m pytest -q -m slow         # full-scale generation (15k customers / 84k orders)
python -m pytest -q -m integration  # needs PostgreSQL; also requires the env flag below
NOVACART_RUN_DB_TESTS=1 python -m pytest -q -m integration
```

Integration tests truncate and reload the `raw` schema of the database in `.env`, so they are
opt-in rather than automatic.

## Data-quality checks

`validate_dataset` runs 59 in-memory checks during generation and refuses to write a dataset
that fails any of them. `sql/checks/verify_raw.sql` then runs 15 cross-table checks against
PostgreSQL after loading; `scripts/check_raw_data.py` executes them, prints a pass/fail table
and stores the result in `meta.data_quality_result`.

The SQL checks cover:

* orphan keys for orders, order items and attributed campaigns;
* one payment per order and one order per payment;
* order subtotal and discount reconciliation against the order lines;
* no orders before signup, no sales before product launch, no future timestamps;
* control-arm exposure and campaign attribution restricted to exposed treatment customers;
* attributed orders inside their campaign window;
* payment amount and payment status consistency with the order;
* duplicate customer emails.

## Planned test coverage (later milestones)

* Revenue metrics: daily/weekly/monthly aggregation, rolling 7/30-day windows, AOV definitions.
* Customer metrics: lifetime revenue, inter-purchase intervals, repeat rate, inactivity rules.
* RFM: quintile boundaries, tie handling, reproducible segment assignment, monotonicity of
  the score against the latent engagement parameter.
* Cohorts: retention matrix shape, first-period = 100%, cohort revenue attribution.
* Statistics: the treatment/control test must recover the manifest's ground truth (detect
  genuine lifts, avoid false positives on placebo campaigns) and produce correct confidence
  intervals and effect sizes.
* Visualisation: chart builders return figures with the expected axes, labels and ordering.

