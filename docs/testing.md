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
| Business analytics (unit) | `tests/test_analytics_metrics.py`, `test_analytics_revenue.py`, `test_analytics_trends.py`, `test_analytics_products.py`, `test_analytics_customers.py`, `test_analytics_plots.py` | KPI/AOV/repeat-rate maths, rolling windows, month-over-month change, product and customer aggregation, ranking and declining rules, chart data and labels, empty frames and zero denominators - all on hand-built frames with known answers |
| RFM segmentation (unit) | `tests/test_rfm.py` | quintile scoring with reversed recency, deterministic tie-breaking, every documented segment rule, exhaustive coverage of all 125 score combinations, never-purchased handling, segment totals reconciling to the input |
| Cohort retention (unit) | `tests/test_cohorts.py` | first-purchase cohort assignment, month-0 baseline = 100%, retention never above 100%, unobservable offsets left blank, cumulative revenue, invariant validation rejecting impossible tables, determinism |
| Campaign statistics (unit) | `tests/test_campaign_statistics.py` | hand-computed Welch values, CI consistency with the test, Hedges' g, bootstrap determinism, Benjamini-Hochberg against a known example and NaN/order handling, campaign aggregation, pre-specified practical thresholds, untestable small groups |
| Business analytics (database) | `tests/test_analytics_integration.py` | the Python layer reproduces the SQL marts (category, product, monthly, rolling, campaign means), RFM reconciles to the customer mart, cohort invariants hold on real data, the full run writes 25 tables and 16 figures, and the analysis never reads the generator ground truth |
| Dashboard exports (unit) | `tests/test_dashboard_exports.py` | every export matches its declared schema, row counts match the canonical tables, the two fact exports reconcile with every aggregate (total, month, country, segment, category, product), the published repeat-customer rule is reproducible from the facts, the data dictionary covers all 230 columns, the manifest records rows and checksums, and exports are byte-deterministic |
| Executive summary (unit) | `tests/test_dashboard_summary.py` | all seven required sections, every quoted figure matches the canonical results, recommendations are derived from measured values, limitations include the required caveats, and changing the data changes the prose |
| Page previews (unit) | `tests/test_dashboard_preview.py` | each page renders the expected panels, the four previews are written under deterministic names, and a window without declining products degrades gracefully |
| Presentation layer (database) | `tests/test_dashboard_integration.py` | the exports reconcile with the SQL marts and the Python analytics, the campaign export equals the statistical results table, and the full build writes 18 datasets, 4 previews and the Markdown/HTML/Excel summary |

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

# the analysis and the notebook
python scripts/build_business_analysis.py
python -m nbconvert --to notebook --execute --inplace notebooks/01_business_analysis.ipynb

# the presentation layer
python scripts/build_dashboard.py
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

* Dashboard assets: the Power BI model must expose the same KPI definitions as
  `analytics.kpis` and the executed notebook.
* Executive summary: every headline number in the README must be reproducible from the
  published tables.

