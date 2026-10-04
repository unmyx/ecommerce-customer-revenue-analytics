"""CSV and manifest writing for the generated dataset."""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

import novacart
from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.models import TABLES
from novacart.synthetic.validation import ValidationReport

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def write_tables(
    frames: dict[str, pd.DataFrame], output_dir: Path
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for key, spec in TABLES.items():
        frame = frames[key]
        missing = set(spec.columns) - set(frame.columns)
        if missing:
            raise ValueError(f"{key} is missing columns required by the schema: {sorted(missing)}")
        path = output_dir / spec.csv_name
        frame.loc[:, list(spec.columns)].to_csv(
            path,
            index=False,
            date_format=TIMESTAMP_FORMAT,
            float_format="%.2f",
            lineterminator="\n",
        )
        written[key] = path
    return written


def _latent_summary(latent: pd.DataFrame) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for column in ("engagement", "churn_hazard", "promo_affinity"):
        series = latent[column]
        summary[column] = {
            "mean": round(float(series.mean()), 4),
            "p10": round(float(series.quantile(0.10)), 4),
            "median": round(float(series.median()), 4),
            "p90": round(float(series.quantile(0.90)), 4),
        }
    return summary


def build_manifest(
    *,
    config: GenerationConfig,
    frames: dict[str, pd.DataFrame],
    paths: dict[str, Path],
    diagnostics: dict[str, float],
    validation: ValidationReport,
    campaign_effects: pd.DataFrame,
    latent: pd.DataFrame | None,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "project": "NovaCart E-commerce Customer & Revenue Analytics",
        "dataset": "synthetic",
        "generator_version": novacart.__version__,
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": config.seed,
        "configuration": {
            "n_customers": config.n_customers,
            "n_products": config.n_products,
            "n_campaigns": config.n_campaigns,
            "target_orders": config.target_orders,
            "start_date": config.start_date.isoformat(),
            "end_date": config.end_date.isoformat(),
            "first_signup_date": config.first_signup_date.isoformat(),
            "never_purchase_share": config.never_purchase_share,
            "baseline_order_share": config.baseline_order_share,
            "annual_growth_rate": config.annual_growth_rate,
            "annual_price_inflation": config.annual_price_inflation,
            "order_dispersion": config.order_dispersion,
            "average_items_per_order": config.average_items_per_order,
            "zero_lift_campaign_share": config.zero_lift_campaign_share,
        },
        "row_counts": {key: len(frame) for key, frame in frames.items()},
        "file_checksums_sha256": {
            key: sha256_file(path) for key, path in paths.items()
        },
        "diagnostics": {key: round(float(value), 4) for key, value in diagnostics.items()},
        "validation": {
            "summary": validation.summary(),
            "issues": [
                {
                    "check_id": issue.check_id,
                    "description": issue.description,
                    "failing_rows": issue.failing_rows,
                    "severity": issue.severity,
                    "sample": list(issue.sample),
                }
                for issue in validation.issues
            ],
        },
        "campaign_ground_truth": campaign_effects.to_dict(orient="records"),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "platform": platform.platform(),
        },
    }
    if latent is not None:
        manifest["latent_parameter_summary"] = _latent_summary(latent)
    return manifest


def write_manifest(manifest: dict[str, object], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path

