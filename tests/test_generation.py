from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.generator import generate_dataset
from novacart.synthetic.models import TABLES
from novacart.synthetic.orders import build_demand_calendar


def test_row_counts_match_configuration(dataset, small_config) -> None:
    counts = dataset.row_counts()
    assert counts["customers"] == small_config.n_customers
    assert counts["products"] == small_config.n_products
    assert counts["marketing_campaigns"] == small_config.n_campaigns
    assert counts["payments"] == counts["orders"]
    assert counts["order_items"] >= counts["orders"]
    assert abs(counts["orders"] - small_config.target_orders) <= 0.30 * small_config.target_orders


def test_generated_dataset_passes_validation(dataset) -> None:
    assert dataset.validation is not None
    assert dataset.validation.errors == []


def test_frames_match_the_database_schema(dataset) -> None:
    for key, spec in TABLES.items():
        assert tuple(dataset.frames[key].columns) == spec.columns


def test_generation_is_deterministic(small_config) -> None:
    first = generate_dataset(small_config, write=False)
    second = generate_dataset(small_config, write=False)
    for key in TABLES:
        pd.testing.assert_frame_equal(first.frames[key], second.frames[key])


def test_different_seeds_produce_different_data(small_config) -> None:
    other = small_config.with_overrides(seed=small_config.seed + 1)
    first = generate_dataset(small_config, write=False)
    second = generate_dataset(other, write=False)
    assert not first.frames["orders"]["customer_id"].equals(second.frames["orders"]["customer_id"])


def test_keys_and_amounts_are_clean(dataset) -> None:
    frames = dataset.frames
    for key, spec in TABLES.items():
        frame = frames[key]
        required = [column for column in spec.columns if column not in spec.nullable_columns]
        assert not frame[required].isna().any().any(), f"{key} contains nulls"
        assert frame[list(spec.primary_key)].duplicated().sum() == 0

    orders = frames["orders"]
    money = ["items_subtotal", "discount_amount", "shipping_amount", "tax_amount"]
    assert (orders[money] >= 0).all().all()
    assert (orders["discount_amount"] <= orders["items_subtotal"]).all()
    assert (frames["order_items"]["quantity"] > 0).all()
    assert (frames["products"]["unit_cost"] <= frames["products"]["unit_price"]).all()


def test_orders_stay_inside_the_analysis_window(dataset, small_config) -> None:
    orders = dataset.frames["orders"]
    timestamps = pd.to_datetime(orders["order_ts"])
    assert timestamps.min() >= pd.Timestamp(small_config.start_date)
    assert timestamps.max() <= pd.Timestamp(small_config.end_date) + pd.Timedelta(days=1)

    signup = dataset.frames["customers"].set_index("customer_id")["signup_date"]
    assert (timestamps.dt.date.to_numpy() >= pd.to_datetime(
        orders["customer_id"].map(signup)
    ).dt.date.to_numpy()).all()


def test_business_metrics_are_plausible(dataset) -> None:
    diagnostics = dataset.diagnostics
    assert 20.0 < diagnostics["average_order_value"] < 400.0
    assert 1.5 < diagnostics["average_items_per_order"] < 4.0
    assert 0.25 < diagnostics["repeat_purchase_rate"] < 0.75
    purchasing_share = diagnostics["purchasing_customers"] / dataset.config.n_customers
    assert 0.40 < purchasing_share < 1.0


def test_every_campaign_has_a_control_group(dataset) -> None:
    assignments = dataset.frames["campaign_assignments"]
    grouped = assignments.groupby("campaign_id")["arm"]
    counts = grouped.value_counts().unstack(fill_value=0)
    assert (counts["treatment"] > 0).all()
    assert (counts["control"] > 0).all()

    exposed = assignments.groupby("campaign_id")["exposed"].sum()
    assert (exposed > 0).all()


def test_campaign_ground_truth_mixes_effect_and_placebo(dataset) -> None:
    effects = dataset.campaign_effects
    assert len(effects) == dataset.config.n_campaigns
    assert effects["is_placebo"].any()
    assert (~effects["is_placebo"]).any()
    active = effects.loc[~effects["is_placebo"], "true_purchase_lift"]
    assert (active > 0).all()
    assert (effects.loc[effects["is_placebo"], "true_purchase_lift"] == 0).all()
    assert effects["true_aov_lift"].between(0.0, 0.2).all()


def test_demand_calendar_has_seasonality(small_config) -> None:
    calendar = build_demand_calendar(small_config, np.random.default_rng(1))
    calendar["month"] = pd.to_datetime(calendar["date"]).dt.month
    monthly = calendar.groupby("month")["factor"].mean()
    assert monthly.idxmax() == 11
    assert monthly.loc[11] > monthly.loc[7] * 1.4
    assert monthly.loc[12] > monthly.mean()
    # Growth compounds over the two-year window.
    first_year = calendar.iloc[:365]["factor"].mean()
    last_year = calendar.iloc[-365:]["factor"].mean()
    assert last_year > first_year


def test_validation_reports_no_warnings_for_the_default_shape(dataset) -> None:
    assert dataset.validation is not None
    assert dataset.validation.summary()["failures"] == 0


@pytest.mark.slow
def test_full_scale_dataset_meets_the_brief() -> None:
    config = GenerationConfig()
    result = generate_dataset(config, write=False)
    counts = result.row_counts()
    assert counts["customers"] >= 15_000
    assert counts["products"] >= 1_200
    assert counts["orders"] >= 80_000
    assert counts["order_items"] >= 180_000
    assert counts["payments"] >= 80_000
    assert result.validation is not None and result.validation.passed

