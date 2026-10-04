"""End-to-end pipeline: synthetic data to portfolio-ready outputs.

``scripts/run_pipeline.py`` runs the twelve documented steps in order and stops at
the first failure with a message that names the step and the underlying error.
Nothing is hidden: every validation gate aborts the run.

    1.  generate synthetic data
    2.  verify the generated artefacts against their manifest
    3.  ensure PostgreSQL is running
    4.  create schemas and load the raw layer
    5.  run the raw data-quality checks
    6.  build the analytical SQL layer
    7.  run the analytical reconciliation checks
    8.  run the Python analytics (including the campaign statistics)
    9.  export the dashboard datasets and the executive summary
    10. rebuild the visual outputs
    11. build the portfolio assets
    12. (optional) run the test suite

The steps are plain callables, so the orchestration itself is unit tested with
fake steps instead of a live warehouse.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

from novacart.analytics.common import format_compact_currency, format_count, load_analysis_inputs
from novacart.analytics.report import BusinessAnalysis, build_business_analysis
from novacart.dashboard.cli import build_dashboard_outputs
from novacart.dashboard.exports import CSV_DIR
from novacart.ingestion.checks import failing_checks, run_raw_data_checks
from novacart.ingestion.loader import load_raw_tables
from novacart.logging_config import configure_logging
from novacart.reconciliation import build_end_to_end_reconciliation
from novacart.settings import (
    GENERATION_METADATA_DIR,
    PROJECT_ROOT,
    RAW_DATA_DIR,
    ConfigurationError,
    DatabaseSettings,
    load_database_settings,
)
from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.generator import generate_dataset
from novacart.synthetic.models import TABLES
from novacart.synthetic.writer import sha256_file
from novacart.warehouse import build_analytics_layer, fetch_reconciliation, list_analytical_views

logger = logging.getLogger(__name__)

MANIFEST_PATH = GENERATION_METADATA_DIR / "generation_manifest.json"
DATABASE_START_TIMEOUT_SECONDS = 90


class PipelineError(RuntimeError):
    """Raised when a pipeline step fails; carries the step that failed."""

    def __init__(self, step_key: str, step_title: str, cause: BaseException) -> None:
        super().__init__(f"step '{step_key}' ({step_title}) failed: {cause}")
        self.step_key = step_key
        self.step_title = step_title
        self.cause = cause


@dataclass
class PipelineContext:
    """Shared state passed between steps (so expensive work happens once)."""

    settings: DatabaseSettings | None = None
    config: GenerationConfig | None = None
    exports_dir: Path = CSV_DIR
    run_tests: bool = False
    inputs: object | None = None
    analysis: BusinessAnalysis | None = None
    completed: list[str] = field(default_factory=list)

    def resolved_settings(self) -> DatabaseSettings:
        if self.settings is None:
            self.settings = load_database_settings()
        return self.settings

    def resolved_config(self) -> GenerationConfig:
        if self.config is None:
            self.config = GenerationConfig.from_env()
        return self.config


@dataclass(frozen=True)
class PipelineStep:
    key: str
    title: str
    run: Callable[[PipelineContext], str]


@dataclass(frozen=True)
class StepResult:
    key: str
    title: str
    summary: str
    seconds: float


@dataclass
class PipelineReport:
    steps: list[StepResult] = field(default_factory=list)
    ok: bool = True


# ---------------------------------------------------------------------------
# step implementations
# ---------------------------------------------------------------------------
def _step_generate(context: PipelineContext) -> str:
    result = generate_dataset(context.resolved_config(), write=True)
    counts = result.row_counts()
    return (
        f"{counts['customers']:,} customers, {counts['products']:,} products, "
        f"{counts['orders']:,} orders, {counts['order_items']:,} lines"
    )


def _step_verify_artifacts(context: PipelineContext) -> str:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(
            f"generation manifest not found at {MANIFEST_PATH}; run the generate step first"
        )
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = manifest.get("file_checksums_sha256", {})
    if not expected:
        raise ValueError("generation manifest does not contain file checksums")
    mismatches = [
        name
        for name in sorted(TABLES)
        if expected.get(name) != sha256_file(RAW_DATA_DIR / TABLES[name].csv_name)
    ]
    if mismatches:
        raise ValueError(
            "generated CSV file(s) do not match the manifest: " + ", ".join(mismatches)
        )
    return f"{len(TABLES)} CSV files match the generation manifest"


def ensure_database(
    settings: DatabaseSettings, *, timeout_seconds: int = DATABASE_START_TIMEOUT_SECONDS
) -> str:
    """Return a status string, starting PostgreSQL with docker compose if needed."""

    def reachable() -> bool:
        try:
            with psycopg.connect(settings.conninfo, connect_timeout=3) as connection:
                connection.execute("SELECT 1")
            return True
        except psycopg.OperationalError:
            return False

    if reachable():
        return f"PostgreSQL already reachable at {settings.host}:{settings.port}"

    logger.info("PostgreSQL is not reachable; starting it with docker compose")
    try:
        completed = subprocess.run(
            ["docker", "compose", "up", "-d"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:  # docker is not installed
        raise RuntimeError(
            "PostgreSQL is not reachable and docker is not available on PATH"
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"docker compose up -d failed: {(completed.stderr or completed.stdout).strip()[-400:]}"
        )

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if reachable():
            return f"started PostgreSQL with docker compose at {settings.host}:{settings.port}"
        time.sleep(2)
    raise RuntimeError(f"PostgreSQL did not become ready within {timeout_seconds} seconds")


def _step_postgres(context: PipelineContext) -> str:
    return ensure_database(context.resolved_settings())


def _step_load_raw(context: PipelineContext) -> str:
    report = load_raw_tables(context.resolved_settings())
    return f"{report.total_rows:,} rows loaded in {report.duration_seconds:.1f}s"


def _step_raw_checks(context: PipelineContext) -> str:
    rows = run_raw_data_checks(context.resolved_settings())
    failures = failing_checks(rows)
    if failures:
        detail = ", ".join(f"{row['check_id']} ({row['failing_rows']})" for row in failures)
        raise ValueError(f"{len(failures)} raw data-quality check(s) failed: {detail}")
    return f"{len(rows)} raw data-quality checks passed"


def _step_analytics_layer(context: PipelineContext) -> str:
    settings = context.resolved_settings()
    applied = build_analytics_layer(settings)
    views = list_analytical_views(settings)
    return (
        f"{sum(applied.values())} SQL statements applied across {len(applied)} files, "
        f"{sum(len(names) for names in views.values())} views available"
    )


def _step_reconciliation_checks(context: PipelineContext) -> str:
    rows = fetch_reconciliation(context.resolved_settings())
    failures = [row for row in rows if not row["passed"]]
    if failures:
        detail = ", ".join(str(row["check_id"]) for row in failures)
        raise ValueError(f"{len(failures)} analytical reconciliation check(s) failed: {detail}")
    return f"{len(rows)} analytical reconciliation checks passed"


def _step_analytics(context: PipelineContext) -> str:
    context.inputs = load_analysis_inputs(context.resolved_settings())
    context.analysis = build_business_analysis(inputs=context.inputs)
    kpi = context.analysis.kpis.iloc[0]
    return (
        f"{format_compact_currency(kpi['total_revenue'])} revenue, "
        f"{format_count(kpi['total_orders'])} orders, "
        f"{len(context.analysis.tables)} tables, {len(context.analysis.figures)} figures"
    )


def _step_dashboard(context: PipelineContext) -> str:
    result = build_dashboard_outputs(
        inputs=context.inputs,
        analysis=context.analysis,
        output_dir=context.exports_dir,
    )
    exports = result["exports"]
    return (
        f"{len(exports.frames) - 1} datasets exported, "
        f"{len(result['previews'])} page previews, "
        f"{len(result['summary_paths'])} summary files"
    )


def _step_end_to_end(context: PipelineContext) -> str:
    reconciliation = build_end_to_end_reconciliation(
        settings=context.resolved_settings(), exports_dir=context.exports_dir
    )
    summary = reconciliation.summary
    if not reconciliation.ok:
        detail = ", ".join(str(metric) for metric in summary["failed_metrics"])
        raise ValueError(f"end-to-end reconciliation failed for: {detail}")
    return (
        f"{summary['metrics']} metrics compared across raw, analytical and exported layers, "
        "0 differences"
    )


def _step_portfolio(context: PipelineContext) -> str:
    from novacart.portfolio import build_portfolio_assets

    paths = build_portfolio_assets(
        inputs=context.inputs, analysis=context.analysis, exports_dir=context.exports_dir
    )
    return f"{len(paths['images'])} portfolio images and {len(paths['samples'])} sample outputs"


def _step_tests(context: PipelineContext) -> str:
    completed = subprocess.run(
        ["python", "-m", "pytest", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        tail = (completed.stdout or completed.stderr).strip().splitlines()[-1:]
        raise RuntimeError(f"test suite failed: {' '.join(tail)}")
    last_line = (completed.stdout or "").strip().splitlines()[-1:]
    return last_line[0] if last_line else "tests passed"


def default_steps(include_tests: bool = False) -> tuple[PipelineStep, ...]:
    steps = [
        PipelineStep("generate", "Generate synthetic data", _step_generate),
        PipelineStep("verify_artifacts", "Verify generated artefacts", _step_verify_artifacts),
        PipelineStep("postgres", "Ensure PostgreSQL is running", _step_postgres),
        PipelineStep("load_raw", "Create schemas and load raw data", _step_load_raw),
        PipelineStep("raw_checks", "Run raw data-quality checks", _step_raw_checks),
        PipelineStep("analytics_layer", "Build the analytical SQL layer", _step_analytics_layer),
        PipelineStep(
            "reconciliation_checks",
            "Run analytical reconciliation checks",
            _step_reconciliation_checks,
        ),
        PipelineStep("analytics", "Run the Python analytics", _step_analytics),
        PipelineStep("dashboard", "Export dashboard datasets and summary", _step_dashboard),
        PipelineStep(
            "end_to_end", "Reconcile raw, analytical and exported layers", _step_end_to_end
        ),
        PipelineStep("portfolio", "Build the portfolio assets", _step_portfolio),
    ]
    if include_tests:
        steps.append(PipelineStep("tests", "Run the test suite", _step_tests))
    return tuple(steps)


def run_pipeline(
    steps: Sequence[PipelineStep] | None = None,
    *,
    context: PipelineContext | None = None,
    include_tests: bool = False,
) -> PipelineReport:
    """Run the steps in order, stopping at the first failure."""
    context = context or PipelineContext(run_tests=include_tests)
    steps = tuple(steps) if steps is not None else default_steps(include_tests)
    report = PipelineReport()

    for step in steps:
        started = time.monotonic()
        logger.info("Step %d/%d - %s", len(report.steps) + 1, len(steps), step.title)
        try:
            summary = step.run(context)
        except Exception as exc:
            report.ok = False
            raise PipelineError(step.key, step.title, exc) from exc
        elapsed = time.monotonic() - started
        report.steps.append(StepResult(step.key, step.title, summary, elapsed))
        context.completed.append(step.key)
        logger.info("  %s (%.1fs)", summary, elapsed)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="novacart-pipeline",
        description="Run the complete NovaCart pipeline from synthetic data to portfolio assets.",
    )
    parser.add_argument("--with-tests", action="store_true", help="Run pytest as the final step")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--list", action="store_true", help="List the steps and exit")
    args = parser.parse_args(argv)
    configure_logging(logging.WARNING if args.quiet else logging.INFO)

    steps = default_steps(args.with_tests)
    if args.list:
        for index, step in enumerate(steps, start=1):
            print(f"{index:>2}. {step.key:<22} {step.title}")
        return 0

    try:
        report = run_pipeline(steps=steps, include_tests=args.with_tests)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}")
        return 2
    except PipelineError as exc:
        print(f"Pipeline failed at {exc.step_key}: {exc.cause}")
        print(f"  step: {exc.step_title}")
        return 1

    print()
    print(f"{'step':<24}{'seconds':>9}  summary")
    for result in report.steps:
        print(f"{result.key:<24}{result.seconds:>9.1f}  {result.summary}")
    print()
    print(f"Pipeline completed: {len(report.steps)} steps, all checks passed")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

