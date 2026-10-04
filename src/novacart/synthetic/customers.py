"""Customer generation: demographics plus hidden behavioural parameters."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from novacart.synthetic import reference
from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.sampling import ar1_multiplicative_noise, day_range, draw_index_with_weights

CATEGORY_ORDER: tuple[str, ...] = tuple(reference.CATEGORIES)


def affinity_column(category: str) -> str:
    sanitised = "".join(char if char.isalnum() else "_" for char in category)
    return f"affinity_{sanitised}"


AFFINITY_COLUMNS: tuple[str, ...] = tuple(affinity_column(c) for c in CATEGORY_ORDER)

SIGNUP_GROWTH_RATE = 0.18


@dataclass(frozen=True)
class CustomerData:
    """Public customer table plus the latent parameters that drive behaviour.

    The latent frame never reaches PostgreSQL; it is only used inside the
    generator (and by generator tests) so that behaviour is internally consistent.
    """

    customers: pd.DataFrame
    latent: pd.DataFrame


def _signup_day_weights(config: GenerationConfig, rng: np.random.Generator) -> np.ndarray:
    days = day_range(config.first_signup_date, config.end_date)
    years = (days - np.datetime64(config.first_signup_date, "D")).astype("timedelta64[D]").astype(float) / 365.25
    growth = (1.0 + SIGNUP_GROWTH_RATE) ** years
    months = pd.DatetimeIndex(days.astype("datetime64[ns]")).month.to_numpy()
    seasonal = np.array([reference.MONTH_DEMAND_FACTORS[int(month)] for month in months])
    noise = ar1_multiplicative_noise(rng, len(days), sigma=0.10, phi=0.60)
    return growth * seasonal * noise


def _country_cities(
    rng: np.random.Generator, country_codes: np.ndarray
) -> np.ndarray:
    cities = np.empty(len(country_codes), dtype=object)
    for code, profile in reference.COUNTRIES.items():
        mask = country_codes == code
        count = int(mask.sum())
        if count:
            chosen = rng.integers(0, len(profile.cities), size=count)
            cities[mask] = np.array(profile.cities, dtype=object)[chosen]
    return cities.astype(str)


def generate_customers(config: GenerationConfig, rng: np.random.Generator) -> CustomerData:
    n = config.n_customers
    customer_ids = np.array([f"CUST-{i:06d}" for i in range(1, n + 1)])

    country_codes = np.array(list(reference.COUNTRIES), dtype=object)[
        draw_index_with_weights(
            rng, [c.weight for c in reference.COUNTRIES.values()], n
        )
    ]

    channel_names = np.array(list(reference.ACQUISITION_CHANNELS), dtype=object)[
        draw_index_with_weights(
            rng, [c.weight for c in reference.ACQUISITION_CHANNELS.values()], n
        )
    ]
    channel_bias = np.array(
        [reference.ACQUISITION_CHANNELS[name].retention_bias for name in channel_names]
    )

    first_names = np.array(reference.FIRST_NAMES, dtype=object)[
        rng.integers(0, len(reference.FIRST_NAMES), size=n)
    ]
    last_names = np.array(reference.LAST_NAMES, dtype=object)[
        rng.integers(0, len(reference.LAST_NAMES), size=n)
    ]

    emails = np.array(
        [
            f"{first.lower()}.{last.lower()}.{i:05d}@mail.novacart.example"
            for i, (first, last) in enumerate(zip(first_names, last_names, strict=True), start=1)
        ]
    )

    # Latent engagement drives order frequency; it is shifted by the acquisition
    # channel and then rank-normalised so the generator can reason in quantiles.
    raw_engagement = rng.beta(2.0, 3.5, size=n) * channel_bias
    order = np.argsort(np.argsort(raw_engagement))
    engagement = (order + 0.5) / n

    churn_hazard = np.clip(rng.beta(2.0, 5.0, size=n) * (1.35 - 0.7 * engagement), 0.01, 0.99)
    promo_affinity = np.clip(rng.beta(2.0, 2.2, size=n), 0.01, 0.99)

    category_weights = np.array([c.weight for c in reference.CATEGORIES.values()])
    affinity = rng.dirichlet(alpha=category_weights * 9.0, size=n)

    signup_weights = _signup_day_weights(config, rng)
    signup_days = day_range(config.first_signup_date, config.end_date)
    signup_index = draw_index_with_weights(rng, signup_weights, n)
    signup_dates = pd.to_datetime(signup_days[signup_index])

    signup_seconds = rng.integers(6 * 3600, 23 * 3600, size=n)
    created_at = signup_dates + pd.to_timedelta(signup_seconds, unit="s")

    cities = _country_cities(rng, country_codes.astype(str))

    customers = pd.DataFrame(
        {
            "customer_id": customer_ids,
            "email": emails,
            "first_name": first_names,
            "last_name": last_names,
            "country_code": country_codes.astype(str),
            "city": cities,
            "signup_date": signup_dates.date,
            "acquisition_channel": channel_names.astype(str),
            "created_at": created_at,
        }
    ).sort_values("customer_id", kind="stable")

    latent = pd.DataFrame(
        {
            "customer_id": customer_ids,
            "engagement": engagement,
            "churn_hazard": churn_hazard,
            "promo_affinity": promo_affinity,
            "country_code": country_codes.astype(str),
            "signup_date": signup_dates.date,
        }
    )
    for index, column in enumerate(AFFINITY_COLUMNS):
        latent[column] = affinity[:, index]

    customers = customers.sort_values("customer_id", kind="stable").reset_index(drop=True)
    latent = latent.sort_values("customer_id", kind="stable").reset_index(drop=True)
    return CustomerData(customers=customers, latent=latent)

