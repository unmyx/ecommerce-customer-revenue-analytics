"""Shared fixtures.

The full dataset takes a while to generate, so the tests run against a reduced
configuration with identical structure (``--slow`` runs use the real scale).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from novacart.analytics.common import AnalysisInputs
from novacart.analytics.report import BusinessAnalysis, analyse
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


# ---------------------------------------------------------------------------
# Presentation-layer fixtures: schema-complete but tiny, so the dashboard export,
# summary and preview code can be tested without a database.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def presentation_inputs() -> AnalysisInputs:
    """Eight customers, fourteen orders (one refunded) across three months."""
    order_rows = [
        # customer, order month, day, revenue, units, status, product, category, brand
        ("C1", "2026-01", 5, 100.0, 2, "completed", "P2", "Home & Kitchen", "Verdant"),
        ("C1", "2026-02", 6, 100.0, 1, "completed", "P3", "Fashion", "Marlow"),
        ("C1", "2026-03", 7, 100.0, 1, "completed", "P2", "Home & Kitchen", "Verdant"),
        ("C2", "2026-02", 8, 80.0, 1, "completed", "P1", "Electronics", "Kestrel"),
        ("C2", "2026-03", 9, 999.0, 5, "refunded", "P1", "Electronics", "Kestrel"),
        ("C3", "2026-01", 10, 120.0, 2, "completed", "P3", "Fashion", "Marlow"),
        ("C3", "2026-03", 11, 80.0, 1, "completed", "P4", "Beauty & Personal Care", "Cassia"),
        ("C5", "2026-01", 12, 150.0, 3, "completed", "P1", "Electronics", "Kestrel"),
        ("C5", "2026-02", 13, 100.0, 2, "completed", "P2", "Home & Kitchen", "Verdant"),
        ("C5", "2026-03", 14, 150.0, 3, "completed", "P1", "Electronics", "Kestrel"),
        ("C5", "2026-03", 20, 100.0, 1, "completed", "P5", "Sports & Outdoors", "Pinewood"),
        ("C6", "2026-01", 15, 60.0, 1, "completed", "P4", "Beauty & Personal Care", "Cassia"),
        ("C7", "2026-02", 16, 70.0, 1, "completed", "P5", "Sports & Outdoors", "Pinewood"),
        ("C7", "2026-03", 17, 80.0, 2, "completed", "P2", "Home & Kitchen", "Verdant"),
    ]
    regions = {
        "C1": ("DE", "organic_search"),
        "C2": ("DE", "paid_search"),
        "C3": ("NL", "organic_search"),
        "C5": ("FR", "email"),
        "C6": ("FR", "referral"),
        "C7": ("IT", "paid_search"),
    }

    orders = []
    lines = []
    for index, row in enumerate(order_rows, start=1):
        (customer, month, day, revenue, units, status, product, category, brand) = row
        order_id = f"O{index:03d}"
        order_date = pd.Timestamp(f"{month}-{day:02d}")
        recognised = status == "completed"
        orders.append(
            {
                "order_id": order_id,
                "customer_id": customer,
                "order_ts": order_date + pd.Timedelta(hours=12),
                "order_date": order_date,
                "order_month": pd.Timestamp(f"{month}-01"),
                "order_status": status,
                "is_revenue_recognised": recognised,
                "is_refunded": status == "refunded",
                "is_cancelled": False,
                "sales_channel": "web" if index % 2 else "mobile_app",
                "campaign_id": "CMP-001" if index % 3 == 0 else None,
                "is_campaign_attributed": index % 3 == 0,
                "country_code": regions[customer][0],
                "acquisition_channel": regions[customer][1],
                "customer_signup_date": pd.Timestamp("2025-11-01"),
                "line_count": 1,
                "total_units": units,
                "gross_merchandise_amount": revenue + (10.0 if recognised else 0.0),
                "discount_amount": 10.0 if recognised else 0.0,
                "net_revenue": revenue,
                "recognised_net_revenue": revenue if recognised else 0.0,
                "recognised_units": units if recognised else 0,
                "shipping_amount": 4.95 if recognised else 0.0,
                "vat_amount": 0.0,
                "order_total": revenue + 4.95 if recognised else 0.0,
                "currency_code": "EUR",
            }
        )
        lines.append(
            {
                "order_item_id": f"I{index:03d}",
                "order_id": order_id,
                "order_ts": order_date + pd.Timedelta(hours=12),
                "order_date": order_date,
                "order_month": pd.Timestamp(f"{month}-01"),
                "order_status": status,
                "is_revenue_recognised": recognised,
                "sales_channel": "web" if index % 2 else "mobile_app",
                "campaign_id": "CMP-001" if index % 3 == 0 else None,
                "customer_id": customer,
                "product_id": product,
                "product_name": f"{brand} {product}",
                "brand": brand,
                "category": category,
                "subcategory": "General",
                "quantity": units,
                "unit_price": round(revenue / units, 2),
                "unit_cost": round(revenue / units * 0.6, 2),
                "line_discount": 10.0 if recognised else 0.0,
                "line_gross_amount": revenue,
                "line_net_revenue": revenue,
                "line_cost": round(revenue * 0.6, 2),
                "line_gross_profit": round(revenue * 0.4, 2),
                "line_margin_rate": 0.4,
                "recognised_line_net_revenue": revenue if recognised else 0.0,
                "recognised_units": units if recognised else 0,
            }
        )

    customer_rows = []
    for index, (customer, (country, channel)) in enumerate(regions.items(), start=1):
        recognised = [o for o in orders if o["customer_id"] == customer and o["is_revenue_recognised"]]
        revenue = sum(o["recognised_net_revenue"] for o in recognised)
        units = sum(o["recognised_units"] for o in recognised)
        last_order = max((o["order_date"] for o in recognised), default=None)
        customer_rows.append(
            {
                "customer_id": customer,
                "customer_name": f"Customer {customer}",
                "country_code": country,
                "city": "Testville",
                "acquisition_channel": channel,
                "signup_date": pd.Timestamp("2025-11-01"),
                "signup_month": "2025-11",
                "has_purchased": bool(recognised),
                "first_order_date": min((o["order_date"] for o in recognised), default=pd.NaT),
                "last_order_date": last_order,
                "first_purchase_month": last_order.strftime("%Y-%m") if last_order else None,
                "total_orders": len(recognised),
                "total_units": units,
                "total_revenue": float(revenue),
                "average_order_value": float(revenue / len(recognised)) if recognised else np.nan,
                "repeat_customer": len(recognised) >= 2,
                "active_months": len({o["order_month"] for o in recognised}),
                "customer_lifetime_days": 60 if recognised else np.nan,
                "average_days_between_orders": 30.0 if len(recognised) >= 2 else np.nan,
                "days_since_first_order": 80 if recognised else np.nan,
                "days_since_last_order": float((pd.Timestamp("2026-03-20") - last_order).days)
                if last_order
                else np.nan,
                "analysis_end_date": pd.Timestamp("2026-03-20"),
            }
        )
    # Two customers who never purchased.
    for customer, country, channel in (("C4", "NL", "display"), ("C8", "IT", "organic_search")):
        customer_rows.append(
            {
                "customer_id": customer,
                "customer_name": f"Customer {customer}",
                "country_code": country,
                "city": "Testville",
                "acquisition_channel": channel,
                "signup_date": pd.Timestamp("2025-12-01"),
                "signup_month": "2025-12",
                "has_purchased": False,
                "first_order_date": pd.NaT,
                "last_order_date": pd.NaT,
                "first_purchase_month": None,
                "total_orders": 0,
                "total_units": 0,
                "total_revenue": 0.0,
                "average_order_value": np.nan,
                "repeat_customer": False,
                "active_months": 0,
                "customer_lifetime_days": np.nan,
                "average_days_between_orders": np.nan,
                "days_since_first_order": np.nan,
                "days_since_last_order": np.nan,
                "analysis_end_date": pd.Timestamp("2026-03-20"),
            }
        )

    campaign_rows = []
    for campaign_id, treatment_values, control_values in (
        ("CMP-001", [200.0, 180.0, 220.0, 160.0], [90.0, 110.0]),
        ("CMP-002", [50.0, 40.0, 60.0], [45.0, 55.0]),
    ):
        for index, value in enumerate(treatment_values):
            campaign_rows.append(
                {
                    "campaign_id": campaign_id,
                    "campaign_name": f"{campaign_id} name",
                    "channel": "email",
                    "objective": "retention",
                    "start_date": pd.Timestamp("2026-02-01"),
                    "end_date": pd.Timestamp("2026-02-28"),
                    "customer_id": f"{campaign_id}-T{index}",
                    "arm": "treatment",
                    "exposed": True,
                    "is_exposed_treatment": True,
                    "window_revenue": value,
                    "window_orders": 1,
                }
            )
        for index, value in enumerate(control_values):
            campaign_rows.append(
                {
                    "campaign_id": campaign_id,
                    "campaign_name": f"{campaign_id} name",
                    "channel": "email",
                    "objective": "retention",
                    "start_date": pd.Timestamp("2026-02-01"),
                    "end_date": pd.Timestamp("2026-02-28"),
                    "customer_id": f"{campaign_id}-C{index}",
                    "arm": "control",
                    "exposed": False,
                    "is_exposed_treatment": False,
                    "window_revenue": value,
                    "window_orders": 1,
                }
            )

    window = pd.DataFrame(
        [
            {
                "first_order_date": pd.Timestamp("2026-01-05"),
                "analysis_end_date": pd.Timestamp("2026-03-20"),
                "window_days": 86,
                "total_orders": len(orders),
            }
        ]
    )
    return AnalysisInputs(
        orders=pd.DataFrame(orders),
        order_lines=pd.DataFrame(lines),
        customers=pd.DataFrame(customer_rows),
        products=pd.DataFrame(),
        categories=pd.DataFrame(),
        daily=pd.DataFrame(),
        monthly=pd.DataFrame(),
        campaign_outcomes=pd.DataFrame(campaign_rows),
        window=window,
    )


@pytest.fixture(scope="session")
def presentation_analysis(presentation_inputs: AnalysisInputs) -> BusinessAnalysis:
    return analyse(presentation_inputs)

