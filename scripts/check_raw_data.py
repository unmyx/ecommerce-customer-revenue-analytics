"""Run the SQL data-quality checks in sql/checks/verify_raw.sql."""

from __future__ import annotations

import argparse
import sys

from novacart.ingestion.checks import run_raw_data_checks
from novacart.logging_config import configure_logging
from novacart.settings import ConfigurationError, load_database_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run raw-layer data-quality checks.")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write the results into meta.data_quality_result",
    )
    args = parser.parse_args(argv)
    configure_logging()

    try:
        settings = load_database_settings()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    rows = run_raw_data_checks(settings, persist=not args.no_persist)

    print(f"{'check_id':<38}{'result':<8}failing_rows")
    failures = 0
    for row in rows:
        if int(row["failing_rows"]):
            failures += 1
        print(f"{row['check_id']:<38}{row['result']:<8}{row['failing_rows']}")
    print()
    print(f"{len(rows)} checks executed, {failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

