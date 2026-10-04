"""Data access and shared metric helpers for the Python analytical layer.

The Python layer never rebuilds revenue from raw columns. It reads the published
SQL facts and marts from Milestone 2 and applies descriptive analysis on top:

    analytics.fct_orders               order grain, recognised_net_revenue
    analytics.fct_order_lines          line grain, recognised_line_net_revenue
    analytics.mart_customer_features   customer grain (includes non-purchasers)
    analytics.mart_product_performance
    analytics.mart_category_performance
    analytics.mart_revenue_daily / analytics.mart_revenue_monthly
    analytics.analysis_window          reporting window / as-of date

Every calculation elsewhere in the package is a pure function over DataFrames so
it can be tested with small hand-built frames. The fallbacks below exist for that
reason: a frame without ``is_revenue_recognised`` is treated as fully recognised,
and ``net_revenue``/``total_units`` are accepted when the ``recognised_*`` columns
are absent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from novacart.db import build_engine
from novacart.settings import OUTPUT_DIR, DatabaseSettings, load_database_settings

logger = logging.getLogger(__name__)

#: Canonical column names published by the analytical SQL layer.
ORDER_REVENUE_COLUMN = "recognised_net_revenue"
LINE_REVENUE_COLUMN = "recognised_line_net_revenue"
ORDER_UNITS_COLUMN = "recognised_units"
RECOGNITION_FLAG = "is_revenue_recognised"

FIGURES_DIR = OUTPUT_DIR / "figures"
TABLES_DIR = OUTPUT_DIR / "tables"

ALLOWED_RELATIONS: frozenset[str] = frozenset(
    {
        "analytics.fct_orders",
        "analytics.fct_order_lines",
        "analytics.mart_customer_features",
        "analytics.mart_product_performance",
        "analytics.mart_category_performance",
        "analytics.mart_revenue_daily",
        "analytics.mart_revenue_monthly",
        "analytics.analysis_window",
    }
)

#: Date/timestamp columns per relation. PostgreSQL DATE values arrive as Python
#: ``date`` objects, so they are converted explicitly for deterministic dtypes.
DATE_COLUMNS: dict[str, tuple[str, ...]] = {
    "analytics.fct_orders": ("order_ts", "order_date", "order_month", "customer_signup_date"),
    "analytics.fct_order_lines": ("order_ts", "order_date", "order_month"),
    "analytics.mart_customer_features": (
        "signup_date",
        "first_order_date",
        "last_order_date",
        "analysis_end_date",
    ),
    "analytics.mart_product_performance": ("launch_date", "first_sold_date", "last_sold_date"),
    "analytics.mart_category_performance": (),
    "analytics.mart_revenue_daily": ("date_key",),
    "analytics.mart_revenue_monthly": ("month_start",),
    "analytics.analysis_window": ("first_order_date", "analysis_end_date"),
}


class AnalyticsError(RuntimeError):
    """Raised when the analytics layer is asked for something it cannot compute."""


@dataclass(frozen=True)
class AnalysisInputs:
    """Everything the business analysis needs, loaded in one pass."""

    orders: pd.DataFrame
    order_lines: pd.DataFrame
    customers: pd.DataFrame
    products: pd.DataFrame
    categories: pd.DataFrame
    daily: pd.DataFrame
    monthly: pd.DataFrame
    window: pd.DataFrame


# ---------------------------------------------------------------------------
# data access
# ---------------------------------------------------------------------------
def load_relation(
    relation: str, *, settings: DatabaseSettings | None = None
) -> pd.DataFrame:
    """Load a published analytical relation into a DataFrame.

    ``SELECT *`` is intentional here: the analytical views are the schema
    contract, and this loader is the single generic entry point to them. The
    relation name is validated against an allow list.
    """
    if relation not in ALLOWED_RELATIONS:
        raise AnalyticsError(
            f"Unknown analytical relation {relation!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_RELATIONS))}"
        )
    engine = build_engine(settings or load_database_settings())
    with engine.connect() as connection:
        frame = pd.read_sql(f"SELECT * FROM {relation}", connection)

    for column in DATE_COLUMNS[relation]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="raise")
    logger.debug("Loaded %s rows from %s", f"{len(frame):,}", relation)
    return frame


def load_analysis_inputs(settings: DatabaseSettings | None = None) -> AnalysisInputs:
    """Load every relation used by the business analysis."""
    return AnalysisInputs(
        orders=load_relation("analytics.fct_orders", settings=settings),
        order_lines=load_relation("analytics.fct_order_lines", settings=settings),
        customers=load_relation("analytics.mart_customer_features", settings=settings),
        products=load_relation("analytics.mart_product_performance", settings=settings),
        categories=load_relation("analytics.mart_category_performance", settings=settings),
        daily=load_relation("analytics.mart_revenue_daily", settings=settings),
        monthly=load_relation("analytics.mart_revenue_monthly", settings=settings),
        window=load_relation("analytics.analysis_window", settings=settings),
    )


# ---------------------------------------------------------------------------
# frame helpers
# ---------------------------------------------------------------------------
def require_columns(frame: pd.DataFrame, columns: tuple[str, ...], purpose: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise AnalyticsError(f"{purpose} requires column(s) {missing}; got {list(frame.columns)}")


def resolve_column(frame: pd.DataFrame, candidates: tuple[str, ...], purpose: str) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    raise AnalyticsError(f"{purpose} requires one of {candidates}; got {list(frame.columns)}")


def recognised(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep revenue-recognised rows (completed orders).

    Frames without the recognition flag are treated as fully recognised, which is
    what the unit-test fixtures rely on.
    """
    if RECOGNITION_FLAG not in frame.columns:
        return frame.copy()
    flag = frame[RECOGNITION_FLAG].fillna(False).astype(bool)
    return frame.loc[flag].copy()


