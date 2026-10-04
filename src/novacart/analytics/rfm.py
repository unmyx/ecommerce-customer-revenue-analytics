"""RFM segmentation (Milestone 4, part A).

Scoring method
    Recency, frequency and monetary value are each split into ``RFM_SCORE_BANDS``
    equal-count bands (quintiles) over purchasing customers:

    * recency  = ``mart_customer_features.days_since_last_order``, measured
      against the fixed analysis end date. Fewer days is better, so the most
      recent quintile scores 5 and the least recent scores 1.
    * frequency = recognised orders (``total_orders``): more is better.
    * monetary  = recognised net revenue (``total_revenue``): more is better.

    Ties are broken by ranking customers in ``customer_id`` order, so the same
    input always produces the same scores.

Segment rules
    Segments are assigned by the first matching rule in priority order, which
    makes the classification exhaustive and reproducible:

    1. Champions            R >= 4 and F >= 4 and M >= 4
    2. Loyal Customers      R >= 3 and F >= 3
    3. Potential Loyalists  R >= 4 and F >= 2
    4. New Customers        R >= 4 and F == 1
    5. At Risk              R <= 2 and F >= 3
    6. Dormant              R <= 2
    7. Needs Attention      any remaining purchasing customer

    Customers who have never purchased cannot be scored; they are kept in the
    table as ``Never Purchased`` with NULL scores so the reactivation universe is
    visible rather than silently dropped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from novacart.analytics.common import empty_frame, require_columns, safe_divide

RFM_SCORE_BANDS = 5

NEVER_PURCHASED_SEGMENT = "Never Purchased"

#: Business-readable order used by tables, charts and the notebook.
SEGMENT_ORDER: tuple[str, ...] = (
    "Champions",
    "Loyal Customers",
    "Potential Loyalists",
    "New Customers",
    "At Risk",
    "Needs Attention",
    "Dormant",
    NEVER_PURCHASED_SEGMENT,
)

SEGMENT_RULES: tuple[tuple[str, str], ...] = (
    ("Champions", "R >= 4 and F >= 4 and M >= 4"),
    ("Loyal Customers", "R >= 3 and F >= 3"),
    ("Potential Loyalists", "R >= 4 and F >= 2"),
    ("New Customers", "R >= 4 and F == 1"),
    ("At Risk", "R <= 2 and F >= 3"),
    ("Dormant", "R <= 2"),
    ("Needs Attention", "all remaining purchasing customers"),
)

RFM_TABLE_COLUMNS = (
    "customer_id",
    "country_code",
    "acquisition_channel",
    "rfm_segment",
    "has_purchased",
    "recency_days",
    "frequency_orders",
    "monetary_revenue",
    "average_order_value",
    "repeat_customer",
    "r_score",
    "f_score",
    "m_score",
    "rfm_score",
    "rfm_cell",
    "segment_rank",
)

SEGMENT_SUMMARY_COLUMNS = (
    "rfm_segment",
    "customers",
    "customer_share_pct",
    "revenue",
    "revenue_share_pct",
    "average_customer_revenue",
    "average_orders",
    "average_order_value",
    "average_recency_days",
    "repeat_customers",
    "repeat_customer_rate",
)


def _quintile_scores(
    values: pd.Series, *, higher_is_better: bool, bands: int = RFM_SCORE_BANDS
) -> pd.Series:
    """Equal-count band scores in ``1..bands`` with deterministic tie handling."""
    if len(values) == 0:
        return pd.Series(dtype="float64")
    ranks = values.rank(method="first", ascending=True)
    band = pd.qcut(ranks, bands, labels=False) + 1
    scores = band if higher_is_better else (bands + 1 - band)
    return scores.astype("int64")


def _assign_segments(scores: pd.DataFrame) -> pd.Series:
    r = scores["r_score"].to_numpy()
    f = scores["f_score"].to_numpy()
    m = scores["m_score"].to_numpy()
    conditions = [
        (r >= 4) & (f >= 4) & (m >= 4),
        (r >= 3) & (f >= 3),
        (r >= 4) & (f >= 2),
        (r >= 4) & (f == 1),
        (r <= 2) & (f >= 3),
        r <= 2,
    ]
    choices = [
        "Champions",
        "Loyal Customers",
        "Potential Loyalists",
        "New Customers",
        "At Risk",
        "Dormant",
    ]
    return pd.Series(np.select(conditions, choices, default="Needs Attention"), index=scores.index)


def segment_for_scores(r_score: int, f_score: int, m_score: int) -> str:
    """Segment name for a single R/F/M score triple (documented rule order)."""
    frame = pd.DataFrame(
        {"r_score": [int(r_score)], "f_score": [int(f_score)], "m_score": [int(m_score)]}
    )
    return str(_assign_segments(frame).iloc[0])


def rfm_table(customers: pd.DataFrame) -> pd.DataFrame:
    """Customer-level RFM scores and segment labels."""
    require_columns(
        customers,
        (
            "customer_id",
            "has_purchased",
            "total_orders",
            "total_revenue",
            "days_since_last_order",
        ),
        "rfm_table",
    )
    if customers.empty:
        return empty_frame(RFM_TABLE_COLUMNS)

    frame = customers.sort_values("customer_id", kind="stable").reset_index(drop=True).copy()
    frame["has_purchased"] = frame["has_purchased"].fillna(False).astype(bool)
    purchasing = frame.loc[frame["has_purchased"] & (frame["total_orders"] > 0)].copy()

    for column in ("r_score", "f_score", "m_score", "rfm_score", "rfm_cell"):
        frame[column] = pd.NA

    if not purchasing.empty:
        purchasing["r_score"] = _quintile_scores(
            purchasing["days_since_last_order"], higher_is_better=False
        )
        purchasing["f_score"] = _quintile_scores(
            purchasing["total_orders"], higher_is_better=True
        )
        purchasing["m_score"] = _quintile_scores(
            purchasing["total_revenue"], higher_is_better=True
        )
        purchasing["rfm_segment"] = _assign_segments(purchasing)
        purchasing["rfm_score"] = (
            purchasing["r_score"] + purchasing["f_score"] + purchasing["m_score"]
        )
        purchasing["rfm_cell"] = (
            purchasing["r_score"].astype(str)
            + purchasing["f_score"].astype(str)
            + purchasing["m_score"].astype(str)
        )

        frame = frame.drop(columns=["r_score", "f_score", "m_score", "rfm_score", "rfm_cell"])
        frame = frame.merge(
            purchasing[
                [
                    "customer_id",
                    "r_score",
                    "f_score",
                    "m_score",
                    "rfm_score",
                    "rfm_cell",
                    "rfm_segment",
                ]
            ],
            on="customer_id",
            how="left",
        )
    else:
        frame["rfm_segment"] = NEVER_PURCHASED_SEGMENT

    frame["rfm_segment"] = frame["rfm_segment"].fillna(NEVER_PURCHASED_SEGMENT)
    frame = frame.rename(
        columns={
            "days_since_last_order": "recency_days",
            "total_orders": "frequency_orders",
            "total_revenue": "monetary_revenue",
        }
    )
    if "average_order_value" not in frame.columns:
        frame["average_order_value"] = np.nan
    if "repeat_customer" not in frame.columns:
        frame["repeat_customer"] = frame["frequency_orders"] >= 2

    frame["segment_rank"] = frame["rfm_segment"].map(
        {segment: rank for rank, segment in enumerate(SEGMENT_ORDER)}
    )
    return frame[list(RFM_TABLE_COLUMNS)].sort_values(
        ["segment_rank", "monetary_revenue", "customer_id"], ascending=[True, False, True]
    ).reset_index(drop=True)


def segment_summary(rfm: pd.DataFrame) -> pd.DataFrame:
    """Customer count, revenue share, value and repeat metrics per segment."""
    require_columns(
        rfm,
        ("rfm_segment", "customer_id", "monetary_revenue", "frequency_orders"),
        "segment_summary",
    )
    if rfm.empty:
        return empty_frame(SEGMENT_SUMMARY_COLUMNS)

    frame = rfm.copy()
    frame["repeat_customer"] = frame["repeat_customer"].fillna(False).astype(bool)
    grouped = frame.groupby("rfm_segment", as_index=False).agg(
        customers=("customer_id", "count"),
        revenue=("monetary_revenue", "sum"),
        average_orders=("frequency_orders", "mean"),
        average_recency_days=("recency_days", "mean"),
        repeat_customers=("repeat_customer", "sum"),
        orders=("frequency_orders", "sum"),
    )
    grouped["revenue"] = grouped["revenue"].round(2)
    grouped["average_orders"] = grouped["average_orders"].round(3)
    grouped["average_recency_days"] = grouped["average_recency_days"].round(1)
    grouped["average_order_value"] = safe_divide(
        grouped["revenue"], grouped["orders"]
    ).round(2)
    grouped["average_customer_revenue"] = safe_divide(
        grouped["revenue"], grouped["customers"]
    ).round(2)
    grouped["customer_share_pct"] = (
        safe_divide(grouped["customers"], int(grouped["customers"].sum())) * 100
    ).round(4)
    grouped["revenue_share_pct"] = (
        safe_divide(grouped["revenue"], float(grouped["revenue"].sum())) * 100
    ).round(4)
    grouped["repeat_customer_rate"] = safe_divide(
        grouped["repeat_customers"], grouped["customers"]
    ).round(4)

    grouped["segment_rank"] = grouped["rfm_segment"].map(
        {segment: rank for rank, segment in enumerate(SEGMENT_ORDER)}
    )
    return (
        grouped.sort_values("segment_rank")[list(SEGMENT_SUMMARY_COLUMNS)]
        .reset_index(drop=True)
    )


def segment_score_profile(rfm: pd.DataFrame) -> pd.DataFrame:
    """Mean R/F/M scores per segment, used by the segment-comparison chart."""
    require_columns(rfm, ("rfm_segment", "r_score", "f_score", "m_score"), "segment_score_profile")
    scored = rfm.dropna(subset=["r_score", "f_score", "m_score"])
    if scored.empty:
        return empty_frame(["rfm_segment", "customers", "average_r", "average_f", "average_m"])

    grouped = scored.groupby("rfm_segment", as_index=False).agg(
        customers=("customer_id", "count"),
        average_r=("r_score", "mean"),
        average_f=("f_score", "mean"),
        average_m=("m_score", "mean"),
    )
    for column in ("average_r", "average_f", "average_m"):
        grouped[column] = grouped[column].round(2)
    grouped["segment_rank"] = grouped["rfm_segment"].map(
        {segment: rank for rank, segment in enumerate(SEGMENT_ORDER)}
    )
    return grouped.sort_values("segment_rank").drop(columns=["segment_rank"]).reset_index(drop=True)

