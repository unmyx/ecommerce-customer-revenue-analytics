"""Order and order-item simulation.

The simulation has three layers:

1. A demand calendar that combines growth, yearly seasonality, weekday patterns,
   retail events and smooth day-to-day noise.
2. A per-customer purchase process (negative binomial counts + seasonal date
   sampling) that produces the baseline order stream.
3. Campaign lift: exposed customers in a treatment arm receive extra orders
   inside the campaign window, at the ground-truth lift documented in the
   generation manifest. Control customers receive none, which is what makes the
   later treatment/control comparison meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from novacart.synthetic import reference
from novacart.synthetic.campaigns import CampaignData
from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.customers import AFFINITY_COLUMNS, CATEGORY_ORDER, CustomerData
from novacart.synthetic.products import ProductData
from novacart.synthetic.sampling import (
    ar1_multiplicative_noise,
    cumulative_probabilities,
    day_range,
    draw_index,
    draw_index_with_weights,
)

MAX_ORDERS_PER_CUSTOMER = 150
MAX_ITEMS_PER_ORDER = 15
CAMPAIGN_AOV_ITEM_BONUS = 0.15
ATTRIBUTION_RATE = 0.85

# Purchase frequency is a mixture: most buyers order once or twice, while a
# smaller loyal segment orders repeatedly. A single negative binomial produces a
# repeat rate above 90%, which does not look like real e-commerce behaviour.
# Calibrated so that roughly 60% of registered customers ever buy, ~50% of
# buyers return, and the configured order target is met (see docs/data_generation.md).
CASUAL_ORDER_MEAN = 0.40
LOYAL_ORDER_MEAN = 15.0
LOYAL_PROBABILITY_POWER = 4.0

FREE_SHIPPING_THRESHOLD = 50.0
STANDARD_SHIPPING = 4.95
EXPRESS_SHIPPING = 9.95
EXPRESS_SHARE = 0.12

PROMO_SHARE = 0.32
PROMO_RATES: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20)
PROMO_RATE_WEIGHTS: tuple[float, ...] = (0.35, 0.35, 0.20, 0.10)

# Retail events layered on top of the monthly seasonality.
RETAIL_EVENTS: tuple[tuple[tuple[int, int, int, int], float], ...] = (
    # (month, start_day, end_day, factor)
    ((11, 24, 30, 1), 1.90),  # Black Friday week
    ((12, 1, 10, 1), 1.25),   # Christmas run-up
    ((12, 11, 20, 1), 1.15),
    ((12, 21, 31, 1), 0.75),  # quiet days between Christmas and New Year
    ((1, 1, 10, 1), 1.10),    # January sale
)


@dataclass(frozen=True)
class OrderData:
    orders: pd.DataFrame
    order_items: pd.DataFrame
    diagnostics: dict[str, float]


def build_demand_calendar(
    config: GenerationConfig, rng: np.random.Generator
) -> pd.DataFrame:
    """Daily demand factors covering the analysis window."""
    days = day_range(config.start_date, config.end_date)
    calendar = pd.DataFrame({"date": pd.to_datetime(days)})
    calendar["day_index"] = np.arange(len(calendar))

    years_elapsed = (
        (days - np.datetime64(config.start_date, "D")).astype("timedelta64[D]").astype(float)
        / 365.25
    )
    calendar["trend"] = (1.0 + config.annual_growth_rate) ** years_elapsed
    calendar["month"] = calendar["date"].dt.month
    calendar["seasonality"] = calendar["month"].map(reference.MONTH_DEMAND_FACTORS)
    calendar["weekday"] = calendar["date"].dt.dayofweek
    calendar["weekly"] = calendar["weekday"].map(dict(enumerate(reference.WEEKDAY_FACTORS)))

    event_factor = np.ones(len(calendar))
    day_of_month = calendar["date"].dt.day.to_numpy()
    month_values = calendar["month"].to_numpy()
    for (month, start_day, end_day, _), factor in RETAIL_EVENTS:
        mask = (
            (month_values == month) & (day_of_month >= start_day) & (day_of_month <= end_day)
        )
        event_factor[mask] = np.maximum(event_factor[mask], factor)
    calendar["event"] = event_factor

    calendar["noise"] = ar1_multiplicative_noise(
        rng,
        len(calendar),
        sigma=reference.DAY_LEVEL_NOISE_SIGMA,
        phi=reference.DAY_LEVEL_NOISE_AR,
    )
    calendar["factor"] = (
        calendar["trend"] * calendar["seasonality"] * calendar["weekly"] * calendar["event"]
        * calendar["noise"]
    )
    return calendar


def _month_buckets(order_days: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map day values to a dense month index, returning (bucket_index, month_starts)."""
    month_starts = np.unique(order_days.astype("datetime64[M]"))
    lookup = {value: index for index, value in enumerate(month_starts)}
    bucket = np.array([lookup[value] for value in order_days.astype("datetime64[M]")])
    return bucket, month_starts


