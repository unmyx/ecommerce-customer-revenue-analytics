"""PostgreSQL helpers shared by ingestion, analysis and tests."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg import Connection
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from novacart.settings import DatabaseSettings

logger = logging.getLogger(__name__)


def build_engine(settings: DatabaseSettings, *, echo: bool = False) -> Engine:
    """SQLAlchemy engine used by the analytical layer."""
    return create_engine(settings.url, echo=echo, pool_pre_ping=True)


@contextmanager
def connect(settings: DatabaseSettings) -> Iterator[Connection]:
    """Transactional psycopg connection; commits on success, rolls back on error."""
    connection = psycopg.connect(settings.conninfo)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def split_sql_statements(script: str) -> list[str]:
    """Split a SQL script into executable statements.

    Handles line comments, single-quoted literals (including doubled quotes) and
    dollar-quoted blocks, so statements can be executed and logged one by one
    while keeping the .sql files readable as plain PostgreSQL scripts.
    """
    statements: list[str] = []
    buffer: list[str] = []
    index = 0
    length = len(script)

    while index < length:
        char = script[index]

        if char == "-" and script.startswith("--", index):
            newline = script.find("\n", index)
            index = length if newline == -1 else newline
            continue

        if char == "/" and script.startswith("/*", index):
            end = script.find("*/", index + 2)
            index = length if end == -1 else end + 2
            buffer.append(" ")
            continue

        if char == "'":
            end = index + 1
            while end < length:
                if script[end] == "'":
                    if end + 1 < length and script[end + 1] == "'":
                        end += 2
                        continue
                    break
                end += 1
            buffer.append(script[index : end + 1])
            index = end + 1
            continue

        if char == "$":
            tag_end = script.find("$", index + 1)
            if tag_end != -1:
                tag = script[index : tag_end + 1]
                inner = tag[1:-1]
                is_valid_tag = inner == "" or (
                    (inner[0].isalpha() or inner[0] == "_") and inner.replace("_", "").isalnum()
                )
                if is_valid_tag:
                    end = script.find(tag, tag_end + 1)
                    if end != -1:
                        buffer.append(script[index : end + len(tag)])
                        index = end + len(tag)
                        continue

        if char == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue

        buffer.append(char)
        index += 1

    tail = "".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements


def apply_sql_file(connection: Connection, path: Path) -> int:
    """Execute every statement in a .sql file and return the statement count."""
    script = path.read_text(encoding="utf-8")
    statements = split_sql_statements(script)
    for statement in statements:
        connection.execute(statement)
    logger.debug("Applied %s (%d statements)", path.name, len(statements))
    return len(statements)


def apply_sql_files(connection: Connection, paths: Iterable[Path]) -> dict[str, int]:
    applied: dict[str, int] = {}
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"SQL file not found: {path}")
        applied[path.name] = apply_sql_file(connection, path)
    return applied


def truncate_tables(connection: Connection, tables: Sequence[str]) -> None:
    """Empty the given tables (and anything depending on them) in one transaction."""
    if not tables:
        return
    connection.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")


def copy_csv(connection: Connection, table: str, csv_path: Path, columns: Sequence[str]) -> int:
    """Bulk load a CSV file with COPY and return the number of rows sent."""
    column_list = ", ".join(columns)
    statement = (
        f"COPY {table} ({column_list}) FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')"
    )
    rows = 0
    with csv_path.open("rb") as handle, connection.cursor() as cursor:
        with cursor.copy(statement) as copy:
            while chunk := handle.read(1 << 20):
                copy.write(chunk)
        if cursor.rowcount is not None and cursor.rowcount >= 0:
            rows = int(cursor.rowcount)
    return rows


def table_row_counts(
    connection: Connection, schema: str, tables: Sequence[str]
) -> Mapping[str, int]:
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table in tables:
            cursor.execute(f"SELECT count(*) FROM {schema}.{table}")
            row = cursor.fetchone()
            counts[table] = int(row[0]) if row else 0
    return counts


def server_version(connection: Connection) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SHOW server_version")
        row = cursor.fetchone()
    return str(row[0]) if row else "unknown"

