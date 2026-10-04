"""Command line entry point: ``novacart-load``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from novacart.ingestion.loader import load_raw_tables
from novacart.logging_config import configure_logging
from novacart.settings import RAW_DATA_DIR, ConfigurationError, load_database_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novacart-load",
        description="Load the generated CSV files into the PostgreSQL raw schema.",
    )
    parser.add_argument("--data-dir", type=Path, default=RAW_DATA_DIR)
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not truncate the raw tables before loading",
    )
    parser.add_argument(
        "--skip-ddl",
        action="store_true",
        help="Skip applying sql/01_schemas.sql and sql/02_raw_tables.sql",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(logging.WARNING if args.quiet else logging.INFO)

    try:
        settings = load_database_settings()
        report = load_raw_tables(
            settings,
            data_dir=args.data_dir,
            truncate=not args.keep_existing,
            apply_ddl=not args.skip_ddl,
        )
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator
        print(f"Load failed: {exc}", file=sys.stderr)
        return 1

    for table, count in report.rows_loaded.items():
        print(f"{table:<20}: {count:>9,} rows")
    print(f"Total rows          : {report.total_rows:>9,}")
    print(f"Duration            : {report.duration_seconds:.1f}s")
    if report.run_id is not None:
        print(f"Ingestion run id    : {report.run_id}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

