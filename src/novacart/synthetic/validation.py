"""Post-generation integrity checks run in memory before anything is written."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from novacart.synthetic import reference
from novacart.synthetic.config import GenerationConfig
from novacart.synthetic.models import TABLES


class DataValidationError(RuntimeError):
    """Raised when generated data violates an integrity rule."""

    def __init__(self, report: ValidationReport) -> None:
        failures = ", ".join(issue.check_id for issue in report.errors)
        super().__init__(f"Generated dataset failed {len(report.errors)} check(s): {failures}")
        self.report = report


@dataclass(frozen=True)
class ValidationIssue:
    check_id: str
    description: str
    failing_rows: int
    severity: str = "error"
    sample: tuple[str, ...] = ()


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(
        self,
        check_id: str,
        description: str,
        failing: pd.Series | np.ndarray | int,
        *,
        severity: str = "error",
        sample: pd.Series | None = None,
    ) -> None:
        if isinstance(failing, (int, np.integer)):
            count = int(failing)
        else:
            count = int(np.asarray(failing).sum())
        sample_values: tuple[str, ...] = ()
        if count and sample is not None:
            sample_values = tuple(str(value) for value in sample.head(5).tolist())
        self.issues.append(
            ValidationIssue(
                check_id=check_id,
                description=description,
                failing_rows=count,
                severity=severity,
                sample=sample_values,
            )
        )

    @property
    def errors(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error" and issue.failing_rows]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning" and issue.failing_rows]

    @property
    def passed(self) -> bool:
        return not self.errors

    def summary(self) -> dict[str, int]:
        return {
            "checks": len(self.issues),
            "failures": len(self.errors),
            "warnings": len(self.warnings),
        }

    def raise_if_failed(self) -> None:
        if not self.passed:
            raise DataValidationError(self)


def _check_unique(
    report: ValidationReport, frame: pd.DataFrame, columns: tuple[str, ...], name: str
) -> None:
    if frame.empty:
        return
    duplicated = frame.duplicated(subset=list(columns), keep="first")
    report.add(
        f"{name}_duplicate",
        f"{name}: {', '.join(columns)} must be unique",
        duplicated,
        sample=frame.loc[duplicated, columns[0]],
    )


def _check_reference(
    report: ValidationReport,
    child: pd.DataFrame,
    child_column: str,
    parent: pd.DataFrame,
    parent_column: str,
    name: str,
) -> None:
    if child.empty:
        return
    missing = ~child[child_column].isin(set(parent[parent_column]))
    report.add(
        f"{name}_orphan",
        f"{name}: {child_column} must exist in {parent_column}",
        missing,
        sample=child.loc[missing, child_column],
    )


def validate_dataset(
    frames: dict[str, pd.DataFrame], config: GenerationConfig
) -> ValidationReport:
    report = ValidationReport()
    customers = frames["customers"]
    products = frames["products"]
    campaigns = frames["marketing_campaigns"]
    assignments = frames["campaign_assignments"]
    orders = frames["orders"]
    items = frames["order_items"]
    payments = frames["payments"]

    window_start = pd.Timestamp(config.start_date)
    window_end = pd.Timestamp(config.end_date)

    for key, spec in TABLES.items():
        frame = frames[key]
        missing_columns = set(spec.columns) - set(frame.columns)
        report.add(
            f"{key}_columns",
            f"{key}: expected columns are present",
            len(missing_columns),
        )
        _check_unique(report, frame, spec.primary_key, key)
        required = [c for c in spec.columns if c not in spec.nullable_columns]
        report.add(
            f"{key}_nulls",
            f"{key}: no nulls in required columns",
            frame[required].isna().any(axis=1),
            sample=frame[spec.primary_key[0]],
        )

    # customers
    _check_unique(report, customers, ("email",), "customers_email")
    signup = pd.to_datetime(customers["signup_date"])
    report.add(
        "customers_signup_window",
        "Signup dates fall inside the declared acquisition window",
        (signup < pd.Timestamp(config.first_signup_date)) | (signup > window_end),
        sample=customers["customer_id"],
    )
    report.add(
        "customers_channel_domain",
        "Acquisition channels are known values",
        ~customers["acquisition_channel"].isin(set(reference.ACQUISITION_CHANNELS)),
        sample=customers["customer_id"],
    )

    # products
    _check_unique(report, products, ("sku",), "products_sku")
    report.add(
        "products_price_positive",
        "Product prices are positive",
        products["unit_price"] <= 0,
        sample=products["product_id"],
    )
    report.add(
        "products_cost_above_price",
        "Product cost does not exceed the list price",
        products["unit_cost"] > products["unit_price"],
        sample=products["product_id"],
    )
    report.add(
        "products_launch_after_window",
        "Product launch dates are not after the analysis window",
        pd.to_datetime(products["launch_date"]) > window_end,
        sample=products["product_id"],
    )

    # campaigns and assignments
    report.add(
        "campaigns_window",
        "Campaign windows fall inside the analysis window",
        (pd.to_datetime(campaigns["start_date"]) < window_start)
        | (pd.to_datetime(campaigns["end_date"]) > window_end),
        sample=campaigns["campaign_id"],
    )
    _check_unique(report, assignments, ("campaign_id", "customer_id"), "assignments_member")
    _check_reference(report, assignments, "campaign_id", campaigns, "campaign_id", "assignments")
    _check_reference(report, assignments, "customer_id", customers, "customer_id", "assignments")
    report.add(
        "assignments_control_exposed",
        "Control arm members are never exposed",
        (assignments["arm"] == "control") & assignments["exposed"],
        sample=assignments["assignment_id"],
    )
    report.add(
        "assignments_arm_domain",
        "Assignment arms are treatment or control",
        ~assignments["arm"].isin({"treatment", "control"}),
        sample=assignments["assignment_id"],
    )

    # orders
    _check_reference(report, orders, "customer_id", customers, "customer_id", "orders")
    campaign_reference = campaigns.loc[
        campaigns["campaign_id"].isin(set(orders["campaign_id"].dropna())), "campaign_id"
    ]
    attributed = orders[orders["campaign_id"].notna()]
    report.add(
        "orders_campaign_orphan",
        "Attributed orders reference a known campaign",
        ~attributed["campaign_id"].isin(set(campaign_reference)),
        sample=attributed["order_id"],
    )
    order_ts = pd.to_datetime(orders["order_ts"])
    report.add(
        "orders_window",
        "Order timestamps fall inside the analysis window",
        (order_ts < window_start) | (order_ts > window_end + pd.Timedelta(days=1)),
        sample=orders["order_id"],
    )
    signup_by_customer = (
        customers.drop_duplicates("customer_id").set_index("customer_id")["signup_date"]
    )
    mapped_signup = pd.to_datetime(orders["customer_id"].map(signup_by_customer))
    report.add(
        "orders_before_signup",
        "Orders are not placed before the customer signed up",
        (order_ts.dt.normalize() < mapped_signup).fillna(True),
        sample=orders["order_id"],
    )
    report.add(
        "orders_negative_amounts",
        "Order amounts are non-negative and discounts do not exceed the subtotal",
        (orders[["items_subtotal", "discount_amount", "shipping_amount", "tax_amount"]] < 0).any(
            axis=1
        )
        | (orders["discount_amount"] > orders["items_subtotal"]),
        sample=orders["order_id"],
    )
    report.add(
        "orders_status_domain",
        "Order statuses are known values",
        ~orders["order_status"].isin(set(reference.ORDER_STATUS_WEIGHTS)),
        sample=orders["order_id"],
    )

    # order items
    _check_reference(report, items, "order_id", orders, "order_id", "order_items")
    _check_reference(report, items, "product_id", products, "product_id", "order_items")
    _check_unique(report, items, ("order_id", "product_id"), "order_items_order_product")
    report.add(
        "order_items_values",
        "Item quantities and prices are positive and discounts are valid",
        (items["quantity"] <= 0)
        | (items["unit_price"] <= 0)
        | (items["unit_cost"] > items["unit_price"])
        | (items["line_discount"] < 0)
        | (items["line_discount"] > items["quantity"] * items["unit_price"]),
        sample=items["order_item_id"],
    )
    launch_by_product = (
        products.drop_duplicates("product_id").set_index("product_id")["launch_date"]
    )
    item_order_ts = items["order_id"].map(
        orders.drop_duplicates("order_id").set_index("order_id")["order_ts"]
    )
    report.add(
        "order_items_before_launch",
        "Products are not sold before their launch date",
        pd.to_datetime(items["product_id"].map(launch_by_product)).to_numpy()
        > pd.to_datetime(item_order_ts).dt.normalize().to_numpy(),
        sample=items["order_item_id"],
    )

    # order header reconciliation against the lines
    # Cross-table reconciliation needs a unique order key; a duplicate primary
    # key is already reported above, so skip rather than raise a pandas error.
    if not orders["order_id"].duplicated().any():
        line_totals = (
            items.assign(gross=items["quantity"] * items["unit_price"])
            .groupby("order_id", sort=False)
            .agg(gross_sum=("gross", "sum"), discount_sum=("line_discount", "sum"))
        )
        reconciled = orders.set_index("order_id").join(line_totals, how="left")
        report.add(
            "orders_subtotal_reconciliation",
            "Order items_subtotal equals the sum of its line gross amounts",
            (reconciled["gross_sum"].round(2) - reconciled["items_subtotal"]).abs() > 0.011,
            sample=pd.Series(reconciled.index),
        )
        report.add(
            "orders_discount_reconciliation",
            "Order discount_amount equals the sum of its line discounts",
            (reconciled["discount_sum"].round(2) - reconciled["discount_amount"]).abs() > 0.011,
            sample=pd.Series(reconciled.index),
        )

    # payments
    _check_unique(report, payments, ("order_id",), "payments_order")
    _check_unique(report, payments, ("provider_reference",), "payments_reference")
    _check_reference(report, payments, "order_id", orders, "order_id", "payments")
    expected_total = (
        orders["items_subtotal"]
        - orders["discount_amount"]
        + orders["shipping_amount"]
        + orders["tax_amount"]
    ).round(2)
    payment_totals = (
        payments.drop_duplicates("order_id")
        .set_index("order_id")["amount"]
        .reindex(orders["order_id"].to_numpy())
        .to_numpy()
    )
    report.add(
        "payments_amount_mismatch",
        "Payment amounts equal the order total",
        np.abs(payment_totals - expected_total.to_numpy()) > 0.011,
        sample=orders["order_id"],
    )
    report.add(
        "payments_missing_order",
        "Every order has a payment record",
        payments["order_id"].nunique() != orders["order_id"].nunique(),
    )
    actual_status = payments.drop_duplicates("order_id").set_index("order_id")["payment_status"]
    status_expectation = orders.drop_duplicates("order_id").set_index("order_id")["order_status"].map(
        reference.PAYMENT_STATUS_BY_ORDER_STATUS
    )
    report.add(
        "payments_status_mismatch",
        "Payment status matches the order status",
        (actual_status.reindex(status_expectation.index) != status_expectation).fillna(True),
        sample=pd.Series(status_expectation.index),
    )
    report.add(
        "payments_refund_above_amount",
        "Refunded amounts never exceed the settled amount",
        payments["refunded_amount"] > payments["amount"],
        sample=payments["payment_id"],
    )

    # scale checks
    report.add(
        "scale_orders",
        "Order volume is within 30% of the configured target",
        int(abs(len(orders) - config.target_orders) > 0.30 * config.target_orders),
    )
    report.add(
        "scale_customers",
        "Customer count matches the configuration",
        int(len(customers) != config.n_customers),
    )
    report.add(
        "scale_products",
        "Product count matches the configuration",
        int(len(products) != config.n_products),
    )
    report.add(
        "scale_campaigns",
        "Campaign count matches the configuration",
        int(len(campaigns) != config.n_campaigns),
    )
    repeat_rate = (
        orders.groupby("customer_id")["order_id"].count().ge(2).mean() if len(orders) else 0.0
    )
    report.add(
        "behaviour_repeat_purchase_rate",
        "Repeat purchase rate is within a plausible 25%-75% band",
        int(not 0.25 <= float(repeat_rate) <= 0.75),
        severity="warning",
    )
    return report

