"""Dashboard export layer.

Reads the canonical analytical outputs (``novacart.analytics``) and writes one CSV
per dashboard dataset into ``outputs/dashboard/csv/``, together with a data
dictionary and a manifest of row counts and SHA-256 checksums.

Rules
    * **No metric is recalculated here.** Every column is copied or renamed from a
      canonical table produced by the SQL layer or :mod:`novacart.analytics`.
    * **Schemas are declared, not implied.** :data:`EXPORT_SPECS` lists the exact
      columns of every export; the builder fails loudly if a canonical table no
      longer provides them, and the data dictionary is generated from the same
      declarations so documentation cannot drift.
    * **Exports are reproducible.** The same database state produces byte-identical
      CSV files.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from novacart.analytics.common import (
    AnalysisInputs,
    AnalyticsError,
    load_analysis_inputs,
    require_columns,
)
from novacart.analytics.report import BusinessAnalysis, analyse
from novacart.dashboard.schema import (
    COMMON_DESCRIPTIONS,
    EXPORT_SPEC_BY_NAME,
    EXPORT_SPECS,
)
from novacart.settings import OUTPUT_DIR
from novacart.synthetic.writer import sha256_file

logger = logging.getLogger(__name__)

DASHBOARD_DIR = OUTPUT_DIR / "dashboard"
CSV_DIR = DASHBOARD_DIR / "csv"
MANIFEST_NAME = "export_manifest.json"
DATA_DICTIONARY_NAME = "data_dictionary.csv"


@dataclass
class DashboardExports:
    """Dashboard-ready frames plus the paths they were written to."""

    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)
    manifest: dict[str, object] = field(default_factory=dict)
    manifest_path: Path | None = None
    data_dictionary_path: Path | None = None

    def row_counts(self) -> dict[str, int]:
        return {name: len(frame) for name, frame in self.frames.items()}


def fact_orders_frame(orders: pd.DataFrame, rfm: pd.DataFrame) -> pd.DataFrame:
    """Sliceable order fact: canonical order columns plus slicer-friendly labels."""
    require_columns(
        orders,
        (
            "order_id",
            "customer_id",
            "order_date",
            "order_month",
            "order_status",
            "is_revenue_recognised",
            "recognised_net_revenue",
            "recognised_units",
            "gross_merchandise_amount",
            "discount_amount",
            "country_code",
            "sales_channel",
            "acquisition_channel",
            "campaign_id",
            "is_campaign_attributed",
        ),
        "fact_orders_frame",
    )
    year_month = pd.to_datetime(orders["order_month"])
    frame = pd.DataFrame(
        {
            "order_id": orders["order_id"],
            "customer_id": orders["customer_id"],
            "order_date": pd.to_datetime(orders["order_date"]),
            "order_month": year_month,
            "year_month": year_month.dt.strftime("%Y-%m"),
            "year": year_month.dt.year,
            "quarter": year_month.dt.quarter,
            "order_status": orders["order_status"],
            "is_revenue_recognised": orders["is_revenue_recognised"],
            "recognised_orders": orders["is_revenue_recognised"].astype("int64"),
            "revenue": orders["recognised_net_revenue"],
            "units": orders["recognised_units"],
            "gross_merchandise_amount": orders["gross_merchandise_amount"],
            "discount_amount": orders["discount_amount"],
            "country_code": orders["country_code"],
            "sales_channel": orders["sales_channel"],
            "acquisition_channel": orders["acquisition_channel"],
            "campaign_id": orders["campaign_id"],
            "is_campaign_attributed": orders["is_campaign_attributed"],
        }
    )
    return frame.merge(rfm[["customer_id", "rfm_segment"]], on="customer_id", how="left")


def fact_order_lines_frame(
    lines: pd.DataFrame, rfm: pd.DataFrame, customers: pd.DataFrame
) -> pd.DataFrame:
    """Sliceable line fact: canonical line columns plus slicer-friendly labels.

    ``fct_order_lines`` has no country column, so the customer's country is joined
    from the customer mart (an export-layer join of canonical columns, not a metric
    recalculation).
    """
    require_columns(
        lines,
        (
            "order_item_id",
            "order_id",
            "customer_id",
            "order_date",
            "order_month",
            "product_id",
            "product_name",
            "brand",
            "category",
            "subcategory",
            "is_revenue_recognised",
            "quantity",
            "recognised_units",
            "unit_price",
            "recognised_line_net_revenue",
            "line_cost",
            "line_gross_profit",
            "sales_channel",
            "campaign_id",
        ),
        "fact_order_lines_frame",
    )
    require_columns(customers, ("customer_id", "country_code"), "fact_order_lines_frame")
    year_month = pd.to_datetime(lines["order_month"])
    frame = pd.DataFrame(
        {
            "order_item_id": lines["order_item_id"],
            "order_id": lines["order_id"],
            "customer_id": lines["customer_id"],
            "order_date": pd.to_datetime(lines["order_date"]),
            "order_month": year_month,
            "year_month": year_month.dt.strftime("%Y-%m"),
            "year": year_month.dt.year,
            "quarter": year_month.dt.quarter,
            "product_id": lines["product_id"],
            "product_name": lines["product_name"],
            "brand": lines["brand"],
            "category": lines["category"],
            "subcategory": lines["subcategory"],
            "is_revenue_recognised": lines["is_revenue_recognised"],
            "quantity": lines["quantity"],
            "units": lines["recognised_units"],
            "unit_price": lines["unit_price"],
            "revenue": lines["recognised_line_net_revenue"],
            "line_cost": lines["line_cost"],
            "line_gross_profit": lines["line_gross_profit"],
            "sales_channel": lines["sales_channel"],
            "campaign_id": lines["campaign_id"],
        }
    )
    frame = frame.merge(
        customers[["customer_id", "country_code"]], on="customer_id", how="left"
    )
    return frame.merge(rfm[["customer_id", "rfm_segment"]], on="customer_id", how="left")


def build_export_frames(
    analysis: BusinessAnalysis, inputs: AnalysisInputs | None = None
) -> dict[str, pd.DataFrame]:
    """Reshape the canonical analytics outputs into the declared export schemas."""
    declarations = EXPORT_SPECS
    rfm = analysis.rfm.loc[:, ["customer_id", "rfm_segment"]]
    frames: dict[str, pd.DataFrame] = {
        "fact_orders": fact_orders_frame(inputs.orders, rfm) if inputs is not None else pd.DataFrame(),
        "fact_order_lines": fact_order_lines_frame(inputs.order_lines, rfm, inputs.customers)
        if inputs is not None
        else pd.DataFrame(),
        "kpi_summary": analysis.kpis,
        "monthly_revenue": analysis.monthly,
        "daily_revenue": analysis.daily,
        "category_performance": analysis.categories,
        "product_performance": analysis.products,
        "declining_products": analysis.declining_products,
        "customer_segments": analysis.rfm_segments,
        "customer_lifecycle": analysis.segments,
        "customer_value_deciles": analysis.deciles,
        "customer_concentration": analysis.concentration,
        "customer_rfm": analysis.rfm,
        "country_performance": analysis.countries,
        "cohort_sizes": analysis.cohorts.sizes,
        "cohort_retention": analysis.cohorts.retention,
        "campaign_results": analysis.campaign_statistics,
        "campaign_comparison": analysis.campaign_comparison,
    }

    prepared: dict[str, pd.DataFrame] = {}
    for name, frame in frames.items():
        if frame.empty and name.startswith("fact_") and inputs is None:
            continue
        spec = declarations[name]
        require_columns(frame, spec.columns, f"dashboard export {name}")
        export = frame.loc[:, list(spec.columns)].reset_index(drop=True).copy()
        prepared[name] = export
    return prepared


def build_data_dictionary() -> pd.DataFrame:
    """One row per exported column: dataset, column, dtype, key flag and description."""
    rows: list[dict[str, object]] = []
    for spec in EXPORT_SPECS.values():
        for column in spec.columns:
            rows.append(
                {
                    "dataset": spec.name,
                    "column": column,
                    "data_type": spec.types.get(column, "text"),
                    "is_key": column in spec.key_columns,
                    "description": spec.descriptions.get(column)
                    or COMMON_DESCRIPTIONS.get(column, ""),
                    "source": spec.source,
                }
            )
    return pd.DataFrame(rows)


def build_dashboard_exports(
    *,
    inputs: AnalysisInputs | None = None,
    analysis: BusinessAnalysis | None = None,
    output_dir: Path | None = None,
    write: bool = True,
    include_facts: bool = True,
) -> DashboardExports:
    """Build (and optionally write) every dashboard dataset plus its manifest."""
    if analysis is None:
        inputs = inputs or load_analysis_inputs()
        analysis = analyse(inputs)
    if include_facts and inputs is None:
        # The sliceable fact exports come from the canonical fact tables, not from
        # the aggregated analytics frames, so they need the loaded inputs.
        inputs = load_analysis_inputs()

    frames = build_export_frames(analysis, inputs if include_facts else None)
    data_dictionary = build_data_dictionary()
    # Copy so later additions (the data dictionary) cannot leak into the manifest loop.
    exports = DashboardExports(frames=dict(frames))

    if not write:
        exports.frames[DATA_DICTIONARY_NAME.removesuffix(".csv")] = data_dictionary
        return exports

    target = output_dir or CSV_DIR
    target.mkdir(parents=True, exist_ok=True)

    for name, frame in frames.items():
        path = target / f"{name}.csv"
        frame.to_csv(path, index=False, lineterminator="\n")
        exports.paths[name] = path

    dictionary_path = target / DATA_DICTIONARY_NAME
    data_dictionary.to_csv(dictionary_path, index=False, lineterminator="\n")
    exports.data_dictionary_path = dictionary_path

    manifest: dict[str, object] = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "analysis_window": {
            "start": str(analysis.kpis.iloc[0]["period_start"]),
            "end": str(analysis.kpis.iloc[0]["period_end"]),
        },
        "datasets": {
            name: {
                "rows": len(frame),
                "columns": list(frame.columns),
                "source": EXPORT_SPEC_BY_NAME[name].source,
                "checksum_sha256": sha256_file(exports.paths[name]),
            }
            for name, frame in frames.items()
        },
        "data_dictionary": {
            "rows": len(data_dictionary),
            "columns": list(data_dictionary.columns),
            "checksum_sha256": sha256_file(dictionary_path),
        },
    }
    manifest_path = target / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    exports.manifest = manifest
    exports.manifest_path = manifest_path
    exports.frames["data_dictionary"] = data_dictionary

    logger.info(
        "Wrote %d dashboard datasets (%d rows) to %s",
        len(frames),
        sum(len(frame) for frame in frames.values()),
        target,
    )
    return exports


def load_export_frame(name: str, *, output_dir: Path | None = None) -> pd.DataFrame:
    """Read a written export back (used by the summary, previews and tests)."""
    if name not in EXPORT_SPEC_BY_NAME:
        raise AnalyticsError(f"Unknown dashboard dataset {name!r}")
    path = (output_dir or CSV_DIR) / f"{name}.csv"
    if not path.is_file():
        raise AnalyticsError(f"Dashboard dataset {name!r} has not been exported yet ({path})")
    return pd.read_csv(path)

