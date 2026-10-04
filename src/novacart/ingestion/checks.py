"""Raw-layer data-quality checks, shared by the CLI script and the pipeline."""

from __future__ import annotations

import logging

from psycopg.rows import dict_row

from novacart.db import connect, split_sql_statements
from novacart.settings import SQL_DIR, DatabaseSettings

logger = logging.getLogger(__name__)

CHECKS_FILE = SQL_DIR / "checks" / "verify_raw.sql"


def _checks_statement() -> str:
    script = CHECKS_FILE.read_text(encoding="utf-8")
    return next(statement for statement in split_sql_statements(script) if statement)


def run_raw_data_checks(
    settings: DatabaseSettings, *, persist: bool = True
) -> list[dict[str, object]]:
    """Run ``sql/checks/verify_raw.sql`` and return one dict per check.

    Each dict has ``check_id``, ``description``, ``failing_rows`` and ``result``.
    When ``persist`` is true the outcome is also stored in
    ``meta.data_quality_result``.
    """
    statement = _checks_statement()
    with connect(settings) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(statement)
            rows = [dict(row) for row in cursor.fetchall()]

        if persist:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM meta.data_quality_result")
                for row in rows:
                    cursor.execute(
                        """
                        INSERT INTO meta.data_quality_result
                            (check_id, check_group, description, passed, failing_rows, executed_at)
                        VALUES (%s, %s, %s, %s, %s, now())
                        """,
                        (
                            row["check_id"],
                            "raw",
                            row["description"],
                            int(row["failing_rows"]) == 0,
                            int(row["failing_rows"]),
                        ),
                    )
    logger.debug("Ran %d raw data-quality checks", len(rows))
    return rows


def failing_checks(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if int(row["failing_rows"]) != 0]

