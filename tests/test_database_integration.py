"""Integration tests against a live PostgreSQL instance.

They are skipped unless ``NOVACART_RUN_DB_TESTS=1`` because they truncate and
reload the ``raw`` schema of the configured database.
"""

from __future__ import annotations

import os

import pytest

from novacart.db import apply_sql_files, connect, split_sql_statements
from novacart.ingestion.loader import load_raw_tables
from novacart.settings import SQL_DIR, ConfigurationError, load_database_settings
from novacart.synthetic.generator import generate_dataset

pytestmark = pytest.mark.integration


def _integration_enabled() -> bool:
    return os.getenv("NOVACART_RUN_DB_TESTS", "").lower() in {"1", "true", "yes"}


def _settings_or_skip():
    if not _integration_enabled():
        pytest.skip("set NOVACART_RUN_DB_TESTS=1 to run database integration tests")
    try:
        return load_database_settings()
    except ConfigurationError as exc:  # pragma: no cover - environment issue
        pytest.skip(f"database configuration unavailable: {exc}")


def test_schema_loads_and_checks_pass(small_config, tmp_path) -> None:
    settings = _settings_or_skip()
    result = generate_dataset(small_config, write=True, output_dir=tmp_path / "raw")
    report = load_raw_tables(settings, data_dir=tmp_path / "raw", truncate=True)

    assert report.rows_loaded["customers"] == small_config.n_customers
    assert report.rows_loaded["orders"] == len(result.frames["orders"])
    assert report.database_counts["payments"] == report.database_counts["orders"]

    checks_file = SQL_DIR / "checks" / "verify_raw.sql"
    statement = next(
        statement
        for statement in split_sql_statements(checks_file.read_text(encoding="utf-8"))
        if statement
    )
    with connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute(statement)
        rows = cursor.fetchall()
    failures = [(row[0], row[2]) for row in rows if row[2]]
    assert failures == []


def test_ddl_is_idempotent() -> None:
    settings = _settings_or_skip()
    with connect(settings) as connection:
        apply_sql_files(
            connection,
            (SQL_DIR / "01_schemas.sql", SQL_DIR / "02_raw_tables.sql"),
        )

