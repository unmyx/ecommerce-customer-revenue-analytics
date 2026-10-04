# Analytical methods

This document records **how every analytical number in the project is produced**: the metric
definitions, the segmentation and cohort rules, the campaign attribution design, the
statistical test and the multiple-testing correction. It is the reference for anyone reviewing
the notebook results or rebuilding the analysis.

All results come from the PostgreSQL analytical layer built in Milestone 2 (see
[data_model.md](data_model.md)). No result is hard-coded, and the generator's ground truth is
never read by the analysis code (enforced by a test).

---

## 1. KPI definitions

| Metric | Definition |
| --- | --- |
| Revenue | Recognised net merchandise revenue: `items_subtotal - discount_amount` on orders with status `completed`. Refunds and cancellations are excluded; shipping and VAT are excluded |
| Total orders | Count of revenue-recognised orders |
| Units | Units on revenue-recognised order lines |
| Unique customers | Customers with at least one recognised order |
| Average order value (AOV) | revenue / recognised orders |
| Average units per order | units / recognised orders |
| Repeat customer | A customer with **two or more** recognised orders |
| Repeat customer rate | repeat customers / purchasing customers |
| Revenue per customer | revenue / **purchasing** customers. `revenue_per_registered_customer` (all registered customers, including non-purchasers) is reported separately rather than blended |
| Rolling revenue | Trailing sum including the current period over a **complete daily calendar**: `revenue_rolling_7d`, `revenue_rolling_30d` (also produced for order counts) |
| Month-over-month change | Absolute difference and percentage change versus the immediately preceding calendar month on a gap-free monthly calendar. A zero or missing base month reports `n/a` (NaN), never an infinite growth rate |
| Declining product | Prior-window recognised units >= 10 **and** unit change <= -30% between two adjacent 90-day windows ending on the last order date in the data |

**Calendar rule.** Daily, weekly and monthly series are reindexed onto complete calendars bounded
by the loaded order period, so a period with no recognised revenue appears as zero instead of
disappearing. Rolling windows and month-over-month comparisons both depend on this.

---

## 2. RFM methodology

**Inputs** (`analytics.mart_customer_features`):

* recency - `days_since_last_order`, measured against the **fixed analysis end date**
  (`analysis_window.analysis_end_date`, 2026-09-30 in the default dataset), never the wall clock;
* frequency - `total_orders`, recognised orders only;
* monetary - `total_revenue`, recognised net revenue.

**Scoring.** Each metric is split into five equal-count bands (quintiles) over purchasing
customers. Recency is inverted - the most recent fifth scores 5, the least recent scores 1.
Frequency and monetary value score 5 for the highest fifth. Bands are computed from ranks
assigned in `customer_id` order, which makes ties deterministic: the same input always produces
the same scores.

**Segment rules.** Segments are assigned by the first matching rule, so the classification is
exhaustive and reproducible:

| Priority | Segment | Rule |
| ---: | --- | --- |
| 1 | Champions | R >= 4 and F >= 4 and M >= 4 |
| 2 | Loyal Customers | R >= 3 and F >= 3 |
| 3 | Potential Loyalists | R >= 4 and F >= 2 |
| 4 | New Customers | R >= 4 and F == 1 |
| 5 | At Risk | R <= 2 and F >= 3 |
| 6 | Dormant | R <= 2 |
| 7 | Needs Attention | any remaining purchasing customer |
| - | Never Purchased | no recognised orders; kept with NULL scores |

The residual "Needs Attention" group exists so that every score combination is covered; without
it, a customer with moderate recency and low frequency would be mislabelled as dormant.

**Outputs.** `rfm_customers` (one row per customer with scores, cell and segment),
`rfm_segments` (customers, revenue, revenue share, average customer revenue, average orders,
AOV, recency, repeat rate) and `rfm_segment_scores` (average R/F/M per segment).

**Limitations.** RFM is descriptive and window-relative; scores are not comparable across
different windows, the quintile boundaries are statistical rather than business-defined, and a
customer can change segment purely because the customer base shifted.

---

