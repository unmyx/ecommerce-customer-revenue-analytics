"""Environment-driven configuration shared by every stage of the project."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = PROJECT_ROOT / "sql"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
GENERATION_METADATA_DIR = PROJECT_ROOT / "data" / "generation_metadata"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

load_dotenv(PROJECT_ROOT / ".env")


class ConfigurationError(RuntimeError):
    """Raised when the environment is missing or contains invalid configuration."""


def _required(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ConfigurationError(
            f"Missing required environment variable {name!r}. "
            f"Copy .env.example to .env and fill in the values."
        )
    return value.strip()


def _optional_date(name: str, default: date | None) -> date | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise ConfigurationError(f"{name!r} must be an ISO date (YYYY-MM-DD), got {raw!r}") from exc


@dataclass(frozen=True)
class DatabaseSettings:
    """Connection details for the local PostgreSQL instance."""

    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def url(self) -> URL:
        """SQLAlchemy URL (handles escaping of special characters)."""
        return URL.create(
            "postgresql+psycopg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )

    @property
    def conninfo(self) -> str:
        """libpq connection string used by psycopg for bulk COPY operations."""
        from psycopg.conninfo import make_conninfo

        return make_conninfo(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
        )


def load_database_settings() -> DatabaseSettings:
    try:
        port = int(_required("POSTGRES_PORT"))
    except ValueError as exc:
        raise ConfigurationError("POSTGRES_PORT must be an integer") from exc

    return DatabaseSettings(
        host=_required("POSTGRES_HOST"),
        port=port,
        database=_required("POSTGRES_DB"),
        user=_required("POSTGRES_USER"),
        password=_required("POSTGRES_PASSWORD"),
    )


def analysis_window() -> tuple[date | None, date | None]:
    """Declared analysis window; also used to sanity-check generated data."""
    return (
        _optional_date("NOVACART_START_DATE", None),
        _optional_date("NOVACART_END_DATE", None),
    )

