"""Statistical testing utilities (Milestone 4, part D).

The campaign experiment compares two independent groups of customers, so the
primary test is Welch's two-sample t-test on the customer-level outcome
(recognised revenue inside the campaign window). Welch is chosen over Student's
test because the treatment and holdout groups differ in size and variance, and
over a per-order test because orders from one customer are not independent
observations.

Reported alongside the test:

* a 95% confidence interval for the difference in means (Welch-Satterthwaite);
* a percentile bootstrap interval as a robustness check against the skew in
  customer revenue;
* Hedges' g as the standardised effect size (Cohen's d with the small-sample
  bias correction - with campaign samples this correction is small but harmless);
* a Mann-Whitney U p-value as a rank-based robustness check;
* Benjamini-Hochberg adjusted p-values across campaigns.

All functions are deterministic: the bootstrap takes an explicit seed and
``benjamini_hochberg_adjusted`` is order-independent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

ALPHA = 0.05
FDR_Q = 0.05
CONFIDENCE_LEVEL = 0.95
BOOTSTRAP_ITERATIONS = 1_000
BOOTSTRAP_SEED = 20261004


@dataclass(frozen=True)
class MeanDifferenceTest:
    """Result of comparing a treatment and control group of customers."""

    treatment_n: int
    control_n: int
    treatment_mean: float
    control_mean: float
    difference: float
    relative_difference: float
    standard_error: float
    confidence_interval_low: float
    confidence_interval_high: float
    t_statistic: float
    degrees_of_freedom: float
    p_value: float
    effect_size: float
    mann_whitney_p_value: float


def _clean(values) -> np.ndarray:
    array = np.asarray(values, dtype="float64").ravel()
    return array[~np.isnan(array)]


def welch_mean_difference(
    treatment, control, *, confidence: float = CONFIDENCE_LEVEL
) -> MeanDifferenceTest:
    """Welch t-test plus confidence interval and Hedges' g for two samples.

    Returns NaN statistics (rather than raising) when a group has fewer than two
    observations or when both groups are constant, so small campaigns can be
    reported honestly as "not testable".
    """
    treated = _clean(treatment)
    controlled = _clean(control)
    n_treatment, n_control = len(treated), len(controlled)
    if n_treatment < 2 or n_control < 2:
        return MeanDifferenceTest(
            treatment_n=n_treatment,
            control_n=n_control,
            treatment_mean=float(treated.mean()) if n_treatment else float("nan"),
            control_mean=float(controlled.mean()) if n_control else float("nan"),
            difference=float("nan"),
            relative_difference=float("nan"),
            standard_error=float("nan"),
            confidence_interval_low=float("nan"),
            confidence_interval_high=float("nan"),
            t_statistic=float("nan"),
            degrees_of_freedom=float("nan"),
            p_value=float("nan"),
            effect_size=float("nan"),
            mann_whitney_p_value=float("nan"),
        )

    treatment_mean = float(treated.mean())
    control_mean = float(controlled.mean())
    difference = treatment_mean - control_mean
    treatment_variance = float(treated.var(ddof=1))
    control_variance = float(controlled.var(ddof=1))

    se_treatment = treatment_variance / n_treatment
    se_control = control_variance / n_control
    standard_error = float(np.sqrt(se_treatment + se_control))

    if standard_error > 0:
        degrees_of_freedom = (se_treatment + se_control) ** 2 / (
            (se_treatment**2) / (n_treatment - 1) + (se_control**2) / (n_control - 1)
        )
        t_statistic = difference / standard_error
        p_value = float(2 * stats.t.sf(abs(t_statistic), degrees_of_freedom))
        critical = float(stats.t.ppf(1 - (1 - confidence) / 2, degrees_of_freedom))
        ci_low = difference - critical * standard_error
        ci_high = difference + critical * standard_error
    else:
        degrees_of_freedom = float("nan")
        t_statistic = float("nan")
        p_value = float("nan")
        ci_low = float("nan")
        ci_high = float("nan")

    pooled_sd = float(
        np.sqrt(
            ((n_treatment - 1) * treatment_variance + (n_control - 1) * control_variance)
            / (n_treatment + n_control - 2)
        )
    )
    effect_size = float("nan")
    if pooled_sd > 0:
        cohens_d = difference / pooled_sd
        correction = 1 - 3 / (4 * (n_treatment + n_control) - 9)
        effect_size = cohens_d * correction

    try:
        mann_whitney = float(stats.mannwhitneyu(treated, controlled, alternative="two-sided").pvalue)
    except ValueError:  # pragma: no cover - all-identical inputs
        mann_whitney = float("nan")

    return MeanDifferenceTest(
        treatment_n=n_treatment,
        control_n=n_control,
        treatment_mean=treatment_mean,
        control_mean=control_mean,
        difference=difference,
        relative_difference=(
            float(difference / control_mean) if control_mean not in (0.0,) else float("nan")
        ),
        standard_error=standard_error,
        confidence_interval_low=float(ci_low),
        confidence_interval_high=float(ci_high),
        t_statistic=float(t_statistic),
        degrees_of_freedom=float(degrees_of_freedom),
        p_value=p_value,
        effect_size=effect_size,
        mann_whitney_p_value=mann_whitney,
    )


def bootstrap_mean_difference_ci(
    treatment,
    control,
    *,
    iterations: int = BOOTSTRAP_ITERATIONS,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = CONFIDENCE_LEVEL,
) -> tuple[float, float]:
    """Percentile bootstrap interval for the difference in means (deterministic)."""
    treated = _clean(treatment)
    controlled = _clean(control)
    if len(treated) == 0 or len(controlled) == 0:
        return float("nan"), float("nan")

    rng = np.random.default_rng(seed)
    treatment_draws = treated[rng.integers(0, len(treated), size=(iterations, len(treated)))]
    control_draws = controlled[rng.integers(0, len(controlled), size=(iterations, len(controlled)))]
    differences = treatment_draws.mean(axis=1) - control_draws.mean(axis=1)
    alpha = (1 - confidence) / 2
    return float(np.quantile(differences, alpha)), float(np.quantile(differences, 1 - alpha))


def benjamini_hochberg_adjusted(p_values) -> np.ndarray:
    """Benjamini-Hochberg FDR-adjusted p-values, NaN-safe and order-independent.

    NaN p-values (campaigns that could not be tested) are excluded from the
    correction and stay NaN in the output.
    """
    values = np.asarray(p_values, dtype="float64")
    adjusted = np.full(values.shape, np.nan)
    mask = ~np.isnan(values)
    tested = int(mask.sum())
    if tested == 0:
        return adjusted

    raw = values[mask]
    order = np.argsort(raw, kind="stable")
    ranked = raw[order]
    scaled = ranked * tested / np.arange(1, tested + 1)
    monotone = np.minimum.accumulate(scaled[::-1])[::-1]
    clip = np.clip(monotone, 0.0, 1.0)
    restored = np.empty(tested)
    restored[order] = clip
    adjusted[mask] = restored
    return adjusted


def effect_size_label(effect_size: float) -> str:
    """Conventional interpretation of Hedges' g / Cohen's d."""
    if effect_size is None or np.isnan(effect_size):
        return "not testable"
    magnitude = abs(effect_size)
    if magnitude < 0.2:
        return "negligible"
    if magnitude < 0.5:
        return "small"
    if magnitude < 0.8:
        return "medium"
    return "large"

