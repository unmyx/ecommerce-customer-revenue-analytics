"""Single source of truth for raw table shape and load order."""

from __future__ import annotations

from dataclasses import dataclass

RAW_SCHEMA = "raw"


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    generated_columns: tuple[str, ...] = ()
    nullable_columns: tuple[str, ...] = ()

    @property
    def qualified_name(self) -> str:
        return f"{RAW_SCHEMA}.{self.name}"

    @property
    def csv_name(self) -> str:
        return f"{self.name}.csv"


TABLES: dict[str, TableSpec] = {
    "customers": TableSpec(
        name="customers",
        columns=(
            "customer_id",
            "email",
            "first_name",
            "last_name",
            "country_code",
            "city",
            "signup_date",
            "acquisition_channel",
            "created_at",
        ),
        primary_key=("customer_id",),
    ),
    "products": TableSpec(
        name="products",
        columns=(
            "product_id",
            "sku",
            "product_name",
            "category",
            "subcategory",
            "brand",
            "unit_price",
            "unit_cost",
            "launch_date",
            "is_active",
        ),
        primary_key=("product_id",),
    ),
    "marketing_campaigns": TableSpec(
        name="marketing_campaigns",
        columns=(
            "campaign_id",
            "campaign_name",
            "channel",
            "objective",
            "target_audience",
            "start_date",
            "end_date",
            "budget_eur",
            "created_at",
        ),
        primary_key=("campaign_id",),
    ),
    "campaign_assignments": TableSpec(
        name="campaign_assignments",
        columns=(
            "assignment_id",
            "campaign_id",
            "customer_id",
            "assigned_at",
            "arm",
            "exposed",
            "assignment_method",
        ),
        primary_key=("assignment_id",),
    ),
    "orders": TableSpec(
        name="orders",
        columns=(
            "order_id",
            "customer_id",
            "order_ts",
            "order_status",
            "sales_channel",
            "campaign_id",
            "items_subtotal",
            "discount_amount",
            "shipping_amount",
            "tax_amount",
            "currency_code",
            "shipping_country_code",
        ),
        primary_key=("order_id",),
        generated_columns=("net_revenue", "order_total"),
        nullable_columns=("campaign_id",),
    ),
    "order_items": TableSpec(
        name="order_items",
        columns=(
            "order_item_id",
            "order_id",
            "product_id",
            "quantity",
            "unit_price",
            "unit_cost",
            "line_discount",
        ),
        primary_key=("order_item_id",),
        generated_columns=("line_net_amount",),
    ),
    "payments": TableSpec(
        name="payments",
        columns=(
            "payment_id",
            "order_id",
            "payment_method",
            "payment_status",
            "amount",
            "refunded_amount",
            "paid_at",
            "provider_reference",
        ),
        primary_key=("payment_id",),
    ),
}

# Parents before children so foreign keys are satisfied during COPY.
LOAD_ORDER: tuple[str, ...] = (
    "customers",
    "products",
    "marketing_campaigns",
    "campaign_assignments",
    "orders",
    "order_items",
    "payments",
)

# Reverse order for truncation; the loader uses TRUNCATE ... CASCADE instead.
DELETE_ORDER: tuple[str, ...] = tuple(reversed(LOAD_ORDER))

