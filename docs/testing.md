# Testing strategy

## Principles

* Test the **rules that protect the analysis**: keys, referential integrity, date logic, money
  arithmetic, determinism and the guard rails around generation parameters.
* Test **both sides of every rule**: the revenue definition is checked in Python before
  writing, in SQL after loading the raw layer, and again when the analytical layer is built.
* Reconciliation assertions are written as raw-versus-analytics comparisons, never as
  hard-coded totals, so they hold for the full dataset and for the reduced test dataset.
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
| Raw layer (database) | `tests/test_database_integration.py` | DDL applies idempotently, COPY loads, the 15 raw SQL checks pass |
| Analytical layer (database) | `tests/test_analytics_layer.py` | revenue reconciles order → line → customer → product → daily/monthly, keys are unique, date/recency/repeat logic is correct, rolling windows are right, campaign attribution follows the exposure and window rules, no ground truth leaks into SQL |

## Running the tests

```bash
python -m pytest -q                 # fast suite, database tests skipped
python -m pytest -q -m slow         # full-scale generation (15k customers / ~85k orders)
python -m pytest -q -m integration  # needs PostgreSQL; also set the env flag below

# database tests: they rebuild the analytical layer and reconcile it against raw
NOVACART_RUN_DB_TESTS=1 python -m pytest -q -m integration

# the same checks outside pytest
python scripts/build_analytics_layer.py
python scripts/run_reconciliation.py
```

Database tests truncate and reload the `raw` schema of the database in `.env`, so they are
opt-in. The analytical-layer tests rebuild the views first and then compare them with whatever
is in `raw`, which makes them independent of dataset size.

## Data-quality and reconciliation gates

Three independent gates protect the numbers:

1. **Generation (in memory)** – `validate_dataset` runs 59 checks and refuses to write a
   dataset that fails any of them.
2. **Raw layer (SQL)** – `sql/checks/verify_raw.sql` runs 15 cross-table checks;
   `scripts/check_raw_data.py` prints the result table and stores it in
   `meta.data_quality_result`.
3. **Analytical layer (SQL)** – `sql/90_reconciliation_checks.sql` implements 20
   raw-versus-analytics reconciliations, read back by `scripts/run_reconciliation.py` and by
   pytest.

Raw checks cover orphan keys, one payment per order, order subtotal and discount
reconciliation, no orders before signup, no sales before product launch, no future
timestamps, control-arm exposure, campaign attribution inside the window, payment amount and
status consistency, and duplicate customer emails.

Reconciliation checks cover:

* row counts: orders, order lines, customers, products, assignments;
* unique keys: `fct_orders.order_id`, `fct_order_lines.order_item_id`;
* revenue: canonical all-status revenue and recognised revenue against raw;
* rollups: raw lines → raw orders, analytical lines → analytical orders, orders → customer
  mart, lines → product and category marts, daily and monthly marts;
* counts: recognised orders, recognised units, attributed orders.

## Planned test coverage (later milestones)

* Customer analytics: RFM quintile boundaries, tie handling, reproducible segment assignment
  and monotonicity of the score against observed behaviour.
* Cohorts: retention matrix shape, first period = 100%, cohort revenue attribution.
* Statistics: the treatment/control test must recover the manifest's ground truth (detect
  genuine lifts, avoid false positives on placebo campaigns) and produce correct confidence
  intervals, effect sizes and multiple-comparison corrections.
* Visualisation: chart builders return figures with the expected axes, labels and ordering.

