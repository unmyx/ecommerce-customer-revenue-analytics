"""Unit tests for the portfolio asset build (Milestone 6, part G)."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from matplotlib.figure import Figure

from novacart.analytics.common import AnalyticsError
from novacart.dashboard.exports import build_dashboard_exports
from novacart.portfolio import (
    IMAGE_FILENAMES,
    SAMPLE_DATASETS,
    build_portfolio_assets,
    draw_architecture,
    draw_campaign_statistics,
    draw_revenue_analysis,
    draw_rfm_segmentation,
)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture()
def export_dir(tmp_path, presentation_analysis, presentation_inputs):
    target = tmp_path / "csv"
    build_dashboard_exports(
        analysis=presentation_analysis, inputs=presentation_inputs, output_dir=target
    )
    return target


def test_architecture_diagram_has_every_layer() -> None:
    figure = draw_architecture()
    assert isinstance(figure, Figure)
    text = " ".join(artist.get_text() for artist in figure.axes[0].texts)
    for fragment in ("Synthetic source system", "PostgreSQL raw layer", "Analytical SQL layer",
                     "Python analytics", "Dashboard exports", "Presentation"):
        assert fragment in text
    assert figure._suptitle.get_text().startswith("NovaCart analytics platform")


def test_revenue_and_rfm_composites_draw_the_data(export_dir) -> None:
    frames = {
        name: pd.read_csv(export_dir / f"{name}.csv", low_memory=False)
        for name in ("monthly_revenue", "category_performance", "country_performance",
                     "customer_segments", "customer_value_deciles", "campaign_results",
                     "cohort_retention")
    }
    revenue = draw_revenue_analysis(frames)
    assert len(revenue.axes) == 3
    line = revenue.axes[0].get_lines()[0]
    assert len(line.get_ydata()) == len(frames["monthly_revenue"])

    rfm = draw_rfm_segmentation(frames)
    assert len(rfm.axes) == 3
    campaign = draw_campaign_statistics(frames)
    assert len(campaign.axes) == 2


def test_build_portfolio_assets_writes_images_samples_and_manifest(export_dir, tmp_path) -> None:
    paths = build_portfolio_assets(exports_dir=export_dir, output_dir=tmp_path / "portfolio")
    images = paths["images"]
    assert set(images) == set(IMAGE_FILENAMES)
    for key, path in images.items():
        assert path.name == IMAGE_FILENAMES[key]
        assert path.is_file()
        assert path.stat().st_size > 20_000

    samples = paths["samples"]
    assert set(SAMPLE_DATASETS).issubset(set(samples))
    for path in samples.values():
        assert path.is_file() and path.stat().st_size > 0

    manifest_path = tmp_path / "portfolio" / "assets_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(manifest["images"]) == set(IMAGE_FILENAMES)
    assert manifest["note"]
    for entry in manifest["images"].values():
        assert len(entry["checksum_sha256"]) == 64


def test_portfolio_build_requires_the_dashboard_exports(tmp_path) -> None:
    with pytest.raises(AnalyticsError):
        build_portfolio_assets(exports_dir=tmp_path / "missing", output_dir=tmp_path / "portfolio")