def _product_cdfs_by_month(
    config: GenerationConfig,
    products: ProductData,
    month_starts: np.ndarray,
) -> dict[tuple[int, str], tuple[np.ndarray, np.ndarray]]:
    """Per month and category: candidate product positions and their CDF."""
    params = products.params
    category_values = params["category"].to_numpy()
    launch_dates = params["launch_date"].to_numpy()
    popularity = params["popularity"].to_numpy()
    slopes = params["trend_slope"].to_numpy()
    window_start = np.datetime64(config.start_date, "D")
    window_length_days = float(
        (np.datetime64(config.end_date, "D") - window_start) / np.timedelta64(1, "D")
    )

    table: dict[tuple[int, str], tuple[np.ndarray, np.ndarray]] = {}
    for month_index, month_start in enumerate(month_starts):
        elapsed = float((month_start - window_start) / np.timedelta64(1, "D"))
        progress = float(np.clip(elapsed / window_length_days, 0.0, 1.0))
        trend_factor = np.clip(1.0 + slopes * (progress - 0.5), 0.05, 3.0)
        available = launch_dates <= month_start
        for category in CATEGORY_ORDER:
            mask = available & (category_values == category)
            positions = np.flatnonzero(mask)
            if positions.size == 0:
                continue
            month_profile = reference.CATEGORIES[category].month_factors
            month_number = int(pd.Timestamp(month_start).month)
            seasonal = month_profile.get(month_number, 1.0)
            weights = popularity[positions] * trend_factor[positions] * seasonal
            table[(month_index, category)] = (positions, cumulative_probabilities(weights))
    return table


