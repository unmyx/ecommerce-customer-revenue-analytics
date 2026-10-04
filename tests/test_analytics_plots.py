"""Unit tests for the reusable business charts.

These assert the data behind each figure (values, ordering, labels), not merely
that an image file was produced.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from novacart.analytics.cohorts import cohort_analysis
from novacart.analytics.common import AnalyticsError
from novacart.analytics.plots import (
    FIGURE_FILENAMES,
    plot_campaign_confidence_intervals,
    plot_campaign_lift_comparison,
    plot_campaign_significance_overview,
    plot_cohort_retention_heatmap,
    plot_cohort_revenue_curve,
    plot_cohort_sizes,
    plot_customer_revenue_distribution,
    plot_monthly_aov_trend,
    plot_monthly_orders_trend,
    plot_monthly_revenue_trend,
    plot_revenue_by_category,
    plot_revenue_by_country,
    plot_rfm_segment_comparison,
    plot_rfm_segment_customers,
    plot_rfm_segment_revenue,
    plot_top_products_by_revenue,
    render_all_figures,
    render_campaign_figures,
    render_segmentation_figures,
)

#: The seven Milestone 3 business figures (the Milestone 4 renderers add nine more).
BUSINESS_FIGURE_KEYS = {
    "monthly_revenue",
    "monthly_orders",
    "monthly_aov",
    "revenue_by_category",
    "top_products_by_revenue",
    "customer_revenue_distribution",
    "revenue_by_country",
}


@pytest.fixture(autouse=True)
def _close_figures():
    """Keep the matplotlib figure registry clean across tests."""
    yield
    plt.close("all")


@pytest.fixture()
def monthly() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month_start": pd.to_datetime(["2026-01-01", "2026-02-01", "2026-03-01"]),
            "year_month": ["2026-01", "2026-02", "2026-03"],
            "revenue": [1000.0, 800.0, 1500.0],
            "orders_recognised": [10, 8, 15],
            "average_order_value": [100.0, 100.0, 100.0],
        }
    )


@pytest.fixture()
def categories() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "category": ["Electronics", "Home", "Fashion"],
            "revenue": [3000.0, 1500.0, 500.0],
            "units": [30, 60, 20],
            "orders": [20, 40, 15],
            "customers": [18, 35, 12],
        }
    )


@pytest.fixture()
def products() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "product_id": [f"P{index:02d}" for index in range(1, 13)],
            "product_name": [f"Product {index:02d}" for index in range(1, 13)],
            "revenue": [float(1200 - index * 50) for index in range(1, 13)],
            "units": [int(120 - index * 5) for index in range(1, 13)],
        }
    )


@pytest.fixture()
def countries() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_code": ["DE", "FR", "NL", "IT"],
            "revenue": [5000.0, 3000.0, 2000.0, 1000.0],
        }
    )


@pytest.fixture()
def customers() -> pd.DataFrame:
    rows = []
    for index in range(10):
        revenue = float((index + 1) * 100)
        rows.append(
            {
                "customer_id": f"C{index + 1:02d}",
                "has_purchased": True,
                "repeat_customer": index >= 5,
                "total_orders": 2 if index >= 5 else 1,
                "total_revenue": revenue,
            }
        )
    rows.append(
        {
            "customer_id": "C11",
            "has_purchased": False,
            "repeat_customer": False,
            "total_orders": 0,
            "total_revenue": 0.0,
        }
    )
    return pd.DataFrame(rows)


def test_monthly_revenue_chart_plots_the_data(monthly: pd.DataFrame) -> None:
    figure = plot_monthly_revenue_trend(monthly)
    assert isinstance(figure, Figure)
    axis = figure.axes[0]
    assert axis.get_title() == "Monthly net revenue"
    assert axis.get_ylabel() == "Net revenue (EUR)"
    assert axis.get_xlabel() == "Month"
    np.testing.assert_allclose(axis.get_lines()[0].get_ydata(), monthly["revenue"])


def test_monthly_orders_chart_plots_the_data(monthly: pd.DataFrame) -> None:
    figure = plot_monthly_orders_trend(monthly)
    axis = figure.axes[0]
    widths = [patch.get_height() for patch in axis.containers[0].patches]
    np.testing.assert_allclose(widths, monthly["orders_recognised"])
    assert "Orders per month" in axis.get_title()
    assert axis.get_ylabel() == "Orders"


def test_monthly_aov_chart_plots_the_data(monthly: pd.DataFrame) -> None:
    figure = plot_monthly_aov_trend(monthly)
    axis = figure.axes[0]
    np.testing.assert_allclose(
        axis.get_lines()[0].get_ydata(), monthly["average_order_value"]
    )
    assert axis.get_ylabel() == "Average order value (EUR)"


def test_revenue_by_category_chart_is_sorted_and_labelled(categories: pd.DataFrame) -> None:
    figure = plot_revenue_by_category(categories)
    axis = figure.axes[0]
    bars = axis.containers[0].patches
    labels = [tick.get_text() for tick in axis.get_yticklabels()]
    assert labels == ["Fashion", "Home", "Electronics"]  # ascending for a horizontal chart
    np.testing.assert_allclose([bar.get_width() for bar in bars], [500.0, 1500.0, 3000.0])
    assert "Revenue by category" in axis.get_title()
    assert axis.get_xlabel() == "Net revenue (EUR)"


def test_top_products_chart_shows_only_the_top_n(products: pd.DataFrame) -> None:
    figure = plot_top_products_by_revenue(products, n=10)
    axis = figure.axes[0]
    widths = [bar.get_width() for bar in axis.containers[0].patches]
    assert len(widths) == 10
    expected = sorted(products["revenue"].nlargest(10))
    np.testing.assert_allclose(widths, expected)
    assert "Top 10 products by revenue" == axis.get_title()


def test_customer_revenue_distribution_has_two_panels(customers: pd.DataFrame) -> None:
    figure = plot_customer_revenue_distribution(customers)
    assert len(figure.axes) == 2
    left, right = figure.axes
    assert left.get_title() == "Customer revenue distribution"
    assert left.get_ylabel() == "Customers"
    assert right.get_title() == "Share of revenue by customer decile"
    shares = [bar.get_height() for bar in right.containers[0].patches]
    assert len(shares) == 10
    assert sum(shares) == pytest.approx(100.0, abs=1e-3)
    assert shares[-1] > shares[0]  # the top decile holds more revenue


def test_revenue_by_country_chart_uses_country_codes(countries: pd.DataFrame) -> None:
    figure = plot_revenue_by_country(countries)
    axis = figure.axes[0]
    labels = [tick.get_text() for tick in axis.get_yticklabels()]
    assert labels == ["IT", "NL", "FR", "DE"]  # ascending for a horizontal chart
    widths = [bar.get_width() for bar in axis.containers[0].patches]
    np.testing.assert_allclose(widths, [1000.0, 2000.0, 3000.0, 5000.0])


def test_render_all_figures_writes_seven_deterministic_files(
    monthly: pd.DataFrame,
    categories: pd.DataFrame,
    products: pd.DataFrame,
    customers: pd.DataFrame,
    countries: pd.DataFrame,
    tmp_path,
) -> None:
    paths = render_all_figures(
        monthly=monthly,
        categories=categories,
        products=products,
        customers=customers,
        countries=countries,
        output_dir=tmp_path,
    )
    assert set(paths) == BUSINESS_FIGURE_KEYS
    for key, path in paths.items():
        assert path.name == FIGURE_FILENAMES[key]
        assert path.is_file()
        assert path.stat().st_size > 0


def test_charts_reject_empty_data(monthly: pd.DataFrame) -> None:
    with pytest.raises(AnalyticsError):
        plot_monthly_revenue_trend(monthly.iloc[0:0])
    with pytest.raises(AnalyticsError):
        plot_revenue_by_category(pd.DataFrame({"category": [], "revenue": []}))


# ---------------------------------------------------------------------------
# Milestone 4 figures
# ---------------------------------------------------------------------------
@pytest.fixture()
def rfm_segments() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rfm_segment": ["Champions", "Loyal Customers", "Dormant", "Never Purchased"],
            "customers": [120, 200, 300, 400],
            "customer_share_pct": [10.0, 16.0, 24.0, 50.0],
            "revenue": [7000.0, 2000.0, 800.0, 0.0],
            "revenue_share_pct": [71.4, 20.4, 8.2, 0.0],
        }
    )


@pytest.fixture()
def rfm_profile() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rfm_segment": ["Champions", "Loyal Customers", "Dormant"],
            "customers": [120, 200, 300],
            "average_r": [5.0, 3.4, 1.6],
            "average_f": [4.8, 3.1, 1.2],
            "average_m": [4.9, 3.0, 1.1],
        }
    )


@pytest.fixture()
def cohort():
    rows = []
    for cohort_month, customers in (("2026-01", ["A1", "A2"]), ("2026-02", ["B1"])):
        for customer in customers:
            rows.append(
                {
                    "order_id": f"{customer}-1",
                    "customer_id": customer,
                    "order_month": pd.Timestamp(f"{cohort_month}-01"),
                    "order_date": pd.Timestamp(f"{cohort_month}-05"),
                    "is_revenue_recognised": True,
                    "recognised_net_revenue": 100.0,
                    "recognised_units": 1,
                }
            )
    rows.append(
        {
            "order_id": "A1-2",
            "customer_id": "A1",
            "order_month": pd.Timestamp("2026-03-01"),
            "order_date": pd.Timestamp("2026-03-05"),
            "is_revenue_recognised": True,
            "recognised_net_revenue": 50.0,
            "recognised_units": 1,
        }
    )
    return cohort_analysis(pd.DataFrame(rows), analysis_end_date="2026-06-30")


@pytest.fixture()
def campaign_statistics_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "campaign_id": ["CMP-001", "CMP-002", "CMP-003"],
            "relative_difference": [0.30, -0.05, 0.02],
            "absolute_difference": [60.0, -8.0, 3.0],
            "confidence_interval_low": [20.0, -30.0, -12.0],
            "confidence_interval_high": [100.0, 14.0, 18.0],
            "adjusted_p_value": [0.001, 0.6, 0.4],
            "statistically_significant": [True, False, False],
            "practically_significant": [True, False, False],
        }
    )


def test_rfm_segment_charts_plot_the_data(rfm_segments: pd.DataFrame, rfm_profile) -> None:
    counts = plot_rfm_segment_customers(rfm_segments)
    widths = [bar.get_width() for bar in counts.axes[0].containers[0].patches]
    assert widths == sorted(rfm_segments["customers"].tolist())
    assert counts.axes[0].get_title() == "Customers by RFM segment"

    revenue = plot_rfm_segment_revenue(rfm_segments)
    widths = [bar.get_width() for bar in revenue.axes[0].containers[0].patches]
    assert widths == sorted(rfm_segments["revenue"].tolist())
    assert revenue.axes[0].get_title() == "Net revenue by RFM segment"

    comparison = plot_rfm_segment_comparison(rfm_profile)
    assert len(comparison.axes[0].containers) == 3
    for container in comparison.axes[0].containers:
        assert len(container.patches) == len(rfm_profile)
    assert comparison.axes[0].get_xlim()[1] > 5.0


def test_cohort_retention_heatmap_shows_the_matrix(cohort) -> None:
    figure = plot_cohort_retention_heatmap(cohort.retention_matrix)
    assert len(figure.axes) == 2  # heatmap + colour bar
    image = figure.axes[0].images[0]
    values = image.get_array()
    assert values.shape == cohort.retention_matrix.shape
    assert np.ma.is_masked(values)  # unobservable months are masked, not zero
    assert figure.axes[0].get_title() == "Monthly cohort retention"
    labels = [tick.get_text() for tick in figure.axes[0].get_yticklabels()]
    assert labels == ["2026-01", "2026-02"]


def test_cohort_size_and_revenue_charts(cohort) -> None:
    sizes = plot_cohort_sizes(cohort.sizes)
    heights = [bar.get_height() for bar in sizes.axes[0].containers[0].patches]
    assert heights == cohort.sizes["cohort_size"].tolist()

    revenue = plot_cohort_revenue_curve(cohort.revenue)
    line = revenue.axes[0].get_lines()[0]
    expected = (
        cohort.revenue.groupby("month_offset")["revenue_per_cohort_customer"].mean().to_numpy()
    )
    np.testing.assert_allclose(line.get_ydata(), expected)
    assert revenue.axes[0].get_xlabel() == "Months since first purchase"


def test_campaign_charts_plot_the_statistics(campaign_statistics_frame) -> None:
    frame = campaign_statistics_frame

    lift = plot_campaign_lift_comparison(frame)
    widths = [bar.get_width() for bar in lift.axes[0].containers[0].patches]
    assert widths == sorted((frame["relative_difference"] * 100).tolist())
    assert lift.axes[0].get_title() == "Campaign lift vs holdout (revenue per assigned customer)"

    intervals = plot_campaign_confidence_intervals(frame)
    assert len(intervals.axes[0].get_yticklabels()) == len(frame)
    # Interval + point marker per campaign, plus the zero reference line.
    assert len(intervals.axes[0].get_lines()) == 2 * len(frame) + 1

    overview = plot_campaign_significance_overview(frame)
    offsets = overview.axes[0].collections[0].get_offsets()
    assert len(offsets) == len(frame)
    assert overview.axes[0].get_ylabel().startswith("Statistical evidence")


def test_segmentation_and_campaign_renderers_write_deterministic_files(
    rfm_segments, rfm_profile, cohort, campaign_statistics_frame, tmp_path
) -> None:
    segmentation = render_segmentation_figures(
        segments=rfm_segments, profile=rfm_profile, cohort=cohort, output_dir=tmp_path
    )
    assert set(segmentation) == {
        "rfm_customer_counts",
        "rfm_revenue_by_segment",
        "rfm_segment_comparison",
        "cohort_retention_heatmap",
        "cohort_sizes",
        "cohort_revenue_curve",
    }
    campaigns = render_campaign_figures(
        statistics=campaign_statistics_frame, output_dir=tmp_path
    )
    assert set(campaigns) == {
        "campaign_lift_comparison",
        "campaign_confidence_intervals",
        "campaign_significance_overview",
    }
    for key, path in {**segmentation, **campaigns}.items():
        assert path.name == FIGURE_FILENAMES[key]
        assert path.is_file() and path.stat().st_size > 0


def test_milestone4_charts_reject_empty_data(rfm_segments, campaign_statistics_frame) -> None:
    with pytest.raises(AnalyticsError):
        plot_rfm_segment_customers(rfm_segments.iloc[0:0])
    with pytest.raises(AnalyticsError):
        plot_campaign_lift_comparison(campaign_statistics_frame.iloc[0:0])
    with pytest.raises(AnalyticsError):
        plot_cohort_retention_heatmap(pd.DataFrame())

