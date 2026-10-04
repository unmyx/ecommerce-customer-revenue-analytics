"""Dashboard build orchestration: ``novacart-dashboard``.

Order of operations
    1. run the canonical analysis (or accept pre-computed inputs),
    2. export the dashboard datasets (CSV + data dictionary + manifest),
    3. generate the executive summary (Markdown, HTML, Excel),
    4. render the static Power BI page previews.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from novacart.analytics.common import (
    AnalysisInputs,
    format_compact_currency,
    format_count,
    format_percent,
    load_analysis_inputs,
)
from novacart.analytics.report import BusinessAnalysis, analyse
from novacart.dashboard.exports import CSV_DIR, build_dashboard_exports
from novacart.dashboard.preview import render_dashboard_previews
from novacart.dashboard.summary import (
    build_executive_summary,
    write_executive_summary,
)
from novacart.logging_config import configure_logging
from novacart.settings import PROJECT_ROOT, ConfigurationError, load_database_settings

logger = logging.getLogger(__name__)

DEFAULT_PREVIEW_DIR = PROJECT_ROOT / "powerbi" / "screenshots"


def build_dashboard_outputs(
    *,
    inputs: AnalysisInputs | None = None,
    analysis: BusinessAnalysis | None = None,
    output_dir: Path | None = None,
    preview_dir: Path | None = None,
    write_excel: bool = True,
    write_previews: bool = True,
) -> dict[str, object]:
    """Build every presentation-layer artefact and return the resulting paths."""
    if analysis is None:
        analysis = analyse(inputs or load_analysis_inputs())

    exports = build_dashboard_exports(analysis=analysis, output_dir=output_dir)
    summary = build_executive_summary(analysis)
    summary_dir = (output_dir or CSV_DIR).parent / "summary"
    summary_paths = write_executive_summary(
        summary, output_dir=summary_dir, write_excel=write_excel
    )
    previews: dict[str, Path] = {}
    if write_previews:
        previews = render_dashboard_previews(
            exports.frames, output_dir=preview_dir or DEFAULT_PREVIEW_DIR
        )
    return {
        "analysis": analysis,
        "exports": exports,
        "summary": summary,
        "summary_paths": summary_paths,
        "previews": previews,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="novacart-dashboard",
        description="Build the dashboard datasets, executive summary and page previews.",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Dashboard export folder")
    parser.add_argument("--preview-dir", type=Path, default=None, help="Where to write page previews")
    parser.add_argument("--no-excel", action="store_true", help="Skip the Excel summary")
    parser.add_argument("--no-previews", action="store_true", help="Skip the PNG page previews")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    configure_logging(logging.WARNING if args.quiet else logging.INFO)

    try:
        settings = load_database_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2

    try:
        result = build_dashboard_outputs(
            inputs=load_analysis_inputs(settings),
            output_dir=args.output_dir,
            preview_dir=args.preview_dir,
            write_excel=not args.no_excel,
            write_previews=not args.no_previews,
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator
        print(f"Dashboard build failed: {exc}")
        return 1

    exports = result["exports"]
    analysis = result["analysis"]
    kpi = analysis.kpis.iloc[0]
    print(f"Analysis window        : {kpi['period_start']} to {kpi['period_end']}")
    print(f"Net revenue            : {format_compact_currency(kpi['total_revenue'])}")
    print(f"Orders / customers     : {format_count(kpi['total_orders'])} / {format_count(kpi['unique_customers'])}")
    print(f"Average order value    : {format_compact_currency(kpi['average_order_value'])}")
    print(f"Repeat customer rate   : {format_percent(kpi['repeat_customer_rate'])}")
    print(f"Datasets exported      : {len(exports.frames) - 1}")
    for name, frame in sorted(exports.frames.items()):
        if name == "data_dictionary":
            continue
        print(f"  {name:<24} {len(frame):>7,} rows")
    for name, path in sorted(result["summary_paths"].items()):
        print(f"Summary ({name:<8})     : {path}")
    for name, path in sorted(result["previews"].items()):
        print(f"Preview ({name:<20}): {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

