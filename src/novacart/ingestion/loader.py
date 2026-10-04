"""Raw-layer loading: apply the schema, COPY the CSVs, and record the run."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from novacart.db import (
    apply_sql_files,
    connect,
    copy_csv,
    table_row_counts,
    truncate_tables,
)
from novacart.settings import (
    GENERATION_METADATA_DIR,
    RAW_DATA_DIR,
    SQL_DIR,
    DatabaseSettings,
)
from novacart.synthetic.models import DELETE_ORDER, LOAD_ORDER, TABLES
from novacart.synthetic.writer import sha256_file

logger = logging.getLogger(__name__)

DDL_FILES: tuple[Path, ...] = (
    SQL_DIR / "01_schemas.sql",
    SQL_DIR / "02_raw_tables.sql",
)
MANIFEST_PATH = GENERATION_METADATA_DIR / "generation_manifest.json"


@dataclass
class LoadReport:
    rows_loaded: dict[str, int] = field(default_factory=dict)
    source_checksums: dict[str, str] = field(default_factory=dict)
    run_id: int | None = None
    duration_seconds: float = 0.0
    database_counts: dict[str, int] = field(default_factory=dict)

    @property
    def total_rows(self) -> int:
        return sum(self.rows_loaded.values())


def ensure_schema(settings: DatabaseSettings, ddl_files: tuple[Path, ...] = DDL_FILES) -> None:
    with connect(settings) as connection:
        apply_sql_files(connection, ddl_files)
    logger.info("Applied schema from %s", ", ".join(path.name for path in ddl_files))


def _load_manifest(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Generation manifest at %s is not valid JSON; ignoring it", path)
        return {}


def load_raw_tables(
    settings: DatabaseSettings,
    *,
    data_dir: Path = RAW_DATA_DIR,
    manifest_path: Path = MANIFEST_PATH,
    truncate: bool = True,
    apply_ddl: bool = True,
    record_run: bool = True,
) -> LoadReport:
    started = datetime.now(UTC)
    report = LoadReport()

    if apply_ddl:
        ensure_schema(settings)

    missing = [key for key in LOAD_ORDER if not (data_dir / TABLES[key].csv_name).is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing generated files: "
            + ", ".join(TABLES[key].csv_name for key in missing)
            + f". Run scripts/generate_data.py first (looked in {data_dir})."
        )

    manifest = _load_manifest(manifest_path)

    with connect(settings) as connection:
        if truncate:
            truncate_tables(connection, [TABLES[key].qualified_name for key in DELETE_ORDER])

        for key in LOAD_ORDER:
            spec = TABLES[key]
            csv_path = data_dir / spec.csv_name
            rows = copy_csv(connection, spec.qualified_name, csv_path, spec.columns)
            report.rows_loaded[key] = rows
            report.source_checksums[key] = sha256_file(csv_path)
            logger.info("Loaded %8d rows into %s", rows, spec.qualified_name)

        report.database_counts = dict(
            table_row_counts(connection, "raw", [TABLES[key].name for key in LOAD_ORDER])
        )

        if record_run:
            finished = datetime.now(UTC)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO meta.ingestion_run
                        (started_at, finished_at, status, generator_seed, rows_loaded,
                         source_checksums, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING run_id
                    """,
                    (
                        started,
                        finished,
                        "success",
                        manifest.get("seed"),
                        json.dumps(report.rows_loaded),
                        json.dumps(report.source_checksums),
                        f"loaded from {data_dir}",
                    ),
                )
                row = cursor.fetchone()
                report.run_id = int(row[0]) if row else None

    report.duration_seconds = (datetime.now(UTC) - started).total_seconds()
    return report

