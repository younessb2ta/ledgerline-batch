"""BigQuery table contracts shared by the loader and the validation gate."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # STRING | INT64 | TIMESTAMP | DATE | BOOL
    mode: str = "NULLABLE"


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: tuple[Column, ...]
    source: str | None = None
    partition_field: str | None = None
    clustering: tuple[str, ...] = ()


RAW_TABLES: dict[str, TableSpec] = {
    "raw_customers": TableSpec(
        name="raw_customers",
        source="customers.csv",
        columns=(
            Column("customer_id", "STRING", "REQUIRED"),
            Column("customer_name", "STRING"),
            Column("email", "STRING"),
            Column("country", "STRING"),
            Column("created_at", "TIMESTAMP"),
        ),
    ),
    "raw_products": TableSpec(
        name="raw_products",
        source="products.csv",
        columns=(
            Column("product_id", "STRING", "REQUIRED"),
            Column("product_name", "STRING"),
            Column("category", "STRING"),
            Column("list_price_cents", "INT64"),
        ),
    ),
    "raw_orders": TableSpec(
        name="raw_orders",
        source="orders.csv",
        partition_field="order_ts",
        clustering=("customer_id",),
        columns=(
            Column("order_id", "STRING", "REQUIRED"),
            Column("customer_id", "STRING", "REQUIRED"),
            Column("order_ts", "TIMESTAMP", "REQUIRED"),
            Column("order_status", "STRING"),
            Column("currency", "STRING"),
        ),
    ),
    "raw_order_items": TableSpec(
        name="raw_order_items",
        source="order_items.csv",
        clustering=("order_id",),
        columns=(
            Column("order_id", "STRING", "REQUIRED"),
            Column("product_id", "STRING", "REQUIRED"),
            Column("quantity", "INT64"),
            Column("unit_price_cents", "INT64"),
            Column("amount_cents", "INT64"),
        ),
    ),
    "raw_payments": TableSpec(
        name="raw_payments",
        source="payments.csv",
        partition_field="paid_ts",
        clustering=("order_id",),
        columns=(
            Column("payment_id", "STRING", "REQUIRED"),
            Column("order_id", "STRING", "REQUIRED"),
            Column("amount_cents", "INT64"),
            Column("paid_ts", "TIMESTAMP"),
            Column("status", "STRING"),
        ),
    ),
    "raw_returns": TableSpec(
        name="raw_returns",
        source="returns.csv",
        partition_field="returned_ts",
        columns=(
            Column("return_id", "STRING", "REQUIRED"),
            Column("order_id", "STRING", "REQUIRED"),
            Column("product_id", "STRING"),
            Column("amount_cents", "INT64"),
            Column("returned_ts", "TIMESTAMP"),
        ),
    ),
}

LOAD_AUDIT = TableSpec(
    name="load_audit",
    partition_field="loaded_at",
    clustering=("batch_id",),
    columns=(
        Column("batch_id", "STRING", "REQUIRED"),
        Column("day", "DATE"),
        Column("table_name", "STRING", "REQUIRED"),
        Column("source_sha256", "STRING"),
        Column("row_count", "INT64"),
        Column("status", "STRING"),
        Column("loaded_at", "TIMESTAMP"),
        Column("message", "STRING"),
    ),
)

DQ_RESULTS = TableSpec(
    name="dq_results",
    partition_field="checked_at",
    clustering=("batch_id",),
    columns=(
        Column("run_id", "STRING"),
        Column("batch_id", "STRING"),
        Column("checked_at", "TIMESTAMP"),
        Column("layer", "STRING"),
        Column("table_name", "STRING"),
        Column("expectation", "STRING"),
        Column("success", "BOOL"),
        Column("observed", "STRING"),
        Column("expected", "STRING"),
        Column("detail", "STRING"),
    ),
)

OPS_TABLES: dict[str, TableSpec] = {
    LOAD_AUDIT.name: LOAD_AUDIT,
    DQ_RESULTS.name: DQ_RESULTS,
}

# Primary keys used by the validation gate and by dbt staging dedupe.
PRIMARY_KEYS: dict[str, str] = {
    "raw_customers": "customer_id",
    "raw_products": "product_id",
    "raw_orders": "order_id",
    "raw_order_items": "order_id",  # composite in reality; checked as pair below
    "raw_payments": "payment_id",
    "raw_returns": "return_id",
}

COMPOSITE_KEYS: dict[str, tuple[str, ...]] = {
    "raw_order_items": ("order_id", "product_id"),
}
