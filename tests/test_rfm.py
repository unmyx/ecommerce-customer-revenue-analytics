"""Unit tests for RFM scoring and segment assignment (part A)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from novacart.analytics.common import AnalyticsError
from novacart.analytics.rfm import (
    NEVER_PURCHASED_SEGMENT,
    RFM_SCORE_BANDS,
    SEGMENT_ORDER,
    rfm_table,
    segment_for_scores,
    segment_score_profile,
    segment_summary,
)


@pytest.fixture()
def customers() -> pd.DataFrame:
    """Ten purchasers with strictly ordered recency, frequency and monetary value."""
    rows = []
    for index in range(10):
        rows.append(
            {
                "customer_id": f"C{index + 1:02d}",
                "country_code": "DE",
                "acquisition_channel": "organic_search",
                "has_purchased": True,
                "total_orders": index + 1,
                "total_revenue": float((index + 1) * 100),
                "days_since_last_order": float((10 - index) * 10),
                "average_order_value": 100.0,
                "repeat_customer": index >= 4,
            }
        )
    rows.append(
        {
            "customer_id": "C11",
            "country_code": "DE",
            "acquisition_channel": "display",
            "has_purchased": False,
            "total_orders": 0,
            "total_revenue": 0.0,
            "days_since_last_order": np.nan,
            "average_order_value": np.nan,
            "repeat_customer": False,
        }
    )
    return pd.DataFrame(rows)


def test_scores_are_quintiles_with_recency_reversed(customers: pd.DataFrame) -> None:
    rfm = rfm_table(customers)
    purchasers = rfm.loc[rfm["has_purchased"]].set_index("customer_id")

    # Two customers per band when the sample is exactly divisible by the bands.
    assert purchasers.loc["C10", "r_score"] == RFM_SCORE_BANDS  # most recent
    assert purchasers.loc["C09", "r_score"] == RFM_SCORE_BANDS
    assert purchasers.loc["C01", "r_score"] == 1  # least recent
    assert purchasers.loc["C10", "f_score"] == RFM_SCORE_BANDS  # most orders
    assert purchasers.loc["C10", "m_score"] == RFM_SCORE_BANDS  # highest revenue
    assert purchasers.loc["C01", "f_score"] == 1
    assert purchasers.loc["C01", "m_score"] == 1

    assert purchasers["r_score"].between(1, RFM_SCORE_BANDS).all()
    assert purchasers["f_score"].between(1, RFM_SCORE_BANDS).all()
    assert purchasers["m_score"].between(1, RFM_SCORE_BANDS).all()
    assert purchasers["rfm_score"].between(3, 3 * RFM_SCORE_BANDS).all()


def test_rfm_cell_and_segments_are_assigned(customers: pd.DataFrame) -> None:
    rfm = rfm_table(customers)
    purchasers = rfm.loc[rfm["has_purchased"]]
    top = purchasers.loc[purchasers["customer_id"] == "C10"].iloc[0]
    assert top["rfm_cell"] == "555"
    assert top["rfm_segment"] == "Champions"
    assert set(purchasers["rfm_segment"]).issubset(set(SEGMENT_ORDER))

    lowest = purchasers.loc[purchasers["customer_id"] == "C01"].iloc[0]
    assert lowest["rfm_cell"] == "111"
    assert lowest["rfm_segment"] == "Dormant"


def test_never_purchased_customers_are_kept_without_scores(customers: pd.DataFrame) -> None:
    rfm = rfm_table(customers)
    never = rfm.loc[~rfm["has_purchased"]].iloc[0]
    assert never["rfm_segment"] == NEVER_PURCHASED_SEGMENT
    assert pd.isna(never["r_score"])
    assert pd.isna(never["f_score"])
    assert pd.isna(never["m_score"])
    assert pd.isna(never["rfm_score"])
    assert never["frequency_orders"] == 0
    assert never["monetary_revenue"] == 0.0


@pytest.mark.parametrize(
    ("r_score", "f_score", "m_score", "expected"),
    [
        (5, 5, 5, "Champions"),
        (4, 4, 4, "Champions"),
        (3, 3, 3, "Loyal Customers"),
        (5, 3, 2, "Loyal Customers"),
        (4, 2, 2, "Potential Loyalists"),
        (4, 1, 1, "New Customers"),
        (2, 5, 5, "At Risk"),
        (1, 3, 3, "At Risk"),
        (1, 1, 1, "Dormant"),
        (2, 2, 2, "Dormant"),
        (3, 2, 2, "Needs Attention"),
        (3, 1, 5, "Needs Attention"),
    ],
)
def test_documented_segment_rules(r_score, f_score, m_score, expected) -> None:
    assert segment_for_scores(r_score, f_score, m_score) == expected


def test_segment_rules_cover_every_score_combination() -> None:
    segments = {
        segment_for_scores(r, f, m)
        for r in range(1, RFM_SCORE_BANDS + 1)
        for f in range(1, RFM_SCORE_BANDS + 1)
        for m in range(1, RFM_SCORE_BANDS + 1)
    }
    assert segments.issubset(set(SEGMENT_ORDER))
    assert "Champions" in segments and "Dormant" in segments


def test_segment_summary_reconciles_with_the_input(customers: pd.DataFrame) -> None:
    rfm = rfm_table(customers)
    summary = segment_summary(rfm)

    assert summary["customers"].sum() == len(customers)
    assert summary["revenue"].sum() == pytest.approx(customers["total_revenue"].sum())
    # Shares are rounded to four decimals for reporting, so the total is 100
    # up to that rounding rather than exactly 100.
    assert summary["customer_share_pct"].sum() == pytest.approx(100.0, abs=0.01)
    assert summary["revenue_share_pct"].sum() == pytest.approx(100.0, abs=0.01)
    assert set(summary["rfm_segment"]).issubset(set(SEGMENT_ORDER))
    assert summary["repeat_customer_rate"].between(0, 1).all()

    champions = summary.loc[summary["rfm_segment"] == "Champions"].iloc[0]
    # C07-C10 all score (4+, 4+, 4+): revenue 700 + 800 + 900 + 1000.
    assert champions["customers"] == 4
    assert champions["revenue"] == pytest.approx(3400.0)
    assert champions["average_customer_revenue"] == pytest.approx(850.0)
    # Business reading: the top segment out-earns the rest per customer.
    assert champions["average_customer_revenue"] > summary["average_customer_revenue"].mean()


def test_segment_score_profile_averages_scores(customers: pd.DataFrame) -> None:
    rfm = rfm_table(customers)
    profile = segment_score_profile(rfm)
    assert not profile.empty
    assert profile[["average_r", "average_f", "average_m"]].to_numpy().max() <= RFM_SCORE_BANDS
    champions = profile.loc[profile["rfm_segment"] == "Champions"].iloc[0]
    # Champions are C07/C08 (4,4,4) and C09/C10 (5,5,5).
    assert champions["average_r"] == pytest.approx(4.5)
    assert champions["average_f"] == pytest.approx(4.5)
    assert champions["average_m"] == pytest.approx(4.5)
    assert champions["average_r"] > profile["average_r"].mean()


def test_rfm_output_is_deterministic_and_row_order_independent(customers: pd.DataFrame) -> None:
    first = rfm_table(customers)
    shuffled = rfm_table(customers.sample(frac=1.0, random_state=7))
    pd.testing.assert_frame_equal(
        first.sort_values("customer_id").reset_index(drop=True),
        shuffled.sort_values("customer_id").reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(first, rfm_table(customers))


def test_rfm_handles_empty_and_invalid_input(customers: pd.DataFrame) -> None:
    empty = rfm_table(customers.iloc[0:0])
    assert empty.empty
    assert "rfm_segment" in empty.columns
    assert segment_summary(empty).empty
    assert segment_score_profile(empty).empty

    with pytest.raises(AnalyticsError):
        rfm_table(pd.DataFrame({"customer_id": ["C1"], "has_purchased": [True]}))

