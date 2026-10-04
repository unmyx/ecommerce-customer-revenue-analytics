"""Run the SQL data-quality checks in sql/checks/verify_raw.sql."""

from __future__ import annotations

import argparse
import sys

from novacart.db import connect, split_sql_statements
from novacart.logging_config import configure_logging
from novacart.settings import SQL_DIR, ConfigurationError, load_database_settings

CHECKS_FILE = SQL_DIR / "checks" / "verify_raw.sql"


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

    statement = next(
        statement
        for statement in split_sql_statements(CHECKS_FILE.read_text(encoding="utf-8"))
        if statement
    )

    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement)
            rows = cursor.fetchall()

        if not args.no_persist:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM meta.data_quality_result")
                for check_id, description, failing_rows, _ in rows:
                    cursor.execute(
                        """
                        INSERT INTO meta.data_quality_result
                            (check_id, check_group, description, passed, failing_rows, executed_at)
                        VALUES (%s, %s, %s, %s, %s, now())
                        """,
                        (check_id, "raw", description, int(failing_rows) == 0, int(failing_rows)),
                    )

    print(f"{'check_id':<38}{'result':<8}failing_rows")
    failures = 0
    for check_id, description, failing_rows, result in rows:
        if failing_rows:
            failures += 1
        print(f"{check_id:<38}{result:<8}{failing_rows}")
    print()
    print(f"{len(rows)} checks executed, {failures} failing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

