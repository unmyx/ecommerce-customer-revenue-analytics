"""Unit tests for campaign comparison and statistical testing (parts C and D)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from novacart.analytics.campaigns import (
    PRACTICAL_ABSOLUTE_THRESHOLD,
    PRACTICAL_RELATIVE_THRESHOLD,
    campaign_comparison,
    campaign_customer_outcomes,
    campaign_statistics,
    significance_overview,
)
from novacart.analytics.common import AnalyticsError
from novacart.analytics.statistics import (
    benjamini_hochberg_adjusted,
    bootstrap_mean_difference_ci,
    effect_size_label,
    welch_mean_difference,
)

TREATMENT = [10, 12, 14, 16, 18]
CONTROL = [8, 9, 10, 11, 12]


# ---------------------------------------------------------------------------
# Welch test, confidence interval and effect size
# ---------------------------------------------------------------------------
def test_welch_test_matches_hand_computed_values() -> None:
    result = welch_mean_difference(TREATMENT, CONTROL)

    assert result.treatment_n == 5 and result.control_n == 5
    assert result.treatment_mean == pytest.approx(14.0)
    assert result.control_mean == pytest.approx(10.0)
    assert result.difference == pytest.approx(4.0)
    assert result.relative_difference == pytest.approx(0.4)
    assert result.standard_error == pytest.approx(np.sqrt(2.5), abs=1e-9)
    assert result.t_statistic == pytest.approx(2.5298, abs=1e-3)
    assert result.degrees_of_freedom == pytest.approx(5.8824, abs=1e-3)
    assert result.p_value == pytest.approx(0.0454, abs=0.002)
    # 95% CI = 4 +/- t(0.975, 5.88) * 1.5811
    assert result.confidence_interval_low == pytest.approx(0.1123, abs=0.01)
    assert result.confidence_interval_high == pytest.approx(7.8877, abs=0.01)
    # Hedges' g = 1.6 * (1 - 3/31)
    assert result.effect_size == pytest.approx(1.4452, abs=1e-3)
    # Ties at 10 and 12 weaken the rank-based evidence relative to a clean split.
    assert result.mann_whitney_p_value == pytest.approx(0.0586, abs=0.01)


def test_welch_p_value_agrees_with_scipy() -> None:
    result = welch_mean_difference(TREATMENT, CONTROL)
    reference = stats.ttest_ind(TREATMENT, CONTROL, equal_var=False)
    assert result.p_value == pytest.approx(float(reference.pvalue), rel=1e-9)
    assert result.standard_error > 0


def test_confidence_interval_is_consistent_with_the_test() -> None:
    """A 95% interval excludes zero exactly when the two-sided p < 0.05."""
    significant = welch_mean_difference(TREATMENT, CONTROL)
    assert significant.p_value < 0.05
    assert significant.confidence_interval_low > 0

    identical = welch_mean_difference([5, 6, 7, 8, 9], [5, 6, 7, 8, 9])
    assert identical.difference == pytest.approx(0.0)
    assert identical.confidence_interval_low < 0 < identical.confidence_interval_high


def test_effect_size_direction_and_magnitude() -> None:
    stronger = welch_mean_difference([20, 22, 24, 26, 28], CONTROL)
    weaker = welch_mean_difference(TREATMENT, CONTROL)
    assert abs(stronger.effect_size) > abs(weaker.effect_size)

    negative = welch_mean_difference(CONTROL, TREATMENT)
    assert negative.effect_size < 0
    assert negative.relative_difference < 0


def test_small_groups_and_zero_variance_are_reported_not_crashed() -> None:
    single = welch_mean_difference([10.0], [5.0, 6.0])
    assert single.treatment_n == 1
    assert np.isnan(single.p_value)
    assert np.isnan(single.difference)
    assert np.isnan(single.effect_size)

    constant = welch_mean_difference([5.0, 5.0, 5.0], [5.0, 5.0, 5.0])
    assert constant.difference == pytest.approx(0.0)
    assert np.isnan(constant.p_value)  # zero standard error: not testable
    assert np.isnan(constant.confidence_interval_low)

    empty = welch_mean_difference([], [])
    assert empty.treatment_n == 0
    assert np.isnan(empty.p_value)


def test_welch_ignores_missing_values() -> None:
    with_nan = welch_mean_difference([10, 12, np.nan, 14, 16, 18], CONTROL)
    without_nan = welch_mean_difference(TREATMENT, CONTROL)
    assert with_nan.p_value == pytest.approx(without_nan.p_value)


# ---------------------------------------------------------------------------
# Bootstrap interval
# ---------------------------------------------------------------------------
def test_bootstrap_interval_is_deterministic_and_brackets_the_estimate() -> None:
    rng = np.random.default_rng(3)
    treatment = rng.gamma(2.0, 60.0, size=400)
    control = rng.gamma(2.0, 45.0, size=250)

    first = bootstrap_mean_difference_ci(treatment, control, seed=123)
    second = bootstrap_mean_difference_ci(treatment, control, seed=123)
    assert first == second
    assert first[0] < first[1]

    estimate = float(treatment.mean() - control.mean())
    assert first[0] < estimate < first[1]

    other = bootstrap_mean_difference_ci(treatment, control, seed=124)
    assert other != first


def test_bootstrap_handles_empty_groups() -> None:
    low, high = bootstrap_mean_difference_ci([], [1.0, 2.0])
    assert np.isnan(low) and np.isnan(high)


# ---------------------------------------------------------------------------
# Multiple-testing correction
# ---------------------------------------------------------------------------
def test_benjamini_hochberg_matches_a_known_example() -> None:
    p_values = [0.01, 0.02, 0.03, 0.04, 0.05]
    adjusted = benjamini_hochberg_adjusted(p_values)
    assert np.allclose(adjusted, [0.05] * 5)


def test_benjamini_hochberg_is_monotone_and_never_below_the_raw_p() -> None:
    p_values = [
        0.001,
        0.008,
        0.039,
        0.041,
        0.042,
        0.06,
        0.074,
        0.205,
        0.212,
        0.216,
        0.222,
        0.251,
        0.269,
        0.275,
        0.34,
    ]
    adjusted = benjamini_hochberg_adjusted(p_values)

    assert adjusted[0] == pytest.approx(0.015)
    assert adjusted[1] == pytest.approx(0.06)
    assert adjusted[2] == pytest.approx(0.126)
    assert adjusted[3] == pytest.approx(0.126)
    assert adjusted[4] == pytest.approx(0.126)
    assert np.all(adjusted >= np.asarray(p_values) - 1e-12)
    assert np.all(np.diff(adjusted) >= -1e-12)  # non-decreasing in p order
    assert np.all(adjusted <= 1.0)


def test_benjamini_hochberg_is_order_independent_and_nan_safe() -> None:
    p_values = [0.04, 0.001, np.nan, 0.03]
    adjusted = benjamini_hochberg_adjusted(p_values)

    # Only three testable campaigns, so the correction uses m = 3.
    assert adjusted[1] == pytest.approx(0.003)
    assert adjusted[3] == pytest.approx(0.04)
    assert adjusted[0] == pytest.approx(0.04)
    assert np.isnan(adjusted[2])

    shuffled = benjamini_hochberg_adjusted([0.03, 0.04, 0.001, np.nan])
    assert shuffled[2] == pytest.approx(0.003)
    assert shuffled[0] == pytest.approx(0.04)
    assert np.isnan(shuffled[3])


def test_benjamini_hochberg_edge_cases() -> None:
    assert benjamini_hochberg_adjusted([]).size == 0
    assert benjamini_hochberg_adjusted([0.2])[0] == pytest.approx(0.2)
    assert np.isnan(benjamini_hochberg_adjusted([np.nan])[0])


def test_effect_size_labels() -> None:
    assert effect_size_label(0.05) == "negligible"
    assert effect_size_label(-0.3) == "small"
    assert effect_size_label(0.6) == "medium"
    assert effect_size_label(1.4) == "large"
    assert effect_size_label(float("nan")) == "not testable"


# ---------------------------------------------------------------------------
# Campaign aggregation
# ---------------------------------------------------------------------------
def _outcomes(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_campaign_outcomes_are_validated() -> None:
    good = _outcomes(
        [
            {
                "campaign_id": "CMP-001",
                "customer_id": "C1",
                "arm": "treatment",
                "window_revenue": 10.0,
            }
        ]
    )
    assert campaign_customer_outcomes(good).shape[0] == 1

    duplicated = pd.concat([good, good], ignore_index=True)
    with pytest.raises(AnalyticsError):
        campaign_customer_outcomes(duplicated)

    unknown_arm = good.assign(arm="placebo")
    with pytest.raises(AnalyticsError):
        campaign_customer_outcomes(unknown_arm)

    with pytest.raises(AnalyticsError):
        campaign_customer_outcomes(pd.DataFrame({"campaign_id": ["CMP-001"]}))


def test_campaign_comparison_computes_arm_metrics() -> None:
    frame = _outcomes(
        [
            {"campaign_id": "CMP-001", "campaign_name": "Test", "channel": "email", "objective": "retention",
             "customer_id": "T1", "arm": "treatment", "is_exposed_treatment": True, "window_revenue": 100.0, "window_orders": 1},
            {"campaign_id": "CMP-001", "campaign_name": "Test", "channel": "email", "objective": "retention",
             "customer_id": "T2", "arm": "treatment", "is_exposed_treatment": True, "window_revenue": 200.0, "window_orders": 2},
            {"campaign_id": "CMP-001", "campaign_name": "Test", "channel": "email", "objective": "retention",
             "customer_id": "T3", "arm": "treatment", "is_exposed_treatment": False, "window_revenue": 300.0, "window_orders": 3},
            {"campaign_id": "CMP-001", "campaign_name": "Test", "channel": "email", "objective": "retention",
             "customer_id": "C1", "arm": "control", "is_exposed_treatment": False, "window_revenue": 50.0, "window_orders": 1},
            {"campaign_id": "CMP-001", "campaign_name": "Test", "channel": "email", "objective": "retention",
             "customer_id": "C2", "arm": "control", "is_exposed_treatment": False, "window_revenue": 100.0, "window_orders": 1},
        ]
    )
    comparison = campaign_comparison(frame).iloc[0]

    assert comparison["assigned_customers"] == 5
    assert comparison["treatment_n"] == 3
    assert comparison["control_n"] == 2
    assert comparison["treatment_exposed"] == 2
    assert comparison["treatment_revenue"] == pytest.approx(600.0)
    assert comparison["control_revenue"] == pytest.approx(150.0)
    assert comparison["treatment_mean"] == pytest.approx(200.0)
    assert comparison["control_mean"] == pytest.approx(75.0)
    assert comparison["absolute_difference"] == pytest.approx(125.0)
    assert comparison["relative_difference"] == pytest.approx(125 / 75, abs=1e-4)
    assert comparison["campaign_name"] == "Test"


def test_campaign_statistics_flags_and_interpretation() -> None:
    rows = []
    # CMP-001: clear, material difference.
    for index, revenue in enumerate(np.arange(100.0, 200.0)):
        rows.append({"campaign_id": "CMP-001", "campaign_name": "Lift", "channel": "email",
                     "objective": "retention", "customer_id": f"T{index}", "arm": "treatment",
                     "is_exposed_treatment": True, "window_revenue": float(revenue), "window_orders": 1})
    for index, revenue in enumerate(np.arange(100.0, 160.0)):
        rows.append({"campaign_id": "CMP-001", "campaign_name": "Lift", "channel": "email",
                     "objective": "retention", "customer_id": f"C{index}", "arm": "control",
                     "is_exposed_treatment": False, "window_revenue": float(revenue), "window_orders": 1})
    # CMP-002: identical distributions, no lift.
    for index, revenue in enumerate(np.arange(100.0, 200.0)):
        rows.append({"campaign_id": "CMP-002", "campaign_name": "Null", "channel": "display",
                     "objective": "brand", "customer_id": f"T{index}", "arm": "treatment",
                     "is_exposed_treatment": True, "window_revenue": float(revenue), "window_orders": 1})
    for index, revenue in enumerate(np.arange(100.0, 200.0)):
        rows.append({"campaign_id": "CMP-002", "campaign_name": "Null", "channel": "display",
                     "objective": "brand", "customer_id": f"C{index}", "arm": "control",
                     "is_exposed_treatment": False, "window_revenue": float(revenue), "window_orders": 1})

    statistics = campaign_statistics(_outcomes(rows))
    assert list(statistics["campaign_id"]) == ["CMP-001", "CMP-002"]
    assert statistics[["treatment_n", "control_n"]].to_numpy().tolist() == [[100, 60], [100, 100]]

    lift = statistics.iloc[0]
    assert lift["treatment_mean"] == pytest.approx(149.5)
    assert lift["control_mean"] == pytest.approx(129.5)
    assert lift["absolute_difference"] == pytest.approx(20.0)
    assert lift["relative_difference"] == pytest.approx(0.1544, abs=1e-3)
    assert lift["p_value"] < 0.001
    assert lift["adjusted_p_value"] >= lift["p_value"]
    assert bool(lift["statistically_significant"]) is True
    assert bool(lift["practically_significant"]) is True
    assert "materially positive" in lift["business_interpretation"]
    assert lift["confidence_interval_low"] > 0
    assert lift["effect_size"] > 0.5
    assert lift["effect_size_label"] in {"medium", "large"}

    null = statistics.iloc[1]
    assert null["absolute_difference"] == pytest.approx(0.0)
    assert null["p_value"] == pytest.approx(1.0)
    assert bool(null["statistically_significant"]) is False
    assert bool(null["practically_significant"]) is False
    assert "No detectable difference" in null["business_interpretation"]


def test_campaign_statistics_uses_pre_specified_thresholds() -> None:
    statistics = campaign_statistics(
        _outcomes(
            [
                {"campaign_id": "CMP-001", "customer_id": "T1", "arm": "treatment",
                 "is_exposed_treatment": True, "window_revenue": 100.0, "window_orders": 1},
                {"campaign_id": "CMP-001", "customer_id": "T2", "arm": "treatment",
                 "is_exposed_treatment": True, "window_revenue": 101.0, "window_orders": 1},
                {"campaign_id": "CMP-001", "customer_id": "C1", "arm": "control",
                 "is_exposed_treatment": False, "window_revenue": 99.0, "window_orders": 1},
                {"campaign_id": "CMP-001", "customer_id": "C2", "arm": "control",
                 "is_exposed_treatment": False, "window_revenue": 100.0, "window_orders": 1},
            ]
        )
    ).iloc[0]
    # +1% relative lift is below both pre-specified practical thresholds.
    assert statistics["relative_difference"] < PRACTICAL_RELATIVE_THRESHOLD
    assert statistics["absolute_difference"] < PRACTICAL_ABSOLUTE_THRESHOLD
    assert bool(statistics["practically_significant"]) is False


def test_campaign_statistics_handles_an_untestable_campaign() -> None:
    statistics = campaign_statistics(
        _outcomes(
            [
                {"campaign_id": "CMP-001", "campaign_name": "Tiny", "channel": "email",
                 "objective": "retention", "customer_id": "C1", "arm": "control",
                 "is_exposed_treatment": False, "window_revenue": 10.0, "window_orders": 1},
                {"campaign_id": "CMP-001", "campaign_name": "Tiny", "channel": "email",
                 "objective": "retention", "customer_id": "T1", "arm": "treatment",
                 "is_exposed_treatment": True, "window_revenue": 20.0, "window_orders": 1},
                {"campaign_id": "CMP-001", "campaign_name": "Tiny", "channel": "email",
                 "objective": "retention", "customer_id": "T2", "arm": "treatment",
                 "is_exposed_treatment": True, "window_revenue": 30.0, "window_orders": 1},
            ]
        )
    ).iloc[0]
    assert statistics["control_n"] == 1
    assert np.isnan(statistics["p_value"])
    assert bool(statistics["statistically_significant"]) is False
    assert "Not testable" in statistics["business_interpretation"]


def test_campaign_statistics_is_deterministic() -> None:
    frame = _outcomes(
        [
            {"campaign_id": "CMP-001", "customer_id": f"T{index}", "arm": "treatment",
             "is_exposed_treatment": True, "window_revenue": float(index), "window_orders": 1}
            for index in range(50)
        ]
        + [
            {"campaign_id": "CMP-001", "customer_id": f"C{index}", "arm": "control",
             "is_exposed_treatment": False, "window_revenue": float(index) / 2, "window_orders": 1}
            for index in range(50)
        ]
    )
    first = campaign_statistics(frame)
    second = campaign_statistics(frame)
    pd.testing.assert_frame_equal(first, second)


def test_significance_overview_counts_campaigns() -> None:
    statistics = pd.DataFrame(
        {
            "p_value": [0.001, 0.2, np.nan],
            "adjusted_p_value": [0.002, 0.2, np.nan],
            "statistically_significant": [True, False, False],
            "practically_significant": [True, False, False],
            "absolute_difference": [10.0, -5.0, np.nan],
        }
    )
    overview = significance_overview(statistics).set_index("category")
    assert overview.loc["campaigns tested", "campaigns"] == 2
    assert overview.loc["statistically significant (FDR 5%)", "campaigns"] == 1
    assert overview.loc["both statistical and practical", "campaigns"] == 1
    assert overview.loc["positive point estimate", "campaigns"] == 1
    assert significance_overview(pd.DataFrame()).empty

