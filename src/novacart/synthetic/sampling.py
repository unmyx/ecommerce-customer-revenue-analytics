"""Small sampling helpers shared by the generator modules."""

from __future__ import annotations

from datetime import date

import numpy as np


def as_probabilities(weights: np.ndarray | list[float] | tuple[float, ...]) -> np.ndarray:
    values = np.asarray(weights, dtype=float)
    if values.ndim != 1:
        raise ValueError("weights must be one-dimensional")
    if not np.all(np.isfinite(values)):
        raise ValueError("weights must be finite")
    if np.any(values < 0):
        raise ValueError("weights must be non-negative")
    total = values.sum()
    if total <= 0:
        raise ValueError("weights must not sum to zero")
    return values / total


def cumulative_probabilities(weights: np.ndarray | list[float] | tuple[float, ...]) -> np.ndarray:
    cumulative = np.cumsum(as_probabilities(weights))
    cumulative[-1] = 1.0
    return cumulative


def draw_index(rng: np.random.Generator, cumulative: np.ndarray, size: int) -> np.ndarray:
    """Vectorised inverse-CDF sampling (fast alternative to ``rng.choice``)."""
    if size <= 0:
        return np.empty(0, dtype=np.int64)
    uniforms = rng.random(size)
    return np.searchsorted(cumulative, uniforms, side="right").clip(0, len(cumulative) - 1)


def draw_index_with_weights(
    rng: np.random.Generator, weights: np.ndarray | list[float] | tuple[float, ...], size: int
) -> np.ndarray:
    return draw_index(rng, cumulative_probabilities(weights), size)


def day_range(start: date, end: date) -> np.ndarray:
    """Inclusive array of ``datetime64[D]`` values."""
    if start > end:
        raise ValueError("start must not be after end")
    return np.arange(np.datetime64(start, "D"), np.datetime64(end, "D") + np.timedelta64(1, "D"))


def ar1_multiplicative_noise(
    rng: np.random.Generator, size: int, sigma: float, phi: float
) -> np.ndarray:
    """Lognormal AR(1) noise: smooth day-to-day variation around a factor of 1.0."""
    innovations = rng.normal(0.0, sigma, size)
    series = np.empty(size, dtype=float)
    series[0] = innovations[0]
    for index in range(1, size):
        series[index] = phi * series[index - 1] + innovations[index]
    return np.exp(series)


def weighted_sample_without_replacement(
    rng: np.random.Generator, weights: np.ndarray, size: int
) -> np.ndarray:
    """Select ``size`` distinct positions with probability proportional to weight."""
    population = len(weights)
    if size >= population:
        return np.arange(population)
    probabilities = as_probabilities(weights)
    selected = rng.choice(population, size=size, replace=False, p=probabilities)
    return np.sort(selected)

