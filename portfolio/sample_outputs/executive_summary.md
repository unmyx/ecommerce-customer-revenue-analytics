# NovaCart - executive summary

_Generated from the canonical analytical layer. Every figure below is produced by `scripts/build_dashboard.py`; none is written by hand._

## 1. Executive KPIs

| Metric | Value |
| --- | --- |
| Analysis window | 2024-10-01 to 2026-09-30 |
| Total net revenue | EUR 14.86m |
| Orders (completed) | 78,896 |
| Units sold | 250,532 |
| Purchasing customers | 7,622 |
| Registered customers | 15,000 |
| Average order value | EUR 188.37 |
| Revenue per purchasing customer | EUR 1,949.82 |
| Revenue per registered customer | EUR 990.77 |
| Repeat customer rate | 56.8% |

## 2. Revenue trend

* Revenue over the last 12 months: **EUR 9.88m**, 98.2% above the preceding 12 months (EUR 4.98m).
* Strongest month: **2025-11** at EUR 1.06m.
* Most recent month (2026-09): EUR 912.17k, -2.8% month over month.

## 3. Customer behaviour

* Champions: 2,201 customers (14.7% of registered customers) generating 84.7% of revenue.
* At Risk: 1,055 customers representing EUR 429.19k of historical revenue.
* Never purchased: 7,378 customers (49.2% of registrations).
* Revenue concentration: the top 10% of purchasing customers hold 53.0% of revenue; the bottom half hold 4.0%.
* Cohort retention: 24 monthly cohorts, median month-1 activity retention 21.2% (excluding the left-censored first cohort, which shows 73.2%).

## 4. Product findings

* Largest category: **Electronics** at EUR 4.54m (30.6% of revenue), followed by Home & Kitchen (22.7%).
* Largest single product: **Marlow Smart Watch Pro** at EUR 228.77k.
* Declining products: 162 of 1,118 comparable products met the decline rule (prior units >= 10 and a unit change of -30% or worse); the steepest is Fable & Fern Dumbbell Set (-48.9%).

## 5. Campaign findings

* 20 campaigns were evaluated with a randomised holdout.
* 8 show a statistically significant lift at a 5% false-discovery rate; 11 also clear the practical thresholds (>= 10% relative and >= EUR 5 absolute per assigned customer).
* 3 campaigns are directionally positive but statistically inconclusive, and 9 show no detectable difference.
* Largest significant effect: **CMP-005 (Black Friday Countdown 2026)** at 51.7% (EUR 110.86 per assigned customer, 95% CI EUR 75.16 to EUR 146.55).

## 6. Data limitations

* All data is **synthetic**; the analysis demonstrates method, not a client result.
* The dataset simulates randomised campaign assignment, while real client data often contains confounding, selection bias, targeting effects and non-random exposure. Campaign effects are therefore not automatically transferable.
* The primary campaign comparison is intention-to-treat and is diluted by treatment-arm members who were never exposed.
* Cohort retention measures any recognised order in a month; the generated data has no churn-decay process, so retention is flatter than a real retail cohort.
* The first cohort (2024-10) is left-censored - it contains customers who were already active before the window - and should be excluded from retention benchmarks.

## 7. Recommended business actions

1. Keep the growth engine running: revenue across the last 12 months was EUR 9.88m, 98.2% higher than the preceding 12 months (EUR 4.98m). Revenue has grown over the comparison period; the 2025-11 peak (EUR 1.06m) confirms the seasonal concentration, so plan inventory, staffing and paid media around it.
2. Protect the 2,201 Champions: they are 14.7% of registered customers but 84.7% of revenue (EUR 12.58m). Any retention or service regression in this group is a direct revenue event, so give them priority support, early access and a named owner of their experience.
3. Win back the 1,055 At Risk customers (EUR 429.19k of historical revenue): they were frequent buyers who have gone quiet, which makes them the highest-probability reactivation target. Measure the win-back campaign against a holdout group, as this analysis does for acquisition campaigns.
4. Scale what is proven and stop paying for noise: 8 of 20 campaigns show a statistically significant lift at a 5% false-discovery rate, led by CMP-005 (51.7% / EUR 110.86 per assigned customer, 95% CI EUR 75.16 to EUR 146.55), while 9 show no detectable difference and can be paused or redesigned. Reallocate that budget to the proven creatives and audiences first.
5. Treat 3 campaigns as undecided rather than successful: their point estimates clear the practical thresholds but their confidence intervals cross zero. Re-run them with a larger holdout or a longer window before committing budget.
6. Defend the product portfolio: Electronics is the largest category at 30.6% of revenue and Marlow Smart Watch Pro is the single largest product (EUR 228.77k). At the same time 162 products met the decline rule, the steepest being Fable & Fern Dumbbell Set (-48.9%); review pricing, stock cover and whether to replace them.
7. Keep the measurement standard: the window contains 15,000 registered customers of whom 7,622 purchased, and 53.0% of revenue comes from the top 10% of buyers. Continue using randomised holdouts and pre-registered tests so campaign decisions stay evidence-based.
