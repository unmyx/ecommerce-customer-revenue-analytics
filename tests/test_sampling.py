from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from novacart.synthetic.sampling import (
    ar1_multiplicative_noise,
    as_probabilities,
    cumulative_probabilities,
    day_range,
    draw_index,
    weighted_sample_without_replacement,
)


def test_as_probabilities_normalises_and_validates() -> None:
    result = as_probabilities([1.0, 3.0])
    assert result.tolist() == pytest.approx([0.25, 0.75])

    with pytest.raises(ValueError):
        as_probabilities([0.0, 0.0])
    with pytest.raises(ValueError):
        as_probabilities([1.0, -1.0])
    with pytest.raises(ValueError):
        as_probabilities([1.0, np.nan])


def test_draw_index_respects_weights() -> None:
    rng = np.random.default_rng(7)
    cumulative = cumulative_probabilities([1.0, 0.0, 0.0])
    draws = draw_index(rng, cumulative, 500)
    assert set(draws.tolist()) == {0}

    cumulative = cumulative_probabilities([0.5, 0.5])
    draws = draw_index(rng, cumulative, 5_000)
    share = float((draws == 0).mean())
    assert 0.45 < share < 0.55


def test_draw_index_is_deterministic_for_a_fixed_seed() -> None:
    cumulative = cumulative_probabilities([0.2, 0.3, 0.5])
    first = draw_index(np.random.default_rng(11), cumulative, 50)
    second = draw_index(np.random.default_rng(11), cumulative, 50)
    np.testing.assert_array_equal(first, second)


def test_day_range_is_inclusive() -> None:
    days = day_range(date(2024, 1, 1), date(2024, 1, 3))
    assert days.astype("datetime64[D]").astype(str).tolist() == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
    ]
    with pytest.raises(ValueError):
        day_range(date(2024, 1, 3), date(2024, 1, 1))


def test_ar1_noise_is_positive_and_smooth() -> None:
    rng = np.random.default_rng(3)
    noise = ar1_multiplicative_noise(rng, size=500, sigma=0.05, phi=0.6)
    assert np.all(noise > 0)
    assert 0.9 < float(np.median(noise)) < 1.1


def test_weighted_sample_without_replacement_returns_unique_positions() -> None:
    rng = np.random.default_rng(5)
    sample = weighted_sample_without_replacement(rng, np.arange(1, 21, dtype=float), 5)
    assert len(set(sample.tolist())) == 5
    assert np.all(sample >= 0) and np.all(sample < 20)

    everything = weighted_sample_without_replacement(rng, np.ones(4), 10)
    assert everything.tolist() == [0, 1, 2, 3]

