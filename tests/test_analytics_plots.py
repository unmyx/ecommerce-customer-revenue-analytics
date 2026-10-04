"""Unit tests for the reusable business charts.

These assert the data behind each figure (values, ordering, labels), not merely
that an image file was produced.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from matplotlib.figure import Figure

from novacart.analytics.common import AnalyticsError
from novacart.analytics.plots import (
    FIGURE_FILENAMES,
    plot_customer_revenue_distribution,
    plot_monthly_aov_trend,
    plot_monthly_orders_trend,
    plot_monthly_revenue_trend,
    plot_revenue_by_category,
    plot_revenue_by_country,
    plot_top_products_by_revenue,
    render_all_figures,
)


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
    assert set(paths) == set(FIGURE_FILENAMES)
    for key, path in paths.items():
        assert path.name == FIGURE_FILENAMES[key]
        assert path.is_file()
        assert path.stat().st_size > 0


def test_charts_reject_empty_data(monthly: pd.DataFrame) -> None:
    with pytest.raises(AnalyticsError):
        plot_monthly_revenue_trend(monthly.iloc[0:0])
    with pytest.raises(AnalyticsError):
        plot_revenue_by_category(pd.DataFrame({"category": [], "revenue": []}))

