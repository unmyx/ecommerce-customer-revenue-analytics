"""Command line entry point: ``novacart-generate``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from novacart.logging_config import configure_logging
from novacart.settings import GENERATION_METADATA_DIR, RAW_DATA_DIR
from novacart.synthetic.config import GenerationConfig, GenerationConfigError
from novacart.synthetic.generator import generate_dataset
from novacart.synthetic.validation import DataValidationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novacart-generate",
        description="Generate the synthetic NovaCart e-commerce dataset.",
    )
    parser.add_argument("--seed", type=int, help="Random seed (defaults to NOVACART_SEED)")
    parser.add_argument("--customers", type=int, help="Number of customers to generate")
    parser.add_argument("--products", type=int, help="Number of products to generate")
    parser.add_argument("--campaigns", type=int, help="Number of marketing campaigns")
    parser.add_argument("--orders", type=int, dest="target_orders", help="Baseline order target")
    parser.add_argument("--output-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument("--metadata-dir", type=Path, default=GENERATION_METADATA_DIR)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Generate and validate in memory without writing files",
    )
    parser.add_argument("--quiet", action="store_true", help="Only log warnings and errors")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(logging.WARNING if args.quiet else logging.INFO)

    try:
        config = GenerationConfig.from_env().with_overrides(
            seed=args.seed,
            n_customers=args.customers,
            n_products=args.products,
            n_campaigns=args.campaigns,
            target_orders=args.target_orders,
        )
    except GenerationConfigError as exc:
        print(f"Invalid generation configuration: {exc}", file=sys.stderr)
        return 2

    try:
        result = generate_dataset(
            config,
            write=not args.no_write,
            output_dir=args.output_dir,
            metadata_dir=args.metadata_dir,
        )
    except DataValidationError as exc:
        print(str(exc), file=sys.stderr)
        for issue in exc.report.errors:
            print(f"  - {issue.check_id}: {issue.description} ({issue.failing_rows} rows)", file=sys.stderr)
        return 1

    print(f"Seed                : {config.seed}")
    print(f"Analysis window     : {config.start_date} .. {config.end_date}")
    for table, count in result.row_counts().items():
        print(f"{table:<20}: {count:>9,}")
    print(f"Net revenue         : EUR {result.diagnostics['net_revenue_total']:>14,.2f}")
    print(f"Average order value : EUR {result.diagnostics['average_order_value']:>14,.2f}")
    print(f"Repeat purchase rate: {result.diagnostics['repeat_purchase_rate']:.1%}")
    if result.validation is not None:
        summary = result.validation.summary()
        print(f"Validation          : {summary['checks']} checks, {summary['failures']} failures")
    if result.manifest_path is not None:
        print(f"Manifest            : {result.manifest_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

