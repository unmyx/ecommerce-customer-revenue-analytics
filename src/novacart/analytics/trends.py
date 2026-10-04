"""Daily, weekly and monthly revenue time series (Milestone 3, part B).

Date handling is explicit and deterministic:

* every series is derived from ``order_date`` (a date, not a timestamp);
* daily metrics are reindexed onto a complete calendar, so a day without orders
  contributes zero instead of disappearing - this keeps 7/30-day rolling windows
  correct (the same reasoning as ``analytics.mart_revenue_daily``);
* weeks start on Monday and are labelled with the ISO year-week of that Monday;
* months are calendar months labelled ``YYYY-MM``;
* rolling windows are trailing sums that include the current period and use
  ``min_periods = 1``, matching the SQL marts;
* month-over-month percentage changes return NaN when the previous month is zero
  or missing rather than an infinite growth rate.
"""

from __future__ import annotations

import pandas as pd

from novacart.analytics.common import (
    ORDER_REVENUE_COLUMN,
    ORDER_UNITS_COLUMN,
    AnalyticsError,
    empty_frame,
    percentage_change,
    recognised,
    require_columns,
    resolve_column,
    rolling_sum,
    safe_divide,
)

METRIC_COLUMNS = (
    "orders_recognised",
    "purchasing_customers",
    "units",
    "revenue",
    "average_order_value",
    "average_units_per_order",
)

DAILY_COLUMNS = (
    "order_date",
    "year",
    "month",
    "year_month",
    "iso_year_week",
    "day_name",
    "is_weekend",
) + METRIC_COLUMNS

WEEKLY_COLUMNS = ("week_start", "iso_year_week", "year", "month") + METRIC_COLUMNS

MONTHLY_COLUMNS = ("month_start", "year_month", "year", "quarter", "month", "month_name") + (
    METRIC_COLUMNS
)

ROLLING_WINDOWS = (7, 30)
MOM_METRICS = ("revenue", "orders_recognised", "average_order_value")


def _prepare(orders: pd.DataFrame, purpose: str) -> pd.DataFrame:
    require_columns(orders, ("customer_id", "order_date"), purpose)
    frame = recognised(orders).copy()
    if not frame.empty:
        frame["order_date"] = pd.to_datetime(frame["order_date"]).dt.normalize()
    return frame


