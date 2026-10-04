"""Top-level orchestration of the synthetic data build."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from novacart.settings import GENERATION_METADATA_DIR, RAW_DATA_DIR
from novacart.synthetic import reference
from novacart.synthetic.campaigns import generate_campaigns
from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.customers import CustomerData, generate_customers
from novacart.synthetic.models import TABLES
from novacart.synthetic.orders import generate_orders
from novacart.synthetic.payments import generate_payments
from novacart.synthetic.products import generate_products
from novacart.synthetic.validation import ValidationReport, validate_dataset
from novacart.synthetic.writer import build_manifest, write_manifest, write_tables

logger = logging.getLogger(__name__)

MANIFEST_NAME = "generation_manifest.json"


@dataclass
class GenerationResult:
    config: GenerationConfig
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    campaign_effects: pd.DataFrame = field(default_factory=pd.DataFrame)
    diagnostics: dict[str, float] = field(default_factory=dict)
    validation: ValidationReport | None = None
    manifest: dict[str, object] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)
    manifest_path: Path | None = None

    def row_counts(self) -> dict[str, int]:
        return {key: len(frame) for key, frame in self.frames.items()}


def build_frames(
    config: GenerationConfig,
) -> tuple[dict[str, pd.DataFrame], dict[str, float], pd.DataFrame, pd.DataFrame]:
    """Generate every table in memory. Returns (frames, diagnostics, effects, latent)."""
    reference.validate_reference_data()

    seeds = np.random.SeedSequence(config.seed).spawn(5)
    rng_customers = np.random.default_rng(seeds[0])
    rng_products = np.random.default_rng(seeds[1])
    rng_campaigns = np.random.default_rng(seeds[2])
    rng_orders = np.random.default_rng(seeds[3])
    rng_payments = np.random.default_rng(seeds[4])

    logger.info("Generating %s customers", f"{config.n_customers:,}")
    customer_data: CustomerData = generate_customers(config, rng_customers)

    logger.info("Generating %s products", f"{config.n_products:,}")
    product_data = generate_products(config, rng_products)

    logger.info("Generating %s campaigns with randomised holdout groups", config.n_campaigns)
    campaign_data = generate_campaigns(config, rng_campaigns, customer_data)

    logger.info("Simulating orders for %s customers", f"{config.n_customers:,}")
    order_data = generate_orders(config, rng_orders, customer_data, product_data, campaign_data)

    logger.info("Settling payments")
    payments = generate_payments(rng_payments, order_data.orders)

    frames = {
        "customers": customer_data.customers,
        "products": product_data.products,
        "marketing_campaigns": campaign_data.campaigns,
        "campaign_assignments": campaign_data.assignments,
        "orders": order_data.orders,
        "order_items": order_data.order_items,
        "payments": payments,
    }

    for key, spec in TABLES.items():
        frames[key] = frames[key].loc[:, list(spec.columns)].reset_index(drop=True)

    diagnostics = dict(order_data.diagnostics)
    diagnostics["repeat_purchase_rate"] = float(
        order_data.orders.groupby("customer_id")["order_id"].count().ge(2).mean()
    )
    diagnostics["purchasing_customers"] = float(order_data.orders["customer_id"].nunique())
    diagnostics["campaign_plausible_lift_share"] = float(
        (~campaign_data.effects["is_placebo"]).mean()
    )

    return frames, diagnostics, campaign_data.effects, customer_data.latent


def generate_dataset(
    config: GenerationConfig | None = None,
    *,
    write: bool = True,
    output_dir: Path | None = None,
    metadata_dir: Path | None = None,
    validate: bool = True,
) -> GenerationResult:
    config = config or GenerationConfig()
    frames, diagnostics, effects, latent = build_frames(config)

    report = validate_dataset(frames, config) if validate else None
    if report is not None:
        report.raise_if_failed()
        for warning in report.warnings:
            logger.warning("Warning: %s (%d rows)", warning.description, warning.failing_rows)

    result = GenerationResult(
        config=config,
        frames=frames,
        campaign_effects=effects,
        diagnostics=diagnostics,
        validation=report,
    )

    if write:
        target_dir = output_dir or RAW_DATA_DIR
        result.paths = write_tables(frames, target_dir)
        manifest = build_manifest(
            config=config,
            frames=frames,
            paths=result.paths,
            diagnostics=diagnostics,
            validation=report or ValidationReport(),
            campaign_effects=effects,
            latent=latent,
        )
        result.manifest = manifest
        result.manifest_path = write_manifest(manifest, (metadata_dir or GENERATION_METADATA_DIR) / MANIFEST_NAME)

    logger.info(
        "Generated %s orders, %s order items, %s payments",
        f"{len(frames['orders']):,}",
        f"{len(frames['order_items']):,}",
        f"{len(frames['payments']):,}",
    )
    return result

