"""Marketing campaigns with randomised treatment and control (holdout) groups."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from novacart.synthetic import reference
from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.customers import CustomerData
from novacart.synthetic.sampling import (
    draw_index_with_weights,
    weighted_sample_without_replacement,
)

TREATMENT_SHARE = 0.72
EXPOSURE_RATE_WITHIN_TREATMENT = 0.93
MIN_AUDIENCE_SIZE = 800
MAX_AUDIENCE_SIZE = 7_000

OBJECTIVE_TO_AUDIENCE: dict[str, str] = {
    "acquisition": "new_customers",
    "retention": "loyal_customers",
    "reactivation": "lapsed_customers",
    "cross_sell": "high_propensity",
    "brand": "broad_reach",
}


@dataclass(frozen=True)
class CampaignData:
    campaigns: pd.DataFrame
    assignments: pd.DataFrame
    effects: pd.DataFrame
    """Ground-truth effect sizes. Generation metadata only - never loaded to the database."""


def _eligible_mask(
    audience: str,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    customers: pd.DataFrame,
    latent: pd.DataFrame,
) -> np.ndarray:
    signup = pd.to_datetime(customers["signup_date"])
    # A customer can only be targeted once they exist in the database.
    exists = (signup <= end_date).to_numpy()
    if audience == "new_customers":
        return exists & (
            (signup >= start_date - pd.Timedelta(days=120)) & (signup <= start_date)
        ).to_numpy()
    if audience == "high_propensity":
        return exists & (latent["engagement"] > 0.60).to_numpy()
    if audience == "loyal_customers":
        return exists & (
            (latent["engagement"] > 0.72)
            & (signup <= start_date - pd.Timedelta(days=180))
        ).to_numpy()
    if audience == "lapsed_customers":
        return exists & (latent["churn_hazard"] > 0.55).to_numpy()
    return exists


def generate_campaigns(
    config: GenerationConfig,
    rng: np.random.Generator,
    customer_data: CustomerData,
) -> CampaignData:
    customers = customer_data.customers
    latent = customer_data.latent
    n = config.n_campaigns

    window_start = pd.Timestamp(config.start_date)
    window_end = pd.Timestamp(config.end_date)
    window_length = (window_end - window_start).days

    channels = list(reference.CAMPAIGN_CHANNELS)
    objectives = list(reference.CAMPAIGN_OBJECTIVES)

    campaign_rows: list[dict[str, object]] = []
    assignment_rows: list[dict[str, object]] = []
    effect_rows: list[dict[str, object]] = []
    assignment_counter = 0

    next_id = 1
    for index in range(n):
        duration = int(rng.integers(21, 50))
        latest_start_offset = max(10, window_length - duration - 5)
        start_offset = int(rng.integers(10, latest_start_offset + 1))
        start_date = window_start + pd.Timedelta(days=start_offset)
        end_date = start_date + pd.Timedelta(days=duration)
        end_date = min(end_date, window_end)

        channel = channels[draw_index_with_weights(
            rng, [reference.CAMPAIGN_CHANNELS[c] for c in channels], 1
        )[0]]
        objective = objectives[draw_index_with_weights(
            rng, [reference.CAMPAIGN_OBJECTIVES[o] for o in objectives], 1
        )[0]]
        audience = OBJECTIVE_TO_AUDIENCE[objective]

        pattern = reference.CAMPAIGN_NAME_PATTERNS[index % len(reference.CAMPAIGN_NAME_PATTERNS)]
        campaign_id = f"CMP-{next_id:03d}"
        campaign_name = f"{pattern} {start_date.year}"
        next_id += 1

        eligible = _eligible_mask(audience, start_date, end_date, customers, latent)
        eligible_positions = np.flatnonzero(eligible)
        if len(eligible_positions) < MIN_AUDIENCE_SIZE:
            eligible_positions = np.flatnonzero(
                eligible & (latent["engagement"].to_numpy() > 0.55)
            )
        if len(eligible_positions) < MIN_AUDIENCE_SIZE:
            eligible_positions = np.flatnonzero(eligible)

        target_size = min(
            len(eligible_positions),
            int(rng.integers(MIN_AUDIENCE_SIZE, MAX_AUDIENCE_SIZE)),
        )
        selection_score = latent["engagement"].to_numpy()[eligible_positions]
        chosen = eligible_positions[
            weighted_sample_without_replacement(rng, selection_score, target_size)
        ]

        is_treatment = rng.random(len(chosen)) < TREATMENT_SHARE
        exposed = np.where(
            is_treatment, rng.random(len(chosen)) < EXPOSURE_RATE_WITHIN_TREATMENT, False
        )

        assigned_seconds = rng.integers(8 * 3600, 20 * 3600, size=len(chosen))
        assigned_at = start_date + pd.to_timedelta(assigned_seconds, unit="s")

        for position, treatment, is_exposed, stamp in zip(
            chosen, is_treatment, exposed, assigned_at, strict=True
        ):
            assignment_counter += 1
            assignment_rows.append(
                {
                    "assignment_id": f"ASG-{assignment_counter:07d}",
                    "campaign_id": campaign_id,
                    "customer_id": customers["customer_id"].iloc[int(position)],
                    "assigned_at": stamp,
                    "arm": "treatment" if treatment else "control",
                    "exposed": bool(is_exposed),
                    "assignment_method": "randomized_holdout",
                }
            )

        is_null = bool(rng.random() < config.zero_lift_campaign_share)
        if is_null:
            purchase_lift = 0.0
            aov_lift = 0.0
        else:
            purchase_lift = float(rng.uniform(0.30, 0.65))
            aov_lift = float(rng.uniform(0.04, 0.14))
            if objective == "brand":
                purchase_lift *= 0.35
                aov_lift = 0.0

        budget = round(float(target_size * rng.uniform(0.60, 2.60)) / 100.0) * 100.0
        budget = max(budget, 5_000.0)

        campaign_rows.append(
            {
                "campaign_id": campaign_id,
                "campaign_name": campaign_name,
                "channel": channel,
                "objective": objective,
                "target_audience": audience,
                "start_date": start_date.date(),
                "end_date": end_date.date(),
                "budget_eur": budget,
                "created_at": (start_date - pd.Timedelta(days=int(rng.integers(7, 22)))).normalize()
                + pd.Timedelta(hours=int(rng.integers(9, 18))),
            }
        )

        effect_rows.append(
            {
                "campaign_id": campaign_id,
                "objective": objective,
                "channel": channel,
                "target_audience": audience,
                "window_days": (end_date - start_date).days,
                "is_placebo": is_null,
                "true_purchase_lift": purchase_lift,
                "true_aov_lift": aov_lift,
                "assigned_customers": len(chosen),
                "exposed_customers": np.count_nonzero(exposed),
                "control_customers": np.count_nonzero(~is_treatment),
            }
        )

    campaigns = pd.DataFrame(campaign_rows).sort_values("campaign_id", kind="stable")
    campaigns = campaigns.reset_index(drop=True)
    assignments = pd.DataFrame(assignment_rows).sort_values(
        ["campaign_id", "assignment_id"], kind="stable"
    )
    assignments = assignments.reset_index(drop=True)
    effects = pd.DataFrame(effect_rows).sort_values("campaign_id", kind="stable").reset_index(drop=True)

    return CampaignData(campaigns=campaigns, assignments=assignments, effects=effects)

