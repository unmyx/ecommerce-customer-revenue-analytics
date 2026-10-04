# Synthetic data design

## Positioning

The dataset is **synthetic**. It is generated from explicit statistical assumptions, not
sampled from, or derived from, any real company. Everything below is a design decision that
can be inspected, changed and re-verified — which is the point of the project.

The generator has three objectives:

1. produce a dataset large enough for meaningful analysis (15,000 customers, 84,000+ orders,
   207,000+ order lines, 20 campaigns);
2. embed realistic *relationships* — customer loyalty, seasonality, price/cost structure,
   campaign lift, retention decay — rather than independent random columns;
3. embed a known **analytical ground truth** so that later milestones can verify that the
   analysis recovers the effects that were designed in.

## Determinism

* A single `seed` (default `20261004`, overridable with `NOVACART_SEED` or `--seed`) is the
  root of every random draw.
* `numpy.random.SeedSequence(seed).spawn(5)` creates independent streams for customers,
  products, campaigns, orders and payments. Changing one stage does not silently reshuffle
  the others.
* `GenerationConfig` fully determines the dataset: same config + same code = byte-identical
  CSVs. `data/generation_metadata/generation_manifest.json` records the seed, the resolved
  configuration, row counts, SHA-256 checksums of every file, the validation report, library
  versions, and the campaign ground truth.
* Nothing is sampled from the wall clock. `generated_at_utc` in the manifest is the only
  non-deterministic field, and it is metadata rather than data.

## Analysis window

| Setting | Default | Meaning |
| --- | --- | --- |
| `start_date` | 2024-10-01 | first order timestamp |
| `end_date` | 2026-09-30 | last order timestamp (24 complete months) |
| `first_signup_date` | 2023-01-01 | earliest customer registration; ~39% of customers pre-date the window |

Orders only exist inside the window, so every customer's *first observed purchase* falls
inside it and each of the 24 months forms a usable acquisition cohort.

## Customers

Demographics: 15 countries (Germany-weighted EU mix, each with a real VAT rate used for
order tax), a name pool of 60 first and 60 last names, and a city consistent with the country.
Emails are unique by construction and use the reserved `example`-style domain
`mail.novacart.example`.

Channel mix (weight → loyalty bias): organic search 22% (×1.15), paid search 18% (×0.95),
paid social 17% (×0.90), email 12% (×1.20), referral 11% (×1.35), direct 12% (×1.05),
affiliate 5% (×0.85), display 3% (×0.80).

Each customer also carries **latent parameters** that never reach the database:

| Latent | Distribution | Drives |
| --- | --- | --- |
| `engagement` | rank-normalised Beta(2, 3.5) × channel bias | probability of being in the loyal segment |
| `churn_hazard` | Beta(2, 5) scaled by engagement | reactivation campaigns, inactive analysis |
| `promo_affinity` | Beta(2, 2.2) | reserved for promotion response analysis |
| `affinity_<category>` | Dirichlet(9 × category weights) | which categories a customer actually buys |

Signup dates follow a growth-weighted, seasonally shaped intensity (≈14–18% more new
customers each year, more signups in November/December).

## Demand calendar

Daily demand is the product of five multiplicative components:

```
factor(day) = trend × month_seasonality × weekday × retail_event × AR(1) noise
```

* **Trend**: 22% growth per year, compounding across the window.
* **Month seasonality**: January 0.86 → November 1.42, December 1.30, summer dip in July (0.93).
* **Weekday**: Friday 1.06 highest, Sunday 0.93 lowest.
* **Retail events**: Black Friday week ×1.90, 1–10 December ×1.25, 11–20 December ×1.15,
  21–31 December ×0.75, first ten days of January ×1.10.
* **Noise**: lognormal AR(1) shocks (σ = 0.07, φ = 0.55) so day-to-day movement is smooth
  rather than white noise.

## Purchase behaviour

Order counts use a **two-component mixture**, because a single distribution either produces
an unrealistically high repeat rate or cannot reach the required order volume:

| Segment | Share of customers | Order process | Mean orders (scaled) |
| --- | --- | --- | --- |
| Casual | `P(engagement^4)` complement (~80%) | Poisson | ≈ 0.8 |
| Loyal | engagement^4 (~20%) | Negative binomial (dispersion 3) | ≈ 28 |