def _draw_baseline_orders(
    config: GenerationConfig,
    rng: np.random.Generator,
    calendar: pd.DataFrame,
    customer_data: CustomerData,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (customer_position, day_index, intensity_by_customer) for baseline orders."""
    latent = customer_data.latent
    days = calendar["date"].to_numpy().astype("datetime64[D]")
    factors = calendar["factor"].to_numpy()

    window_start = np.datetime64(config.start_date, "D")
    signup = np.array([np.datetime64(value, "D") for value in latent["signup_date"]])
    active_start = np.searchsorted(days, np.maximum(signup, window_start), side="left")
    active_start = np.clip(active_start, 0, len(days) - 1)
    active_days = len(days) - active_start

    n = len(latent)
    engagement = latent["engagement"].to_numpy()
    exposure = active_days / len(days)
    loyal_probability = engagement**LOYAL_PROBABILITY_POWER
    is_loyal = rng.random(n) < loyal_probability
    base_intensity = np.where(is_loyal, LOYAL_ORDER_MEAN, CASUAL_ORDER_MEAN) * exposure

    baseline_target = config.target_orders * config.baseline_order_share
    never_purchase = rng.random(n) < config.never_purchase_share
    base_intensity = np.where(never_purchase, 0.0, base_intensity)
    scale = baseline_target / base_intensity.sum()
    intensity = base_intensity * scale

    dispersion = config.order_dispersion
    probability = dispersion / (dispersion + intensity)
    casual_counts = rng.poisson(intensity)
    loyal_counts = rng.negative_binomial(dispersion, probability)
    counts = np.where(is_loyal & ~never_purchase, loyal_counts, casual_counts)
    counts = np.clip(counts, 0, MAX_ORDERS_PER_CUSTOMER)

    customer_positions: list[np.ndarray] = []
    day_positions: list[np.ndarray] = []
    for position in np.flatnonzero(counts > 0):
        start = int(active_start[position])
        local_factors = factors[start:]
        cumulative = cumulative_probabilities(local_factors)
        chosen = draw_index(rng, cumulative, int(counts[position])) + start
        customer_positions.append(np.full(len(chosen), position, dtype=np.int64))
        day_positions.append(chosen)

    if not customer_positions:
        empty = np.empty(0, dtype=np.int64)
        return empty, empty, intensity
    return np.concatenate(customer_positions), np.concatenate(day_positions), intensity


def _draw_campaign_orders(
    config: GenerationConfig,
    rng: np.random.Generator,
    calendar: pd.DataFrame,
    customer_data: CustomerData,
    campaign_data: CampaignData,
    intensity_by_customer: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (customer_position, day_index, campaign_position) for lift-driven orders."""
    customers = customer_data.customers
    days = calendar["date"].to_numpy().astype("datetime64[D]")
    factors = calendar["factor"].to_numpy()
    window_start = np.datetime64(config.start_date, "D")
    prefix_sums = np.concatenate([[0.0], np.cumsum(factors)])

    signup = np.array([np.datetime64(value, "D") for value in customers["signup_date"]])
    active_start = np.clip(np.searchsorted(days, np.maximum(signup, window_start), side="left"), 0, len(days) - 1)

    customer_position = {
        customer_id: position for position, customer_id in enumerate(customers["customer_id"])
    }
    campaign_position = {
        campaign_id: position
        for position, campaign_id in enumerate(campaign_data.campaigns["campaign_id"])
    }
    effects = campaign_data.effects.set_index("campaign_id")

    order_customers: list[np.ndarray] = []
    order_days: list[np.ndarray] = []
    order_campaigns: list[np.ndarray] = []

    assignments = campaign_data.assignments
    exposed = assignments[assignments["exposed"]]
    for campaign_id, rows in exposed.groupby("campaign_id", sort=True):
        campaign_row = campaign_data.campaigns.loc[
            campaign_data.campaigns["campaign_id"] == campaign_id
        ].iloc[0]
        start = np.datetime64(campaign_row["start_date"], "D")
        end = np.datetime64(campaign_row["end_date"], "D")
        lift = float(effects.loc[campaign_id, "true_purchase_lift"])
        if lift <= 0:
            continue

        positions = np.array(
            [customer_position[cid] for cid in rows["customer_id"]], dtype=np.int64
        )
        window_start_index = int(np.searchsorted(days, start, side="left"))
        window_end_index = int(np.searchsorted(days, end, side="right"))
        starts = np.maximum(active_start[positions], window_start_index)
        ends = np.minimum(window_end_index, len(days))
        total_factors = prefix_sums[len(days)] - prefix_sums[active_start[positions]]
        window_factors = np.maximum(prefix_sums[ends] - prefix_sums[starts], 0.0)
        share = np.divide(
            window_factors, total_factors, out=np.zeros_like(window_factors), where=total_factors > 0
        )
        expected_extra = intensity_by_customer[positions] * share * lift
        extra_counts = rng.poisson(expected_extra)
        extra_counts = np.clip(extra_counts, 0, 25)
        if extra_counts.sum() == 0:
            continue

        for p, count in zip(positions, extra_counts, strict=True):
            count = int(count)
            if count <= 0:
                continue
            local_start = max(int(active_start[p]), window_start_index)
            if window_end_index <= local_start:
                continue
            local_factors = factors[local_start:window_end_index]
            chosen = draw_index(rng, cumulative_probabilities(local_factors), count) + local_start
            attributed = rng.random(count) < ATTRIBUTION_RATE
            order_customers.append(np.full(count, p, dtype=np.int64))
            order_days.append(chosen)
            order_campaigns.append(
                np.where(attributed, campaign_position[campaign_id], -1).astype(np.int64)
            )

    if not order_customers:
        empty = np.empty(0, dtype=np.int64)
        return empty, empty, empty
    return (
        np.concatenate(order_customers),
        np.concatenate(order_days),
        np.concatenate(order_campaigns),
    )


def _line_category_index(
    rng: np.random.Generator,
    line_month: np.ndarray,
    line_customer: np.ndarray,
    month_category_weights: np.ndarray,
    affinity: np.ndarray,
) -> np.ndarray:
    weights = month_category_weights[line_month] * affinity[line_customer]
    totals = weights.sum(axis=1, keepdims=True)
    probabilities = np.divide(weights, totals, out=np.zeros_like(weights), where=totals > 0)
    cumulative = np.cumsum(probabilities, axis=1)
    cumulative[:, -1] = 1.0
    uniforms = rng.random(len(probabilities))
    return (cumulative < uniforms[:, None]).sum(axis=1)


def _resolve_duplicate_products(
    rng: np.random.Generator,
    line_order: np.ndarray,
    line_product: np.ndarray,
    line_month: np.ndarray,
    line_category_index: np.ndarray,
    product_cdfs: dict[tuple[int, str], tuple[np.ndarray, np.ndarray]],
) -> np.ndarray:
    """Resample lines that picked a product already present in the same order."""
    product = line_product.copy()
    for _ in range(12):
        used: dict[int, set[int]] = {}
        duplicates: list[int] = []
        for line in range(len(product)):
            order = int(line_order[line])
            product_id = int(product[line])
            seen_products = used.setdefault(order, set())
            if product_id in seen_products:
                duplicates.append(line)
            else:
                seen_products.add(product_id)
        if not duplicates:
            break
        for line in duplicates:
            order = int(line_order[line])
            key = (int(line_month[line]), CATEGORY_ORDER[int(line_category_index[line])])
            if key not in product_cdfs:
                continue
            positions, cdf = product_cdfs[key]
            replacement: int | None = None
            for candidate in positions[draw_index(rng, cdf, 64)]:
                if int(candidate) not in used[order]:
                    replacement = int(candidate)
                    break
            if replacement is None:
                for candidate in positions:
                    if int(candidate) not in used[order]:
                        replacement = int(candidate)
                        break
            if replacement is None:
                continue
            product[line] = replacement
            used[order].add(replacement)
    return product


def generate_orders(
    config: GenerationConfig,
    rng: np.random.Generator,
    customer_data: CustomerData,
    product_data: ProductData,
    campaign_data: CampaignData,
) -> OrderData:
    calendar = build_demand_calendar(config, rng)
    days = calendar["date"].to_numpy().astype("datetime64[D]")
    customers = customer_data.customers
    latent = customer_data.latent

    customer_orders, order_day, intensity_by_customer = _draw_baseline_orders(
        config, rng, calendar, customer_data
    )

    campaign_customers, campaign_days, campaign_ids = _draw_campaign_orders(
        config, rng, calendar, customer_data, campaign_data, intensity_by_customer
    )

    all_customers = np.concatenate([customer_orders, campaign_customers])
    all_day_index = np.concatenate([order_day, campaign_days])
    all_campaigns = np.concatenate(
        [np.full(len(customer_orders), -1, dtype=np.int64), campaign_ids]
    )
    all_treatment = np.concatenate(
        [np.zeros(len(customer_orders), dtype=bool), np.ones(len(campaign_customers), dtype=bool)]
    )

    # Randomise timestamps inside the day, then order by time to assign order ids.
    hours = draw_index_with_weights(rng, reference.HOUR_OF_DAY_WEIGHTS, len(all_day_index))
    minutes = rng.integers(0, 60, size=len(all_day_index))
    seconds = rng.integers(0, 60, size=len(all_day_index))
    timestamps = (
        pd.to_datetime(days[all_day_index].astype("datetime64[ns]"))
        + pd.to_timedelta(hours, unit="h")
        + pd.to_timedelta(minutes, unit="m")
        + pd.to_timedelta(seconds, unit="s")
    )
    sort_order = np.argsort(timestamps.to_numpy(), kind="stable")
    all_customers = all_customers[sort_order]
    all_day_index = all_day_index[sort_order]
    all_dates = days[all_day_index]
    all_campaigns = all_campaigns[sort_order]
    all_treatment = all_treatment[sort_order]
    order_ts = pd.Series(timestamps.to_numpy()).iloc[sort_order].reset_index(drop=True)

    n_orders = len(all_customers)
    order_ids = np.array([f"ORD-{i:07d}" for i in range(1, n_orders + 1)])

    customer_ids = customers["customer_id"].to_numpy()[all_customers]
    countries = customers["country_code"].to_numpy()[all_customers]
    vat_rates = np.array([reference.COUNTRIES[code].vat_rate for code in countries])

    statuses = np.array(list(reference.ORDER_STATUS_WEIGHTS), dtype=object)[
        draw_index_with_weights(
            rng, list(reference.ORDER_STATUS_WEIGHTS.values()), n_orders
        )
    ]
    sales_channels = np.array(list(reference.SALES_CHANNELS), dtype=object)[
        draw_index_with_weights(rng, list(reference.SALES_CHANNELS.values()), n_orders)
    ]
    campaign_ids_by_order = campaign_data.campaigns["campaign_id"].to_numpy()

    # ------------------------------------------------------------------
    # order items
    # ------------------------------------------------------------------
    order_months, month_starts = _month_buckets(all_dates)
    product_cdfs = _product_cdfs_by_month(config, product_data, month_starts)

    base_items = rng.poisson(config.average_items_per_order, size=n_orders)
    treatment_bonus = 1.0 + CAMPAIGN_AOV_ITEM_BONUS * all_treatment
    item_counts = np.clip(
        np.maximum(1, (base_items * treatment_bonus).round().astype(int)), 1, MAX_ITEMS_PER_ORDER
    )
    n_lines = int(item_counts.sum())

    line_order = np.repeat(np.arange(n_orders), item_counts)
    line_month = order_months[line_order]
    line_customer = all_customers[line_order]
    month_category_weights = np.zeros((len(month_starts), len(CATEGORY_ORDER)))
    for month_index, month_start in enumerate(month_starts):
        month_number = int(pd.Timestamp(month_start).month)
        for index, category in enumerate(CATEGORY_ORDER):
            if (month_index, category) not in product_cdfs:
                continue
            profile = reference.CATEGORIES[category]
            month_category_weights[month_index, index] = (
                profile.weight * profile.month_factors.get(month_number, 1.0)
            )
        if month_category_weights[month_index].sum() <= 0:
            raise RuntimeError(
                f"No purchasable products available for month starting {month_start}"
            )

    affinity = latent[list(AFFINITY_COLUMNS)].to_numpy()
    line_category_index = _line_category_index(
        rng, line_month, line_customer, month_category_weights, affinity
    )

    line_product_position = np.zeros(n_lines, dtype=np.int64)
    for month_index in range(len(month_starts)):
        month_mask = line_month == month_index
        if not month_mask.any():
            continue
        for category_index, category in enumerate(CATEGORY_ORDER):
            mask = month_mask & (line_category_index == category_index)
            count = int(mask.sum())
            if count == 0:
                continue
            key = (month_index, category)
            if key not in product_cdfs:
                raise RuntimeError(
                    f"Category {category} has no purchasable product in month {month_index}"
                )
            positions, cdf = product_cdfs[key]
            line_product_position[mask] = positions[
                draw_index(rng, cdf, count)
            ]

    line_product_position = _resolve_duplicate_products(
        rng, line_order, line_product_position, line_month, line_category_index, product_cdfs
    )

    params = product_data.params
    product_price = params["unit_price"].to_numpy()
    product_cost = params["unit_cost"].to_numpy()

    window_start = np.datetime64(config.start_date, "D")
    years_elapsed = (
        (all_dates - window_start).astype("timedelta64[D]").astype(float) / 365.25
    )
    inflation = (1.0 + config.annual_price_inflation) ** years_elapsed[line_order]

    price_noise = rng.lognormal(mean=0.0, sigma=0.02, size=n_lines)
    promo_draw = rng.random(n_orders)
    promo_rate = np.where(
        promo_draw < PROMO_SHARE,
        np.array(PROMO_RATES)[
            draw_index_with_weights(rng, PROMO_RATE_WEIGHTS, n_orders)
        ],
        0.0,
    )[line_order]

    gross_unit_price = product_price[line_product_position] * inflation * price_noise
    unit_price = np.round(gross_unit_price * (1.0 - promo_rate), 2)
    unit_price = np.maximum(unit_price, 0.99)
    unit_cost = np.round(
        product_cost[line_product_position] * inflation * rng.lognormal(0.0, 0.02, n_lines), 2
    )
    unit_cost = np.minimum(unit_cost, np.round(unit_price * 0.95, 2))

    base_quantity = draw_index_with_weights(rng, (0.78, 0.16, 0.05, 0.01), n_lines)
    quantity = base_quantity + 1
    line_discount = np.round(quantity * unit_price * promo_rate, 2)

    items = pd.DataFrame(
        {
            "order_item_id": [f"OIT-{i:08d}" for i in range(1, n_lines + 1)],
            "order_id": order_ids[line_order],
            "product_id": params["product_id"].to_numpy()[line_product_position],
            "quantity": quantity.astype(int),
            "unit_price": unit_price,
            "unit_cost": unit_cost,
            "line_discount": line_discount,
        }
    )

    items_subtotal = (
        items.assign(gross=items["quantity"] * items["unit_price"])
        .groupby("order_id", sort=False)["gross"]
        .sum()
        .reindex(order_ids)
        .fillna(0.0)
        .round(2)
        .to_numpy()
    )
    discount_amount = (
        items.groupby("order_id", sort=False)["line_discount"]
        .sum()
        .reindex(order_ids)
        .fillna(0.0)
        .round(2)
        .to_numpy()
    )

    goods_value = items_subtotal - discount_amount
    is_express = rng.random(n_orders) < EXPRESS_SHARE
    shipping = np.where(goods_value >= FREE_SHIPPING_THRESHOLD, 0.0, STANDARD_SHIPPING)
    shipping = np.where(is_express, shipping + EXPRESS_SHIPPING, shipping)
    tax = np.round((goods_value + shipping) * vat_rates, 2)

    orders = pd.DataFrame(
        {
            "order_id": order_ids,
            "customer_id": customer_ids,
            "order_ts": order_ts,
            "order_status": statuses.astype(str),
            "sales_channel": sales_channels.astype(str),
            "campaign_id": np.where(
                all_campaigns >= 0, campaign_ids_by_order[np.maximum(all_campaigns, 0)], None
            ),
            "items_subtotal": np.round(items_subtotal, 2),
            "discount_amount": discount_amount,
            "shipping_amount": np.round(shipping, 2),
            "tax_amount": tax,
            "currency_code": "EUR",
            "shipping_country_code": countries,
        }
    )

    campaign_order_share = float((all_campaigns >= 0).mean()) if n_orders else 0.0
    diagnostics = {
        "orders": float(n_orders),
        "order_items": float(n_lines),
        "average_items_per_order": float(n_lines / n_orders) if n_orders else 0.0,
        "attributed_order_share": campaign_order_share,
        "net_revenue_total": float((items_subtotal - discount_amount).sum()),
        "average_order_value": float((items_subtotal - discount_amount).mean()) if n_orders else 0.0,
    }

    return OrderData(orders=orders, order_items=items, diagnostics=diagnostics)