## 3. Cohort methodology

**Cohort definition.** A customer's cohort is the calendar month of their **first recognised
order** (`min(order_month)`).

**Month offsets.** `month_offset = (year difference * 12) + month difference` between the cohort
month and the activity month. Offset 0 is the acquisition month by construction, so month-0
retention is 100% of the cohort.

**Retention.** A customer is retained in offset *k* when they place at least one recognised order
in that month. Retention rate = retained customers / cohort size, so it can never exceed 100%.

**Observability.** The analysis end date is fixed (`2026-09-30`, the last order date of the
loaded window). Offsets beyond that date are not observable and are left blank in the retention
matrix rather than reported as zero retention. Later cohorts therefore have fewer columns.

**Outputs.** `cohort_sizes` (cohort size, months observed, revenue, revenue per customer, repeat
rate), `cohort_retention` (long format), `cohort_retention_matrix` (wide, heatmap-ready) and
`cohort_revenue` (revenue and cumulative revenue by offset, per cohort customer).

**Invariants (tested).** month 0 equals the cohort baseline; retention never exceeds 100%; cohort
size is constant within a cohort; cohort indexing is deterministic and ascending; the cohort
sizes sum to the number of purchasing customers; cohort revenue sums to recognised revenue.

---

## 4. Campaign attribution and comparison

**Design.** Each campaign randomised its audience into a treatment arm and a holdout (control)
arm (72/28 in the generated data), and exposure was assigned before any outcome was observed.
Order-level attribution is recorded only for **exposed treatment** customers and only for orders
**inside the campaign window**; the control arm is never attributed.

**Unit of analysis.** One row per **assigned customer** per campaign
(`analytics.mart_campaign_customer_outcomes`). The outcome is recognised net revenue inside the
campaign window. Orders are not treated as independent observations, because a customer can
place several orders in the window.

**Primary comparison (intention-to-treat).** Everyone randomised to treatment versus everyone
randomised to the holdout, whether or not they were exposed. This preserves the randomisation and
is the defensible primary estimate. Exposure-only comparisons are available in the mart for
diagnostics but are not the headline, because selecting on exposure breaks the randomisation.

**Windows.** descriptive outcomes are reported for the 90 days before the campaign, the campaign
window itself, and the 30 days after it. The statistical test uses the campaign window only.

**Ground truth.** The generator knows the true lift designed into each campaign. It lives in
`data/generation_metadata/generation_manifest.json`, is never loaded into PostgreSQL, and is never
read by `novacart/analytics`. A test asserts that no analytics module references it; the single
post-hoc validation cell in `notebooks/04_campaign_analysis.ipynb` is clearly marked and does not
feed any result.

---

## 5. Statistical test selection

| Choice | Method | Rationale |
| --- | --- | --- |
| Primary test | **Welch's two-sample t-test** on customer-level revenue | Two independent groups with unequal sizes and variances. Welch does not assume equal variance, unlike Student's t-test, and the central limit theorem makes the test on means reliable at these sample sizes even with skewed revenue |
| Interval | **95% confidence interval** for the difference in means using the Welch-Satterthwaite degrees of freedom | Standard companion to the test; directly readable as the range of plausible lifts per assigned customer |
| Robustness | **Percentile bootstrap** interval and **Mann-Whitney U** p-value | Revenue is heavy-tailed (top 10% of customers hold ~53% of revenue). Both checks confirm the conclusion is not an artefact of skew or a few large customers |
| Effect size | **Hedges' g** (bias-corrected Cohen's d) | Standardised magnitude that is comparable across campaigns with different revenue levels |

Alternatives considered and rejected: a per-order t-test (orders within a customer are not
independent, which inflates the sample size and understates uncertainty); a chi-square test on
customer counts (it answers "did they buy at all", not "how much value did the campaign create");
and a Mann-Whitney test as the primary (it tests distribution shift rather than the mean revenue
that the business decision depends on).

**Pre-specification.** The test, the confidence level, the effect size, the correction method and
the practical thresholds were all fixed in code before the results were inspected. Nothing was
changed after seeing the output.