Intensity is also scaled by each customer's active exposure (a customer who signs up in the
middle of the window cannot order before that), then rescaled so the total equals the
configured baseline target. 9% of customers are drawn as never-purchasers, which is what makes
the inactive-customer and reactivation analyses realistic.

Order timestamps are sampled from the demand calendar restricted to each customer's active
window, then given a time of day from an hourly profile that peaks at 10:00 and 19:00–21:00.

## Basket and pricing

* Items per order: Poisson(2.35), at least 1, capped at 15; campaign-exposed orders get a 15%
  basket bonus (the AOV effect).
* Category choice: category weight × month factor × the customer's category affinity.
* Product choice: within the chosen category, weighted by a Pareto popularity distribution
  (a small number of bestsellers carry much of the volume) multiplied by a product trend
  factor. Roughly 12% of products have a declining trend and 13% a growing trend, which is
  what the "declining products" analysis is designed to find.
* Prices: per-category lognormal medians, snapped to retail endings (…9.99 / …4.99 / …9.99).
  Historical line prices apply 3% annual inflation and 2% lognormal noise on top of the list
  price, so `products.unit_price` never perfectly matches `order_items.unit_price`.
* Promotions: 32% of orders carry a line discount of 5%, 10%, 15% or 20%.
* Margins: per-category gross margins from 28% (Electronics) to 62% (Beauty), with noise; cost
  is always below price.
* Shipping: free above €50 of goods value, otherwise €4.95, with 12% express orders adding
  €9.95. Tax uses the shipping country's VAT rate on goods plus shipping.
* Cart composition: a product appears at most once per order; duplicates are resolved during
  generation, and the rule is enforced by a unique constraint in the database.

## Campaign design and ground truth

20 campaigns run inside the window (email, paid search, paid social, display, influencer,
affiliate) across five objectives. Each campaign targets an audience defined by latent
propensity or signup recency, samples 800–7,000 eligible customers, and randomises them into a
**72% treatment / 28% control** holdout. 93% of treatment customers are actually exposed;
control customers never are.

True effects are assigned before any order is simulated:

| Campaign type | Purchase lift (orders per customer) | AOV lift |
| --- | --- | --- |
| Placebo (`zero_lift_campaign_share = 0.30`) | 0% | 0% |
| Standard | +30% to +65% | +4% to +14% |
| Brand objective | 35% of the standard lift | 0% |

In the default run 8 of 11 genuinely-lifted campaigns and 1 of 9 placebo campaigns were
detectable at the 5% level with a simple two-sample t-test on orders per customer — a realistic
outcome that leaves the later statistics milestone with something honest to work on
(multiple-comparison correction, power, revenue-based effect sizes).

## Calibration of the default run

| Metric | Measured |
| --- | --- |
| Orders / order lines / payments | 84,263 / 207,374 / 84,263 |
| Customers who purchase at least once | 7,822 of 15,000 (52%) |
| Repeat purchase rate (among purchasers) | 57% |
| Average order value | €188 |
| Net revenue | €15.9m over 24 months |
| Items per order | 2.46 |
| Campaign-attributed share of orders | 4.1% |
| Revenue mix | Electronics 31%, Home & Kitchen 23%, Fashion 20%, Sports 15% |

The repeat rate is higher than a typical single-brand D2C benchmark because a deliberate loyal
core places a large share of the orders — the arithmetically necessary consequence of
84,000 orders spread over 15,000 registered customers. That trade-off is documented rather
than hidden.

## Assumptions and limitations

* One payment per order; no partial payments, chargebacks or instalment schedules.
* Refunds are order-level. Item-level returns and return reasons are out of scope.
* No price history table: product list prices are a single snapshot, while order lines carry
  historical prices.
* Geography affects tax and shipping country, not pricing or currency (everything is EUR).
* Campaign assignment is randomised — a designed experiment. Real campaigns are often
  confounded, which the statistics milestone must discuss as a limitation.
* The latent parameters create correlation between behaviour and acquisition channel
  *by design*; they are generation inputs, not observable customer attributes.

## Changing the configuration

```bash
# smaller, faster dataset with identical structure
python scripts/generate_data.py --customers 2000 --products 300 --campaigns 8 --orders 9000

# a different but still reproducible universe
python scripts/generate_data.py --seed 7
```

`GenerationConfig` validates its inputs (dates ordered, shares in range, plausible order
target) and raises a descriptive error instead of producing a degenerate dataset.

