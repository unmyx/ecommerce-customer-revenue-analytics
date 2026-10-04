"""Shared fixtures.

The full dataset takes a while to generate, so the tests run against a reduced
configuration with identical structure (``--slow`` runs use the real scale).
"""

from __future__ import annotations

import pytest

from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.generator import GenerationResult, generate_dataset


@pytest.fixture(scope="session")
def small_config() -> GenerationConfig:
    return GenerationConfig(
        seed=424242,
        n_customers=800,
        n_products=120,
        n_campaigns=6,
        target_orders=2_500,
    )


@pytest.fixture(scope="session")
def dataset(small_config: GenerationConfig) -> GenerationResult:
    return generate_dataset(small_config, write=False)


@pytest.fixture()
def frames(dataset: GenerationResult) -> dict:
    return {key: frame.copy() for key, frame in dataset.frames.items()}

