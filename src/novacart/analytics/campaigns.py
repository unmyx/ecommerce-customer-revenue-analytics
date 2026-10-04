"""Campaign comparison and significance testing (Milestone 4, parts C and D).

Unit of analysis
    One row per **assigned customer** per campaign, taken from
    ``analytics.mart_campaign_customer_outcomes``. The outcome is recognised net
    revenue inside the campaign window. Treating individual orders as independent
    observations would overstate the sample size and understate uncertainty,
    because one customer can place several orders.

Primary comparison
    Intention-to-treat: everybody randomised into the treatment arm versus
    everybody randomised into the holdout arm, regardless of whether they were
    exposed. This preserves the randomisation and is the defensible primary
    estimate. ``exposed`` treatment members are reported descriptively, but the
    headline test stays ITT.

Decision rules (fixed before any result was inspected)
    * statistical significance: Benjamini-Hochberg adjusted p-value < 0.05;
    * practical significance: relative difference >= 10% **and** absolute
      difference >= EUR 5.00 per assigned customer;
    * both are reported separately, because a small but precisely estimated
      difference can be statistically significant without being worth acting on.

The generator's ground-truth lift is never used here; every number comes from the
observed analytical data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from novacart.analytics.common import AnalyticsError, empty_frame, require_columns, safe_divide
from novacart.analytics.statistics import (
    ALPHA,
    BOOTSTRAP_SEED,
    FDR_Q,
    benjamini_hochberg_adjusted,
    bootstrap_mean_difference_ci,
    effect_size_label,
    welch_mean_difference,
)

ARM_TREATMENT = "treatment"
ARM_CONTROL = "control"

#: Pre-specified practical-significance thresholds (see module docstring).
PRACTICAL_RELATIVE_THRESHOLD = 0.10
PRACTICAL_ABSOLUTE_THRESHOLD = 5.00

COMPARISON_COLUMNS = (
    "campaign_id",
    "campaign_name",
    "channel",
    "objective",
    "start_date",
    "end_date",
    "assigned_customers",
    "treatment_n",
    "control_n",
    "treatment_exposed",
    "treatment_revenue",
    "control_revenue",
    "treatment_mean",
    "control_mean",
    "absolute_difference",
    "relative_difference",
    "treatment_mean_orders",
    "control_mean_orders",
)

STATISTICS_COLUMNS = (
    "campaign_id",
    "campaign_name",
    "channel",
    "objective",
    "treatment_n",
    "control_n",
    "treatment_mean",
    "control_mean",
    "absolute_difference",
    "relative_difference",
    "confidence_interval_low",
    "confidence_interval_high",
    "bootstrap_confidence_interval_low",
    "bootstrap_confidence_interval_high",
    "p_value",
    "adjusted_p_value",
    "mann_whitney_p_value",
    "effect_size",
    "effect_size_label",
    "statistically_significant",
    "practically_significant",
    "business_interpretation",
)


def campaign_customer_outcomes(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Validate and clean the customer-level campaign outcome frame."""
    require_columns(
        outcomes,
        ("campaign_id", "customer_id", "arm", "window_revenue"),
        "campaign_customer_outcomes",
    )
    if outcomes.empty:
        return empty_frame(
            ["campaign_id", "customer_id", "arm", "window_revenue", "window_orders"]
        )

    frame = outcomes.copy()
    frame["arm"] = frame["arm"].astype(str).str.lower()
    unknown = set(frame["arm"]) - {ARM_TREATMENT, ARM_CONTROL}
    if unknown:
        raise AnalyticsError(f"Unknown campaign arm(s): {sorted(unknown)}")
    duplicated = frame.duplicated(subset=["campaign_id", "customer_id"])
    if duplicated.any():
        raise AnalyticsError(
            "Campaign outcomes must be unique per campaign and customer; "
            f"{int(duplicated.sum())} duplicate rows found"
        )
    frame["window_revenue"] = frame["window_revenue"].fillna(0.0).astype("float64")
    if "window_orders" not in frame.columns:
        frame["window_orders"] = 0
    frame["window_orders"] = frame["window_orders"].fillna(0).astype("int64")
    if "is_exposed_treatment" not in frame.columns:
        if "exposed" in frame.columns:
            frame["is_exposed_treatment"] = frame["arm"].eq(ARM_TREATMENT) & frame["exposed"].fillna(False).astype(bool)
        else:
            frame["is_exposed_treatment"] = False
    return frame