def revenue_column(frame: pd.DataFrame, grain: str) -> str:
    """Return the canonical revenue column for an order or line frame."""
    candidates = (
        (ORDER_REVENUE_COLUMN, "net_revenue")
        if grain == "order"
        else (LINE_REVENUE_COLUMN, "line_net_revenue")
    )
    return resolve_column(frame, candidates, f"{grain}-grain revenue")


def units_column(frame: pd.DataFrame, grain: str) -> str:
    candidates = (
        (ORDER_UNITS_COLUMN, "total_units") if grain == "order" else ("recognised_units", "quantity")
    )
    return resolve_column(frame, candidates, f"{grain}-grain units")


def empty_frame(columns: dict[str, str] | list[str]) -> pd.DataFrame:
    """Build a typed empty frame so downstream formatting never fails."""
    if isinstance(columns, dict):
        return pd.DataFrame({name: pd.Series(dtype=dtype) for name, dtype in columns.items()})
    return pd.DataFrame({name: pd.Series(dtype="float64") for name in columns})


# ---------------------------------------------------------------------------
# metric helpers
# ---------------------------------------------------------------------------
def safe_divide(numerator: Any, denominator: Any) -> Any:
    """Divide, returning NaN where the denominator is zero or missing.

    Accepts scalars and array-likes; returns a float for scalar input and a NumPy
    array otherwise.
    """
    numerator_array = np.asarray(numerator, dtype="float64")
    denominator_array = np.asarray(denominator, dtype="float64")
    shape = np.broadcast_shapes(numerator_array.shape, denominator_array.shape)
    result = np.full(shape, np.nan, dtype="float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        np.divide(numerator_array, denominator_array, out=result, where=denominator_array != 0)
    return float(result) if result.ndim == 0 else result


def percentage_change(current: Any, previous: Any) -> Any:
    """Relative change ``(current - previous) / |previous|``.

    Returns NaN when the previous value is zero or missing, so a new month from a
    zero base is reported as "n/a" rather than as an infinite growth rate.
    """
    current_array = np.asarray(current, dtype="float64")
    previous_array = np.asarray(previous, dtype="float64")
    change = current_array - previous_array
    return safe_divide(change, np.abs(previous_array))


def rolling_sum(series: pd.Series, window: int, *, min_periods: int = 1) -> pd.Series:
    """Trailing rolling sum, matching the SQL ``ROWS BETWEEN n PRECEDING`` windows."""
    if window <= 0:
        raise AnalyticsError("rolling window must be positive")
    return series.astype("float64").rolling(window=window, min_periods=min_periods).sum()


def to_date(value: Any) -> pd.Timestamp:
    """Normalise any date-like value to a midnight Timestamp (deterministic)."""
    return pd.Timestamp(pd.to_datetime(value)).normalize()


# ---------------------------------------------------------------------------
# formatting helpers (used by the report, the notebook and the console)
# ---------------------------------------------------------------------------
def format_currency(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"EUR {float(value):,.2f}"


def format_compact_currency(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"EUR {value / 1_000_000:,.2f}m"
    if abs(value) >= 1_000:
        return f"EUR {value / 1_000:,.2f}k"
    return f"EUR {value:,.2f}"


def format_count(value: Any) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{int(value):,}"


def format_percent(value: Any, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value) * 100:.{decimals}f}%"


def ensure_output_dirs(base: Path | None = None) -> tuple[Path, Path]:
    """Create and return the (figures, tables) output directories."""
    figures = (base / "figures") if base else FIGURES_DIR
    tables = (base / "tables") if base else TABLES_DIR
    figures.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    return figures, tables

