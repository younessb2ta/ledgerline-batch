from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

GENERATOR_VERSION = "0.1.0"
SCHEMA_VERSION = 1
CURRENCY = "USD"

EVENT_TYPES = (
    "order_created",
    "order_paid",
    "order_cancelled",
    "refund_issued",
)


def iso_utc(dt: datetime) -> str:
    """ISO-8601 with millisecond precision and a Z suffix (lexicographically sortable)."""
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class Customer:
    customer_id: str
    customer_name: str
    email: str
    country: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "email": self.email,
            "country": self.country,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class Product:
    product_id: str
    product_name: str
    category: str
    list_price_cents: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_id": self.product_id,
            "product_name": self.product_name,
            "category": self.category,
            "list_price_cents": self.list_price_cents,
        }


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    event_type: str
    event_ts: str
    order_id: str
    customer_id: str
    product_id: str | None
    quantity: int
    unit_price_cents: int
    amount_cents: int
    currency: str = CURRENCY
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_ts": self.event_ts,
            "order_id": self.order_id,
            "customer_id": self.customer_id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "unit_price_cents": self.unit_price_cents,
            "amount_cents": self.amount_cents,
            "currency": self.currency,
            "schema_version": self.schema_version,
        }