---

## 6. Multiple-testing correction

Twenty campaigns are tested simultaneously, so raw p-values would produce roughly one false
positive by chance alone. The analysis applies the **Benjamini-Hochberg procedure** to control the
**false discovery rate at q = 0.05**: among campaigns flagged as significant, at most about 5%
are expected to be false discoveries.

Benjamini-Hochberg was chosen over Bonferroni because the campaign set is exploratory and the
goal is to limit false discoveries without discarding real effects. Adjusted p-values are reported
alongside raw p-values; the significance flags use the adjusted values. Campaigns that cannot be
tested (a group with fewer than two customers, or zero variance) keep a NaN adjusted p-value and
are excluded from the correction, which is stated in the results table.

**Effect size interpretation** follows the conventional Hedges' g / Cohen's d bands: |g| < 0.2
negligible, < 0.5 small, < 0.8 medium, otherwise large.

---

## 7. Statistical versus practical significance

Two separate flags are published:

* **statistically_significant** - FDR-adjusted p-value < 0.05;
* **practically_significant** - relative lift >= 10% **and** absolute lift >= EUR 5.00 per
  assigned customer (fixed before the analysis).

A difference can be statistically significant and still not worth acting on when the sample is
large and the effect is tiny; conversely, a large point estimate with a wide interval is not a
reason to act either. The `business_interpretation` column states which case each campaign is in.

---

## 8. Known limitations

* **Randomisation is simulated.** The dataset simulates randomised campaign assignment, while
  real client data often contains confounding, selection bias, targeting effects and non-random
  exposure. Effect estimates from this project are therefore not automatically transferable to
  real campaign evaluations.
* **Intention-to-treat dilution.** The primary estimate includes treatment-arm customers who were
  never exposed, so it understates the effect on the exposed population by design.
* **Heavy-tailed revenue.** Means are sensitive to large customers; the bootstrap and rank-based
  checks mitigate but do not remove this.
* **Fixed-window outcomes.** Campaign outcomes are measured inside the campaign window plus a
  30-day tail; longer-term effects are out of scope.
* **Descriptive segmentation and cohorts.** RFM and cohort analysis describe what happened; they
  do not identify why customers returned or lapsed.
* **The first cohort is left-censored and should not be used as a benchmark.** Customers who
  were already active before the loaded window have their first *observed* order in 2024-10, so
  that cohort mixes genuine new customers with pre-existing loyal customers. It shows month-1
  retention of ~73% against ~20% for every other cohort. Cohorts from 2024-11 onwards are clean
  acquisition cohorts; only they should be compared.
* **Flat retention is a property of the data design.** The generator gives each customer a
  constant order intensity rather than an explicit churn-decay process, so monthly activity
  retention for the clean cohorts is roughly flat (median month 1 ~21%, month 6 ~23%) instead of
  declining the way a typical retail cohort does. The cohort method is correct; a production
  dataset would show decay, and later cohorts also inherit a selection effect because only their
  early months are observable.
* **Synthetic data.** Every customer, order and campaign is generated; the analysis demonstrates
  method, not a real business result.

---

## 9. Reproducibility

| Area | Module | Key tests |
| --- | --- | --- |
| KPIs, revenue, trends, products, customers | `analytics/{kpis,revenue,trends,products,customers}.py` | `test_analytics_metrics.py`, `test_analytics_revenue.py`, `test_analytics_trends.py`, `test_analytics_products.py`, `test_analytics_customers.py` |
| RFM | `analytics/rfm.py` | `test_rfm.py` |
| Cohorts | `analytics/cohorts.py` | `test_cohorts.py` |
| Campaigns and statistics | `analytics/{campaigns,statistics}.py` | `test_campaign_statistics.py` |
| Charts | `analytics/plots.py` | `test_analytics_plots.py` |
| End-to-end on the database | `analytics/report.py` | `test_analytics_integration.py` |

Rebuild everything with:

```bash
python scripts/build_business_analysis.py
python -m nbconvert --to notebook --execute --inplace notebooks/0*.ipynb
```

