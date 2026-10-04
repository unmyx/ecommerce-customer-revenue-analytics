"""Unit tests for the end-to-end reconciliation (Milestone 6, part C)."""

from __future__ import annotations

import pytest

from novacart.analytics.common import AnalyticsError
from novacart.reconciliation import METRICS, assemble_reconciliation, summarise


def _values(**overrides: float) -> dict[str, float]:
    baseline = {key: 100.0 for key in METRICS}
    baseline.update(overrides)
    return baseline


def test_identical_layers_reconcile_with_zero_difference() -> None:
    raw = _values(revenue_recognised=14_861_510.32, orders_recognised=78_896)
    table = assemble_reconciliation(raw, dict(raw), dict(raw))
    summary = summarise(table)

    assert summary["ok"] is True
    assert summary["metrics"] == len(METRICS)
    assert summary["failed"] == 0
    assert summary["max_money_difference"] == 0.0
    assert summary["max_count_difference"] == 0.0
    assert table["passed"].all()


def test_money_differences_within_the_rounding_tolerance_pass() -> None:
    raw = _values(revenue_recognised=1000.00)
    analytical = _values(revenue_recognised=1000.00)
    exported = _values(revenue_recognised=1000.005)  # half a cent of rounding

    table = assemble_reconciliation(raw, analytical, exported)
    row = table.set_index("metric_key").loc["revenue_recognised"]
    assert row["passed"]
    assert row["tolerance"] == pytest.approx(0.01)


def test_money_differences_beyond_the_tolerance_fail() -> None:
    raw = _values(revenue_recognised=1000.00)
    analytical = _values(revenue_recognised=999.00)
    exported = _values(revenue_recognised=999.00)

    table = assemble_reconciliation(raw, analytical, exported)
    row = table.set_index("metric_key").loc["revenue_recognised"]
    assert not row["passed"]
    assert row["raw_minus_analytical"] == pytest.approx(1.0)

    summary = summarise(table)
    assert summary["ok"] is False
    assert summary["failed"] == 1
    assert summary["failed_metrics"] == ["Recognised revenue"]
    assert summary["max_money_difference"] == pytest.approx(1.0)


def test_count_metrics_must_match_exactly() -> None:
    raw = _values(orders_recognised=100)
    analytical = _values(orders_recognised=99)
    exported = _values(orders_recognised=100)

    table = assemble_reconciliation(raw, analytical, exported)
    row = table.set_index("metric_key").loc["orders_recognised"]
    assert not row["passed"]
    assert row["tolerance"] == 0.0
    assert row["raw_minus_analytical"] == pytest.approx(1.0)


def test_reconciliation_covers_every_documented_metric() -> None:
    table = assemble_reconciliation(_values(), _values(), _values())
    assert set(table["metric_key"]) == set(METRICS)
    assert {"money", "count"} == set(table["kind"])
    assert (table["expectation"] == "must equal").all()
    assert table["definition"].str.len().gt(0).all()


def test_missing_metric_is_reported_clearly() -> None:
    incomplete = _values()
    del incomplete["units_recognised"]
    with pytest.raises(AnalyticsError) as excinfo:
        assemble_reconciliation(incomplete, _values(), _values())
    assert "units_recognised" in str(excinfo.value)


def test_summarise_handles_an_empty_table() -> None:
    summary = summarise(assemble_reconciliation(_values(), _values(), _values()).iloc[0:0])
    assert summary["metrics"] == 0
    assert summary["ok"] is True

