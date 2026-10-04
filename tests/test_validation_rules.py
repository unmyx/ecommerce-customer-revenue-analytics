from __future__ import annotations

import pandas as pd
import pytest

from novacart.synthetic.validation import (
    DataValidationError,
    validate_dataset,
)


def _failing_checks(frames, config) -> set[str]:
    report = validate_dataset(frames, config)
    return {issue.check_id for issue in report.errors}


def test_duplicate_primary_key_is_detected(frames, small_config) -> None:
    frames["customers"].loc[1, "customer_id"] = frames["customers"].loc[0, "customer_id"]
    assert "customers_duplicate" in _failing_checks(frames, small_config)


def test_orphan_foreign_key_is_detected(frames, small_config) -> None:
    frames["orders"].loc[0, "customer_id"] = "CUST-999999"
    assert "orders_orphan" in _failing_checks(frames, small_config)


def test_invalid_order_line_is_detected(frames, small_config) -> None:
    line = frames["order_items"].index[0]
    frames["order_items"].loc[line, "line_discount"] = (
        frames["order_items"].loc[line, "quantity"]
        * frames["order_items"].loc[line, "unit_price"]
        + 10
    )
    assert "order_items_values" in _failing_checks(frames, small_config)


def test_payment_mismatch_is_detected(frames, small_config) -> None:
    frames["payments"].loc[0, "amount"] = frames["payments"].loc[0, "amount"] + 7
    assert "payments_amount_mismatch" in _failing_checks(frames, small_config)


def test_duplicate_product_within_an_order_is_detected(frames, small_config) -> None:
    items = frames["order_items"]
    first = items.iloc[0]
    duplicate = items.iloc[1].copy()
    duplicate["order_item_id"] = "OIT-99999999"
    duplicate["order_id"] = first["order_id"]
    duplicate["product_id"] = first["product_id"]
    frames["order_items"] = pd.concat([items, duplicate.to_frame().T], ignore_index=True)
    assert "order_items_order_product_duplicate" in _failing_checks(frames, small_config)


def test_control_group_exposure_is_detected(frames, small_config) -> None:
    index = frames["campaign_assignments"].index[0]
    frames["campaign_assignments"].loc[index, "arm"] = "control"
    frames["campaign_assignments"].loc[index, "exposed"] = True
    assert "assignments_control_exposed" in _failing_checks(frames, small_config)


def test_validation_error_carries_the_report(frames, small_config) -> None:
    frames["orders"].loc[0, "customer_id"] = "CUST-999999"
    report = validate_dataset(frames, small_config)
    with pytest.raises(DataValidationError):
        report.raise_if_failed()

