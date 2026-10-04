"""Product catalogue generation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from novacart.synthetic import reference
from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.sampling import day_range, draw_index_with_weights

IN_WINDOW_LAUNCH_SHARE = 0.15
EARLIEST_LAUNCH_DATE = np.datetime64("2019-01-01", "D")
PRODUCT_VARIANTS: tuple[str, ...] = (
    "Classic", "Pro", "Compact", "Premium", "Essential", "Plus", "Mini", "Studio",
)

CATEGORY_PREFIXES: dict[str, str] = {
    "Electronics": "ELEC",
    "Home & Kitchen": "HOME",
    "Sports & Outdoors": "SPRT",
    "Beauty & Personal Care": "BEAU",
    "Fashion": "FASH",
    "Toys & Games": "TOYS",
    "Books & Media": "BOOK",
    "Grocery": "GROC",
}


@dataclass(frozen=True)
class ProductData:
    """Public catalogue plus the hidden popularity/trend parameters."""

    products: pd.DataFrame
    params: pd.DataFrame


def _snap_price(value: float) -> float:
    """Retail-style price endings (9.99 / x4.99 / x9.99)."""
    value = max(value, 3.5)
    if value < 40:
        return round(float(np.floor(value)) + 0.99, 2)
    if value < 200:
        return round(float(np.floor(value / 5) * 5) + 4.99, 2)
    return round(float(np.floor(value / 10) * 10) + 9.99, 2)


def _trend_slopes(rng: np.random.Generator, n: int) -> np.ndarray:
    """~12% declining, ~13% growing, the rest roughly flat over the window."""
    slopes = np.zeros(n)
    draw = rng.random(n)
    declining = draw < 0.12
    growing = (draw >= 0.12) & (draw < 0.25)
    slopes[declining] = rng.uniform(-0.55, -0.12, size=int(declining.sum()))
    slopes[growing] = rng.uniform(0.12, 0.60, size=int(growing.sum()))
    slopes[~(declining | growing)] = rng.uniform(-0.06, 0.06, size=int((~(declining | growing)).sum()))
    return slopes


def generate_products(config: GenerationConfig, rng: np.random.Generator) -> ProductData:
    n = config.n_products

    category_names = list(reference.CATEGORIES)
    category_index = draw_index_with_weights(
        rng, [c.weight for c in reference.CATEGORIES.values()], n
    )

    subcategories = np.empty(n, dtype=object)
    nouns = np.empty(n, dtype=object)
    brands = np.empty(n, dtype=object)
    price_median = np.empty(n)
    price_sigma = np.empty(n)
    gross_margin = np.empty(n)
    popularity_decay = np.empty(n)

    for index, name in enumerate(category_names):
        mask = category_index == index
        count = int(mask.sum())
        if count == 0:
            continue
        profile = reference.CATEGORIES[name]
        subcategories[mask] = np.array(profile.subcategories, dtype=object)[
            rng.integers(0, len(profile.subcategories), size=count)
        ]
        nouns[mask] = np.array(profile.product_nouns, dtype=object)[
            rng.integers(0, len(profile.product_nouns), size=count)
        ]
        brands[mask] = np.array(reference.BRANDS, dtype=object)[
            rng.integers(0, len(reference.BRANDS), size=count)
        ]
        price_median[mask] = profile.price_median
        price_sigma[mask] = profile.price_sigma
        gross_margin[mask] = profile.gross_margin
        popularity_decay[mask] = profile.popularity_decay

    raw_price = price_median * rng.lognormal(mean=0.0, sigma=price_sigma)
    unit_price = np.array([_snap_price(value) for value in raw_price])
    margin_noise = rng.lognormal(mean=0.0, sigma=0.07, size=n)
    effective_margin = np.clip(gross_margin * margin_noise, 0.08, 0.80)
    unit_cost = np.round(unit_price * (1.0 - effective_margin), 2)

    window_days = day_range(config.start_date, config.end_date)
    pre_window_days = day_range(EARLIEST_LAUNCH_DATE.astype(object), config.start_date)
    in_window = rng.random(n) < IN_WINDOW_LAUNCH_SHARE
    launch_index = np.where(
        in_window,
        rng.integers(0, len(window_days), size=n),
        rng.integers(0, len(pre_window_days), size=n),
    )
    launch_dates = np.where(
        in_window,
        window_days[np.clip(launch_index, 0, len(window_days) - 1)],
        pre_window_days[np.clip(launch_index, 0, len(pre_window_days) - 1)],
    )

    trend_slope = _trend_slopes(rng, n)
    active_probability = np.where(trend_slope < 0, 0.76, 0.93)
    is_active = rng.random(n) < active_probability

    # Heavy-tailed long-tail demand: a small share of products carries most volume.
    popularity = (rng.pareto(a=1.6, size=n) + 1.0) ** (1.0 / popularity_decay)

    product_ids = np.array([f"PRD-{i:05d}" for i in range(1, n + 1)])
    prefixes = np.array([CATEGORY_PREFIXES[name] for name in np.array(category_names)[category_index]])
    skus = np.array(
        [f"NC-{prefix}-{i:05d}" for i, prefix in enumerate(prefixes, start=1)]
    )
    variant = np.where(
        rng.random(n) < 0.45,
        "",
        np.array(PRODUCT_VARIANTS, dtype=object)[rng.integers(0, len(PRODUCT_VARIANTS), size=n)],
    )
    product_names = np.array(
        [
            " ".join(part for part in (brand, noun, extra) if part)
            for brand, noun, extra in zip(brands, nouns, variant, strict=True)
        ]
    )

    products = pd.DataFrame(
        {
            "product_id": product_ids,
            "sku": skus,
            "product_name": product_names,
            "category": np.array(category_names, dtype=object)[category_index],
            "subcategory": subcategories.astype(str),
            "brand": brands.astype(str),
            "unit_price": unit_price,
            "unit_cost": unit_cost,
            "launch_date": launch_dates.astype("datetime64[D]").astype(object),
            "is_active": is_active,
        }
    ).sort_values("product_id", kind="stable").reset_index(drop=True)

    params = pd.DataFrame(
        {
            "product_id": product_ids,
            "category": np.array(category_names, dtype=object)[category_index],
            "popularity": popularity,
            "trend_slope": trend_slope,
            "launch_date": launch_dates,
            "is_active": is_active,
            "unit_price": unit_price,
            "unit_cost": unit_cost,
        }
    ).sort_values("product_id", kind="stable").reset_index(drop=True)

    return ProductData(products=products, params=params)