def campaign_comparison(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Descriptive treatment/holdout comparison per campaign (customer level)."""
    frame = campaign_customer_outcomes(outcomes)
    if frame.empty:
        return empty_frame(COMPARISON_COLUMNS)

    attributes = [
        column
        for column in (
            "campaign_id",
            "campaign_name",
            "channel",
            "objective",
            "start_date",
            "end_date",
        )
        if column in frame.columns
    ]
    exposure = frame.groupby("campaign_id", as_index=False).agg(
        treatment_exposed=("is_exposed_treatment", "sum")
    )
    treatment = (
        frame.loc[frame["arm"] == ARM_TREATMENT]
        .groupby("campaign_id", as_index=False)
        .agg(
            treatment_n=("customer_id", "count"),
            treatment_revenue=("window_revenue", "sum"),
            treatment_mean=("window_revenue", "mean"),
            treatment_mean_orders=("window_orders", "mean"),
        )
    )
    control = (
        frame.loc[frame["arm"] == ARM_CONTROL]
        .groupby("campaign_id", as_index=False)
        .agg(
            control_n=("customer_id", "count"),
            control_revenue=("window_revenue", "sum"),
            control_mean=("window_revenue", "mean"),
            control_mean_orders=("window_orders", "mean"),
        )
    )

    grouped = exposure.merge(treatment, on="campaign_id", how="outer")
    grouped = grouped.merge(control, on="campaign_id", how="left")
    grouped["treatment_n"] = grouped["treatment_n"].fillna(0).astype("int64")
    grouped["control_n"] = grouped["control_n"].fillna(0).astype("int64")
    grouped["assigned_customers"] = (grouped["treatment_n"] + grouped["control_n"]).astype("int64")
    grouped["treatment_exposed"] = grouped["treatment_exposed"].fillna(0).astype("int64")
    grouped["absolute_difference"] = (
        grouped["treatment_mean"] - grouped["control_mean"]
    ).round(2)
    grouped["relative_difference"] = safe_divide(
        grouped["absolute_difference"], grouped["control_mean"]
    ).round(4)
    for column in ("treatment_revenue", "control_revenue"):
        grouped[column] = grouped[column].round(2)
    for column in ("treatment_mean", "control_mean", "treatment_mean_orders", "control_mean_orders"):
        grouped[column] = grouped[column].round(2)

    if attributes and set(attributes) - {"campaign_id"}:
        attribute_frame = frame[attributes].drop_duplicates("campaign_id")
        grouped = grouped.merge(attribute_frame, on="campaign_id", how="left")
    # Keep a stable output contract: campaign attributes that are absent from the
    # input (for example in a small unit-test fixture) are reported as missing.
    for column in COMPARISON_COLUMNS:
        if column not in grouped.columns:
            grouped[column] = pd.NA
    return (
        grouped[list(COMPARISON_COLUMNS)]
        .sort_values("campaign_id")
        .reset_index(drop=True)
    )


def _interpret(row: pd.Series) -> str:
    difference = row["absolute_difference"]
    relative = row["relative_difference"]
    if pd.isna(row["p_value"]):
        return "Not testable (group too small or zero variance)"
    direction = "positive" if difference > 0 else "negative"
    magnitude = (
        f"{relative:+.1%} ({difference:+.2f} EUR per assigned customer)"
        if pd.notna(relative)
        else f"{difference:+.2f} EUR per assigned customer"
    )
    if row["statistically_significant"] and row["practically_significant"]:
        return f"Statistically significant and materially {direction}: {magnitude}"
    if row["statistically_significant"]:
        return f"Statistically significant but too small to matter in practice: {magnitude}"
    if row["practically_significant"]:
        return f"Directionally {direction} but not statistically significant at FDR {FDR_Q:.0%}: {magnitude}"
    return f"No detectable difference between treatment and holdout: {magnitude}"


def campaign_statistics(outcomes: pd.DataFrame) -> pd.DataFrame:
    """Full campaign results table: means, differences, CI, p-values and flags."""
    comparison = campaign_comparison(outcomes)
    if comparison.empty:
        return empty_frame(STATISTICS_COLUMNS)
    frame = campaign_customer_outcomes(outcomes)

    rows: list[dict[str, object]] = []
    for position, campaign in enumerate(comparison.itertuples()):
        subset = frame.loc[frame["campaign_id"] == campaign.campaign_id]
        treated = subset.loc[subset["arm"] == ARM_TREATMENT, "window_revenue"].to_numpy()
        controlled = subset.loc[subset["arm"] == ARM_CONTROL, "window_revenue"].to_numpy()
        test = welch_mean_difference(treated, controlled)
        boot_low, boot_high = bootstrap_mean_difference_ci(
            treated, controlled, seed=BOOTSTRAP_SEED + position
        )
        rows.append(
            {
                "campaign_id": campaign.campaign_id,
                "campaign_name": campaign.campaign_name,
                "channel": campaign.channel,
                "objective": campaign.objective,
                "treatment_n": test.treatment_n,
                "control_n": test.control_n,
                "treatment_mean": round(test.treatment_mean, 2) if pd.notna(test.treatment_mean) else np.nan,
                "control_mean": round(test.control_mean, 2) if pd.notna(test.control_mean) else np.nan,
                # Reuse the descriptive comparison so both published tables agree exactly.
                "absolute_difference": campaign.absolute_difference,
                "relative_difference": campaign.relative_difference,
                "confidence_interval_low": round(test.confidence_interval_low, 2),
                "confidence_interval_high": round(test.confidence_interval_high, 2),
                "bootstrap_confidence_interval_low": round(boot_low, 2),
                "bootstrap_confidence_interval_high": round(boot_high, 2),
                "p_value": test.p_value,
                "mann_whitney_p_value": test.mann_whitney_p_value,
                "effect_size": round(test.effect_size, 4),
                "effect_size_label": effect_size_label(test.effect_size),
            }
        )

    statistics = pd.DataFrame(rows)
    # Adjusted p-values keep full precision: rounding would turn very small
    # values into zero and understate the evidence.
    statistics["adjusted_p_value"] = benjamini_hochberg_adjusted(statistics["p_value"])
    statistics["statistically_significant"] = (
        statistics["adjusted_p_value"] < ALPHA
    ).fillna(False)
    statistics["practically_significant"] = (
        (statistics["relative_difference"] >= PRACTICAL_RELATIVE_THRESHOLD)
        & (statistics["absolute_difference"] >= PRACTICAL_ABSOLUTE_THRESHOLD)
    ).fillna(False)
    statistics["business_interpretation"] = statistics.apply(_interpret, axis=1)
    return statistics[list(STATISTICS_COLUMNS)].sort_values("campaign_id").reset_index(drop=True)


def significance_overview(statistics: pd.DataFrame) -> pd.DataFrame:
    """Headline count of campaigns by statistical and practical significance."""
    if statistics.empty:
        return empty_frame(["category", "campaigns"])
    rows = [
        ("campaigns tested", int(statistics["p_value"].notna().sum())),
        (
            "statistically significant (FDR 5%)",
            int(statistics["statistically_significant"].sum()),
        ),
        (
            "practically significant (>=10% and >= EUR 5)",
            int(statistics["practically_significant"].sum()),
        ),
        (
            "both statistical and practical",
            int(
                (
                    statistics["statistically_significant"]
                    & statistics["practically_significant"]
                ).sum()
            ),
        ),
        (
            "positive point estimate",
            int((statistics["absolute_difference"] > 0).sum()),
        ),
    ]
    return pd.DataFrame(rows, columns=["category", "campaigns"])

