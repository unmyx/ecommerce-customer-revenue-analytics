"""Unit tests for the static Power BI page previews (Milestone 5, part E)."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import pytest
from matplotlib.figure import Figure

from novacart.analytics.common import AnalyticsError
from novacart.dashboard.exports import build_export_frames
from novacart.dashboard.preview import (
    PAGE_FILENAMES,
    draw_campaign_analytics,
    draw_customer_analytics,
    draw_executive_overview,
    draw_product_analytics,
    render_dashboard_previews,
)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture()
def frames(presentation_analysis, presentation_inputs) -> dict[str, pd.DataFrame]:
    return build_export_frames(presentation_analysis, presentation_inputs)


def test_executive_page_draws_kpi_cards_and_panels(frames) -> None:
    figure = draw_executive_overview(frames)
    assert isinstance(figure, Figure)
    assert "Executive overview" in figure._suptitle.get_text()
    # Six KPI cards plus six analytical panels.
    assert len(figure.axes) == 12


def test_customer_page_draws_segments_value_and_cohorts(frames) -> None:
    figure = draw_customer_analytics(frames)
    assert "Customer analytics" in figure._suptitle.get_text()
    assert len(figure.axes) >= 5


def test_product_page_draws_categories_products_and_declines(frames) -> None:
    figure = draw_product_analytics(frames)
    assert "Product analytics" in figure._suptitle.get_text()
    assert len(figure.axes) >= 4


def test_product_page_handles_a_window_without_declining_products(frames) -> None:
    """A small or filtered window may have no product meeting the decline rule."""
    without_declines = dict(frames)
    without_declines["declining_products"] = pd.DataFrame()
    figure = draw_product_analytics(without_declines)
    assert "Product analytics" in figure._suptitle.get_text()


def test_campaign_page_draws_lift_intervals_and_table(frames) -> None:
    figure = draw_campaign_analytics(frames)
    assert "Campaign analytics" in figure._suptitle.get_text()
    assert len(figure.axes) >= 4
    # The results table is drawn on the last axis.
    assert figure.axes[-1].get_title(loc="left").startswith("Campaign results")


def test_render_dashboard_previews_writes_four_named_files(frames, tmp_path) -> None:
    paths = render_dashboard_previews(frames, output_dir=tmp_path)
    assert set(paths) == set(PAGE_FILENAMES)
    for name, path in paths.items():
        assert path.name == PAGE_FILENAMES[name]
        assert path.is_file()
        assert path.stat().st_size > 10_000  # a real rendered page, not an empty canvas


def test_previews_reject_empty_datasets() -> None:
    with pytest.raises(AnalyticsError):
        draw_executive_overview({"kpi_summary": pd.DataFrame()})
    with pytest.raises(AnalyticsError):
        draw_campaign_analytics({"campaign_results": pd.DataFrame()})

