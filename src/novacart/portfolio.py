"""Portfolio asset packaging: architecture diagram, screenshots and sample outputs.

Every image is rendered from the canonical analytical results or from the exported
dashboard datasets - no mock-ups, no hand-edited numbers. The samples copied into
``portfolio/sample_outputs/`` are the real generated files, so a reviewer can see
the outputs without running the pipeline.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from novacart.analytics.common import AnalyticsError
from novacart.analytics.plots import (
    bar_panel,
    count_formatter,
    currency_formatter,
    line_panel,
    plot_cohort_retention_heatmap,
)
from novacart.dashboard.exports import CSV_DIR
from novacart.dashboard.preview import draw_executive_overview
from novacart.settings import OUTPUT_DIR, PROJECT_ROOT
from novacart.synthetic.writer import sha256_file

logger = logging.getLogger(__name__)

PORTFOLIO_DIR = PROJECT_ROOT / "portfolio"
SCREENSHOTS_DIR = PORTFOLIO_DIR / "screenshots"
SAMPLE_OUTPUTS_DIR = PORTFOLIO_DIR / "sample_outputs"
CASE_STUDY = PORTFOLIO_DIR / "case-study.md"
MANIFEST_NAME = "assets_manifest.json"

IMAGE_FILENAMES: dict[str, str] = {
    "architecture": "01_architecture.png",
    "executive_dashboard": "02_executive_dashboard.png",
    "revenue_analysis": "03_revenue_analysis.png",
    "rfm_segmentation": "04_rfm_segmentation.png",
    "cohort_heatmap": "05_cohort_heatmap.png",
    "campaign_statistics": "06_campaign_statistics.png",
}

#: dataset name in outputs/dashboard/csv -> file name in portfolio/sample_outputs
SAMPLE_DATASETS: dict[str, str] = {
    "kpi_summary": "kpi_summary.csv",
    "monthly_revenue": "monthly_revenue.csv",
    "customer_segments": "rfm_segments.csv",
    "campaign_results": "campaign_results.csv",
    "declining_products": "declining_products.csv",
}

ACCENT = "#1f4e79"
ACCENT_LIGHT = "#9dc3e6"
ACCENT_WARM = "#c55a11"
INK = "#1f2933"
MUTED = "#6b7280"
DPI = 150


def _style() -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.22,
            "figure.facecolor": "white",
        }
    )


_style()


def _read_exports(exports_dir: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for name in (
        "kpi_summary",
        "monthly_revenue",
        "category_performance",
        "country_performance",
        "customer_segments",
        "customer_value_deciles",
        "cohort_retention",
        "cohort_sizes",
        "campaign_results",
        "product_performance",
        "declining_products",
    ):
        path = exports_dir / f"{name}.csv"
        if not path.is_file():
            raise AnalyticsError(
                f"dashboard export {name!r} not found in {exports_dir}; "
                "run scripts/build_dashboard.py first"
            )
        frames[name] = pd.read_csv(path, low_memory=False)
    return frames


def draw_architecture() -> Figure:
    """Layered architecture diagram (data generation -> warehouse -> analytics -> BI)."""
    layers = [
        (
            "1. Synthetic source system",
            "seeded generator, schema-complete CSV files, generation manifest with checksums",
            "#eaf1f8",
        ),
        (
            "2. PostgreSQL raw layer",
            "raw schema: customers, products, orders, order_items, payments, campaigns, assignments",
            "#dce9f5",
        ),
        (
            "3. Analytical SQL layer",
            "staging views, order/line facts, revenue, customer, product and campaign marts, reconciliation checks",
            "#c9dcf0",
        ),
        (
            "4. Python analytics",
            "KPIs, trends, RFM, cohorts, campaign statistics (Welch t-test, bootstrap, Hedges' g, BH FDR)",
            "#b6cfea",
        ),
        (
            "5. Dashboard exports",
            "18 declared datasets + data dictionary + manifest; facts and aggregates reconcile exactly",
            "#a3c2e5",
        ),
        (
            "6. Presentation",
            "Power BI pages 1-4, generated executive summary (Markdown/HTML/Excel), portfolio assets",
            "#8fb5e0",
        ),
    ]

    figure, axis = plt.subplots(figsize=(13.0, 8.0), dpi=DPI)
    axis.set_xlim(0, 10)
    axis.set_ylim(0, len(layers) * 1.35 + 0.6)
    axis.axis("off")
    figure.suptitle(
        "NovaCart analytics platform - architecture",
        x=0.02,
        ha="left",
        fontsize=17,
        fontweight="bold",
        color=INK,
    )
    figure.text(
        0.02,
        0.93,
        "One reproducible path from synthetic data to business presentation; every layer downstream of the raw schema is derived.",
        ha="left",
        fontsize=10,
        color=MUTED,
    )

    top = len(layers) * 1.35 + 0.3
    for index, (title, detail, colour) in enumerate(layers):
        y = top - (index + 1) * 1.35
        box = FancyBboxPatch(
            (0.35, y),
            9.3,
            0.95,
            boxstyle="round,pad=0.06,rounding_size=0.08",
            linewidth=1,
            edgecolor="#c3cdd8",
            facecolor=colour,
        )
        axis.add_patch(box)
        axis.text(0.65, y + 0.63, title, fontsize=12, fontweight="bold", color=ACCENT, va="center")
        axis.text(0.65, y + 0.28, detail, fontsize=9, color=INK, va="center")
        if index < len(layers) - 1:
            axis.add_patch(
                FancyArrowPatch(
                    (5.0, y - 0.04),
                    (5.0, y - 0.36),
                    arrowstyle="-|>",
                    mutation_scale=16,
                    linewidth=1.4,
                    color=ACCENT,
                )
            )
    figure.tight_layout(rect=(0, 0.02, 1, 0.92))
    return figure


def draw_revenue_analysis(frames: dict[str, pd.DataFrame]) -> Figure:
    """Monthly revenue trend, category mix and market mix."""
    monthly = frames["monthly_revenue"].sort_values("month_start")
    categories = frames["category_performance"].sort_values("revenue")
    countries = frames["country_performance"].sort_values("revenue").tail(10)

    figure = plt.figure(figsize=(16.0, 5.6), dpi=DPI)
    figure.suptitle(
        "Revenue analysis", x=0.01, ha="left", fontsize=16, fontweight="bold", color=INK
    )
    figure.text(
        0.01,
        0.925,
        "Recognised net merchandise revenue (completed orders, discounts applied, shipping and VAT excluded)",
        ha="left",
        fontsize=9,
        color=MUTED,
    )
    grid = figure.add_gridspec(1, 3, left=0.05, right=0.99, top=0.85, bottom=0.16, wspace=0.32)
    line_panel(
        figure.add_subplot(grid[0, 0]),
        list(monthly["year_month"]),
        monthly["revenue"].to_numpy(),
        "Monthly net revenue",
        max_labels=10,
    )
    bar_panel(
        figure.add_subplot(grid[0, 1]),
        list(categories["category"]),
        categories["revenue"].to_numpy(),
        "Revenue by category",
        label_size=9,
    )
    bar_panel(
        figure.add_subplot(grid[0, 2]),
        list(countries["country_code"]),
        countries["revenue"].to_numpy(),
        "Revenue by country (top 10)",
        label_size=9,
    )
    return figure


def draw_rfm_segmentation(frames: dict[str, pd.DataFrame]) -> Figure:
    """RFM segment size, revenue contribution and customer value distribution."""
    segments = frames["customer_segments"]
    deciles = frames["customer_value_deciles"]
    by_customers = segments.sort_values("customers")
    by_revenue = segments.loc[segments["revenue"] > 0].sort_values("revenue")

    figure = plt.figure(figsize=(16.0, 5.6), dpi=DPI)
    figure.suptitle(
        "RFM segmentation", x=0.01, ha="left", fontsize=16, fontweight="bold", color=INK
    )
    figure.text(
        0.01,
        0.925,
        "Quintile scores over purchasing customers; segments assigned by documented priority rules",
        ha="left",
        fontsize=9,
        color=MUTED,
    )
    grid = figure.add_gridspec(1, 3, left=0.05, right=0.99, top=0.85, bottom=0.16, wspace=0.32)
    bar_panel(
        figure.add_subplot(grid[0, 0]),
        list(by_customers["rfm_segment"]),
        by_customers["customers"].to_numpy(),
        "Customers by segment",
        formatter=count_formatter,
        label_size=9,
    )
    bar_panel(
        figure.add_subplot(grid[0, 1]),
        list(by_revenue["rfm_segment"]),
        by_revenue["revenue"].to_numpy(),
        "Revenue by segment",
        label_size=9,
    )
    axis = figure.add_subplot(grid[0, 2])
    positions = np.arange(len(deciles))
    axis.bar(positions, deciles["revenue_share_pct"], color=ACCENT_WARM, width=0.7)
    axis.set_xticks(positions)
    axis.set_xticklabels([str(int(value)) for value in deciles["revenue_decile"]])
    axis.yaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0f}%"))
    axis.set_title("Revenue share by customer decile", loc="left")
    axis.set_xlabel("Decile (1 = lowest spend)", fontsize=9)
    return figure


def draw_cohort_heatmap(frames: dict[str, pd.DataFrame], analysis=None) -> Figure:
    """Cohort retention heatmap from the canonical retention matrix."""
    if analysis is not None:
        matrix = analysis.cohorts.retention_matrix
    else:
        retention = frames["cohort_retention"]
        matrix = retention.pivot(
            index="cohort_month", columns="month_offset", values="retention_rate"
        ).sort_index()
    figure = plot_cohort_retention_heatmap(matrix)
    figure.set_size_inches(13.0, 8.0)
    return figure


def draw_campaign_statistics(frames: dict[str, pd.DataFrame]) -> Figure:
    """Campaign lift and confidence intervals."""
    campaigns = frames["campaign_results"].copy()
    lift = campaigns.sort_values("relative_difference")
    intervals = campaigns.sort_values("absolute_difference").reset_index(drop=True)

    figure = plt.figure(figsize=(16.0, 6.4), dpi=DPI)
    figure.suptitle(
        "Campaign analysis", x=0.01, ha="left", fontsize=16, fontweight="bold", color=INK
    )
    figure.text(
        0.01,
        0.93,
        "Intention-to-treat comparison of treatment and holdout; Welch 95% confidence intervals, "
        "Benjamini-Hochberg FDR control",
        ha="left",
        fontsize=9,
        color=MUTED,
    )
    grid = figure.add_gridspec(1, 2, left=0.075, right=0.99, top=0.86, bottom=0.12, wspace=0.28)

    axis = figure.add_subplot(grid[0, 0])
    colours = [
        ACCENT if significant else ACCENT_LIGHT for significant in lift["statistically_significant"]
    ]
    axis.barh(lift["campaign_id"], lift["relative_difference"] * 100, color=colours)
    axis.axvline(10, color=ACCENT_WARM, linestyle="--", linewidth=1)
    axis.axvline(0, color=INK, linewidth=1)
    axis.xaxis.set_major_formatter(plt.FuncFormatter(lambda value, _: f"{value:.0f}%"))
    axis.set_title("Relative lift vs holdout", loc="left")
    axis.grid(axis="y", visible=False)

    axis = figure.add_subplot(grid[0, 1])
    for position, row in intervals.iterrows():
        colour = ACCENT if row["statistically_significant"] else ACCENT_LIGHT
        axis.plot(
            [row["confidence_interval_low"], row["confidence_interval_high"]],
            [position, position],
            color=colour,
            linewidth=2.4,
        )
        axis.plot(row["absolute_difference"], position, marker="o", color=colour, markersize=4.5)
    axis.axvline(0, color=INK, linewidth=1)
    axis.set_yticks(range(len(intervals)))
    axis.set_yticklabels(intervals["campaign_id"], fontsize=8.5)
    axis.xaxis.set_major_formatter(plt.FuncFormatter(currency_formatter))
    axis.set_title("Lift with 95% confidence intervals", loc="left")
    axis.grid(axis="y", visible=False)
    return figure


def _copy_samples(exports_dir: Path, output_dir: Path) -> dict[str, Path]:
    samples: dict[str, Path] = {}
    for dataset, filename in SAMPLE_DATASETS.items():
        source = exports_dir / f"{dataset}.csv"
        if not source.is_file():
            raise AnalyticsError(f"missing dashboard export {source}")
        target = output_dir / filename
        shutil.copyfile(source, target)
        samples[dataset] = target

    extras = {
        "executive_summary": (OUTPUT_DIR / "dashboard" / "summary" / "executive_summary.md", "executive_summary.md"),
        "end_to_end_reconciliation": (
            OUTPUT_DIR / "reconciliation" / "end_to_end_reconciliation.csv",
            "end_to_end_reconciliation.csv",
        ),
    }
    for key, (source, filename) in extras.items():
        if source.is_file():
            target = output_dir / filename
            shutil.copyfile(source, target)
            samples[key] = target
    return samples


def build_portfolio_assets(
    *,
    inputs=None,
    analysis=None,
    exports_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, dict[str, Path]]:
    """Render the six portfolio images and copy the sample outputs."""
    source_dir = exports_dir or CSV_DIR
    base = output_dir or PORTFOLIO_DIR
    screenshots = base / "screenshots"
    samples_dir = base / "sample_outputs"
    screenshots.mkdir(parents=True, exist_ok=True)
    samples_dir.mkdir(parents=True, exist_ok=True)

    frames = _read_exports(source_dir)
    figures = {
        "architecture": draw_architecture(),
        "executive_dashboard": draw_executive_overview(frames),
        "revenue_analysis": draw_revenue_analysis(frames),
        "rfm_segmentation": draw_rfm_segmentation(frames),
        "cohort_heatmap": draw_cohort_heatmap(frames, analysis),
        "campaign_statistics": draw_campaign_statistics(frames),
    }
    images: dict[str, Path] = {}
    for key, figure in figures.items():
        path = screenshots / IMAGE_FILENAMES[key]
        figure.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
        plt.close(figure)
        images[key] = path

    samples = _copy_samples(source_dir, samples_dir)

    manifest = {
        "images": {
            key: {"file": path.name, "checksum_sha256": sha256_file(path)}
            for key, path in images.items()
        },
        "sample_outputs": {
            key: {"file": path.name, "checksum_sha256": sha256_file(path)}
            for key, path in samples.items()
        },
        "case_study": CASE_STUDY.name if CASE_STUDY.is_file() else None,
        "note": (
            "Images are rendered from the canonical analytical results and the exported "
            "dashboard datasets; sample outputs are copies of the generated files."
        ),
    }
    (base / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    logger.info("Built %d portfolio images and %d sample outputs", len(images), len(samples))
    return {"images": images, "samples": samples}


def main(argv: list[str] | None = None) -> int:
    import argparse

    from novacart.analytics.common import load_analysis_inputs
    from novacart.analytics.report import analyse
    from novacart.logging_config import configure_logging
    from novacart.settings import ConfigurationError, load_database_settings

    parser = argparse.ArgumentParser(
        prog="novacart-portfolio",
        description="Build the portfolio images and sample outputs.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(logging.WARNING if args.quiet else logging.INFO)

    try:
        settings = load_database_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2

    try:
        inputs = load_analysis_inputs(settings)
        analysis = analyse(inputs)
        paths = build_portfolio_assets(inputs=inputs, analysis=analysis, output_dir=args.output_dir)
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator
        print(f"Portfolio build failed: {exc}")
        return 1

    for key, path in sorted(paths["images"].items()):
        print(f"image  {key:<22} {path}")
    for key, path in sorted(paths["samples"].items()):
        print(f"sample {key:<22} {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

