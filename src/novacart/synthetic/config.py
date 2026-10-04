"""Configuration for the synthetic data generator."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import date


class GenerationConfigError(ValueError):
    """Raised when generator parameters are inconsistent."""


@dataclass(frozen=True)
class GenerationConfig:
    """Parameters that fully determine the generated dataset.

    Every random draw in the generator descends from ``seed`` through
    ``numpy.random.SeedSequence``, so the same configuration always produces a
    byte-identical dataset.
    """

    seed: int = 20261004
    n_customers: int = 15_000
    n_products: int = 1_200
    n_campaigns: int = 20
    target_orders: int = 85_000
    start_date: date = date(2024, 10, 1)
    end_date: date = date(2026, 9, 30)
    first_signup_date: date = date(2023, 1, 1)
    never_purchase_share: float = 0.09
    annual_growth_rate: float = 0.22
    annual_price_inflation: float = 0.03
    order_dispersion: float = 3.0
    average_items_per_order: float = 2.35
    zero_lift_campaign_share: float = 0.30
    baseline_order_share: float = 0.94

    def __post_init__(self) -> None:
        if self.seed <= 0:
            raise GenerationConfigError("seed must be a positive integer")
        for field in ("n_customers", "n_products", "n_campaigns", "target_orders"):
            if getattr(self, field) <= 0:
                raise GenerationConfigError(f"{field} must be positive")
        if self.first_signup_date > self.start_date:
            raise GenerationConfigError("first_signup_date must not be after start_date")
        if self.start_date >= self.end_date:
            raise GenerationConfigError("start_date must be before end_date")
        if not 0.0 <= self.never_purchase_share < 1.0:
            raise GenerationConfigError("never_purchase_share must be in [0, 1)")
        if not 0.0 <= self.zero_lift_campaign_share < 1.0:
            raise GenerationConfigError("zero_lift_campaign_share must be in [0, 1)")
        if not 0.0 < self.baseline_order_share <= 1.0:
            raise GenerationConfigError("baseline_order_share must be in (0, 1]")
        if self.order_dispersion <= 0:
            raise GenerationConfigError("order_dispersion must be positive")
        if self.average_items_per_order <= 1.0:
            raise GenerationConfigError("average_items_per_order must be greater than 1")
        if self.target_orders < self.n_customers // 2:
            raise GenerationConfigError(
                "target_orders is too small relative to n_customers; the dataset would not "
                "contain a realistic repeat-purchase structure"
            )

    def with_overrides(self, **overrides: object) -> GenerationConfig:
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)  # type: ignore[arg-type]

    @classmethod
    def from_env(cls) -> GenerationConfig:
        """Build a configuration, letting environment variables override defaults."""
        overrides: dict[str, object] = {}
        int_fields = {
            "NOVACART_SEED": "seed",
            "NOVACART_CUSTOMERS": "n_customers",
            "NOVACART_PRODUCTS": "n_products",
            "NOVACART_CAMPAIGNS": "n_campaigns",
            "NOVACART_TARGET_ORDERS": "target_orders",
        }
        for env_name, field_name in int_fields.items():
            raw = os.getenv(env_name)
            if raw:
                try:
                    overrides[field_name] = int(raw)
                except ValueError as exc:
                    raise GenerationConfigError(f"{env_name} must be an integer") from exc

        date_fields = {
            "NOVACART_START_DATE": "start_date",
            "NOVACART_END_DATE": "end_date",
        }
        for env_name, field_name in date_fields.items():
            raw = os.getenv(env_name)
            if raw:
                try:
                    overrides[field_name] = date.fromisoformat(raw)
                except ValueError as exc:
                    raise GenerationConfigError(f"{env_name} must be an ISO date") from exc

        return cls(**overrides)  # type: ignore[arg-type]