def _order_bounds(orders: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    """First and last order date including non-recognised orders.

    The calendar must span the whole loaded period, not just the periods that
    happen to contain recognised revenue, otherwise a month or week that only
    contains refunds would silently disappear from the series.
    """
    dates = pd.to_datetime(orders["order_date"])
    return dates.min().normalize(), dates.max().normalize()


def _empty_aggregate(keys: list[str]) -> pd.DataFrame:
    return empty_frame(keys + list(METRIC_COLUMNS))


def _aggregate(frame: pd.DataFrame, keys: list[str], purpose: str) -> pd.DataFrame:
    if frame.empty:
        return _empty_aggregate(keys)
    revenue_col = resolve_column(frame, (ORDER_REVENUE_COLUMN, "net_revenue"), purpose)
    units_col = resolve_column(frame, (ORDER_UNITS_COLUMN, "total_units"), purpose)

    if "order_id" in frame.columns:
        order_counts = (
            frame.groupby(keys, as_index=False)["order_id"]
            .nunique()
            .rename(columns={"order_id": "orders_recognised"})
        )
    else:
        order_counts = (
            frame.groupby(keys, as_index=False)
            .size()
            .rename(columns={"size": "orders_recognised"})
        )

    customer_counts = (
        frame.groupby(keys, as_index=False)["customer_id"]
        .nunique()
        .rename(columns={"customer_id": "purchasing_customers"})
    )
    totals = frame.groupby(keys, as_index=False).agg(
        units=(units_col, "sum"), revenue=(revenue_col, "sum")
    )

    merged = order_counts.merge(customer_counts, on=keys, how="outer")
    merged = merged.merge(totals, on=keys, how="outer")
    merged["units"] = merged["units"].fillna(0).astype("int64")
    merged["revenue"] = merged["revenue"].fillna(0.0).round(2)
    merged["average_order_value"] = safe_divide(
        merged["revenue"], merged["orders_recognised"]
    ).round(2)
    merged["average_units_per_order"] = safe_divide(
        merged["units"], merged["orders_recognised"]
    ).round(2)
    return merged


def _add_calendar_labels(frame: pd.DataFrame, date_column: str) -> pd.DataFrame:
    dates = pd.to_datetime(frame[date_column])
    frame["year"] = dates.dt.year
    frame["month"] = dates.dt.month
    frame["year_month"] = dates.dt.strftime("%Y-%m")
    return frame


def _complete_calendar(
    frame: pd.DataFrame,
    date_column: str,
    frequency: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Reindex a period series onto a gap-free calendar and refill derived metrics."""
    index = pd.date_range(start, end, freq=frequency, name=date_column)
    completed = frame.set_index(date_column).reindex(index).reset_index()
    for count_column in ("orders_recognised", "purchasing_customers", "units"):
        completed[count_column] = completed[count_column].fillna(0).astype("int64")
    completed["revenue"] = completed["revenue"].fillna(0.0).round(2)
    completed["average_order_value"] = safe_divide(
        completed["revenue"], completed["orders_recognised"]
    ).round(2)
    completed["average_units_per_order"] = safe_divide(
        completed["units"], completed["orders_recognised"]
    ).round(2)
    return completed


def daily_metrics(orders: pd.DataFrame, *, complete_calendar: bool = True) -> pd.DataFrame:
    """Daily revenue metrics, optionally reindexed onto a complete day calendar."""
    frame = _prepare(orders, "daily_metrics")
    if frame.empty:
        return empty_frame(DAILY_COLUMNS)

    start, end = _order_bounds(orders)
    daily = _aggregate(frame, ["order_date"], "daily_metrics")

    if complete_calendar:
        daily = _complete_calendar(daily, "order_date", "D", start, end)

    daily = _add_calendar_labels(daily, "order_date")
    daily["iso_year_week"] = pd.to_datetime(daily["order_date"]).dt.strftime("%G-W%V")
    daily["day_name"] = pd.to_datetime(daily["order_date"]).dt.day_name()
    daily["is_weekend"] = pd.to_datetime(daily["order_date"]).dt.weekday >= 5
    return daily[list(DAILY_COLUMNS)].sort_values("order_date").reset_index(drop=True)


def weekly_metrics(orders: pd.DataFrame, *, complete_calendar: bool = True) -> pd.DataFrame:
    """Weekly metrics, grouped on ISO weeks (Monday start)."""
    frame = _prepare(orders, "weekly_metrics")
    if frame.empty:
        return empty_frame(WEEKLY_COLUMNS)

    frame["week_start"] = frame["order_date"] - pd.to_timedelta(
        frame["order_date"].dt.weekday, unit="D"
    )
    weekly = _aggregate(frame, ["week_start"], "weekly_metrics")
    if complete_calendar:
        start, end = _order_bounds(orders)
        weekly = _complete_calendar(
            weekly,
            "week_start",
            "7D",
            start - pd.Timedelta(days=start.weekday()),
            end - pd.Timedelta(days=end.weekday()),
        )
    weekly = _add_calendar_labels(weekly, "week_start")
    weekly["iso_year_week"] = pd.to_datetime(weekly["week_start"]).dt.strftime("%G-W%V")
    return weekly[list(WEEKLY_COLUMNS)].sort_values("week_start").reset_index(drop=True)


def monthly_metrics(orders: pd.DataFrame, *, complete_calendar: bool = True) -> pd.DataFrame:
    """Monthly metrics on calendar months.

    The calendar is completed by default so month-over-month comparisons always
    look at the immediately preceding month, even if it had no recognised orders.
    """
    frame = _prepare(orders, "monthly_metrics")
    if frame.empty:
        return empty_frame(MONTHLY_COLUMNS)

    frame["month_start"] = (
        frame["order_date"].dt.to_period("M").dt.start_time.dt.normalize()
    )
    monthly = _aggregate(frame, ["month_start"], "monthly_metrics")
    if complete_calendar:
        start, end = _order_bounds(orders)
        monthly = _complete_calendar(
            monthly, "month_start", "MS", start.replace(day=1), end.replace(day=1)
        )
    dates = pd.to_datetime(monthly["month_start"])
    monthly["year"] = dates.dt.year
    monthly["quarter"] = dates.dt.quarter
    monthly["month"] = dates.dt.month
    monthly["month_name"] = dates.dt.month_name()
    monthly["year_month"] = dates.dt.strftime("%Y-%m")
    return monthly[list(MONTHLY_COLUMNS)].sort_values("month_start").reset_index(drop=True)


def add_rolling_metrics(
    daily: pd.DataFrame, windows: tuple[int, ...] = ROLLING_WINDOWS
) -> pd.DataFrame:
    """Add trailing rolling revenue and order sums to a daily metrics frame."""
    require_columns(daily, ("order_date", "revenue", "orders_recognised"), "add_rolling_metrics")
    frame = daily.sort_values("order_date").reset_index(drop=True).copy()
    for window in windows:
        if window <= 0:
            raise AnalyticsError("rolling window must be positive")
        frame[f"revenue_rolling_{window}d"] = rolling_sum(frame["revenue"], window).round(2)
        frame[f"orders_rolling_{window}d"] = (
            rolling_sum(frame["orders_recognised"], window).round(0).astype("int64")
        )
    return frame


def add_month_over_month(
    monthly: pd.DataFrame, metrics: tuple[str, ...] = MOM_METRICS
) -> pd.DataFrame:
    """Add absolute and percentage month-over-month changes to a monthly frame."""
    require_columns(monthly, ("month_start",), "add_month_over_month")
    frame = monthly.sort_values("month_start").reset_index(drop=True).copy()
    for metric in metrics:
        require_columns(frame, (metric,), "add_month_over_month")
        previous = frame[metric].shift(1)
        frame[f"{metric}_mom_change"] = (frame[metric] - previous).round(2)
        frame[f"{metric}_mom_pct"] = pd.Series(
            percentage_change(frame[metric], previous), index=frame.index
        ).round(4)
    return frame

