from __future__ import annotations

import hashlib
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from .ids import event_id
from .model import (
    CURRENCY,
    GENERATOR_VERSION,
    SCHEMA_VERSION,
    Customer,
    Event,
    Product,
    iso_utc,
)

FIRST_NAMES = (
    "Amina",
    "Bruno",
    "Chen",
    "Dara",
    "Elif",
    "Farid",
    "Greta",
    "Hugo",
    "Ines",
    "Jonas",
    "Kaito",
    "Lena",
    "Mateo",
    "Nadia",
    "Omar",
    "Priya",
    "Quinn",
    "Rosa",
    "Sven",
    "Tara",
)

LAST_NAMES = (
    "Okafor",
    "Silva",
    "Nakamura",
    "Haddad",
    "Novak",
    "Rossi",
    "Kowalski",
    "Dubois",
    "Andersen",
    "Mensah",
    "Iqbal",
    "Fischer",
    "Moreau",
    "Petrov",
    "Costa",
    "Yilmaz",
)

COUNTRIES = ("US", "DE", "FR", "BR", "JP", "IN", "CA", "NL", "ES", "SE")

CATEGORIES: dict[str, tuple[str, ...]] = {
    "electronics": ("Headphones", "Monitor", "Keyboard", "Mouse", "Webcam", "Speaker"),
    "home": ("Lamp", "Kettle", "Chair", "Shelf", "Rug", "Clock"),
    "outdoors": ("Tent", "Backpack", "Bottle", "Lantern", "Compass", "Hammock"),
    "books": ("Notebook", "Atlas", "Almanac", "Anthology", "Guidebook", "Journal"),
}

ADJECTIVES = (
    "Aurora",
    "Nimbus",
    "Quartz",
    "Ember",
    "Atlas",
    "Pixel",
    "Cobalt",
    "Vertex",
    "Lumen",
    "Onyx",
)


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 42
    start_date: date = date(2026, 11, 1)
    days: int = 1
    n_customers: int = 500
    n_products: int = 200
    orders_per_day: int = 800
    max_lines: int = 4
    refund_rate: float = 0.03
    cancel_rate: float = 0.04
    backdate_days: int = 0


@dataclass
class DayData:
    day: date
    customers: list[Customer] = field(default_factory=list)
    products: list[Product] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    order_items: list[dict] = field(default_factory=list)
    payments: list[dict] = field(default_factory=list)
    returns: list[dict] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    ground_truth: dict = field(default_factory=dict)


def build_dimensions(cfg: GeneratorConfig) -> tuple[list[Customer], list[Product]]:
    """Customers and products are stable for a seed, independent of the day."""
    rng = random.Random(f"{cfg.seed}:dimensions")

    products: list[Product] = []
    for i in range(cfg.n_products):
        category = rng.choice(tuple(CATEGORIES))
        noun = rng.choice(CATEGORIES[category])
        products.append(
            Product(
                product_id=f"prd_{i + 1:05d}",
                product_name=f"{rng.choice(ADJECTIVES)} {noun}",
                category=category,
                list_price_cents=rng.randrange(499, 20_001),
            )
        )

    epoch = datetime(2023, 1, 1, tzinfo=UTC)
    customers: list[Customer] = []
    for i in range(cfg.n_customers):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        created = epoch + timedelta(
            days=rng.randrange(0, 900),
            seconds=rng.randrange(0, 86_400),
        )
        customers.append(
            Customer(
                customer_id=f"cus_{i + 1:05d}",
                customer_name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}{i + 1}@example.com",
                country=rng.choice(COUNTRIES),
                created_at=iso_utc(created),
            )
        )

    return customers, products


def generate_day(cfg: GeneratorConfig, day: date) -> DayData:
    customers, products = build_dimensions(cfg)
    rng = random.Random(f"{cfg.seed}:{day.isoformat()}")

    day_start = datetime.combine(day, time(0, 0), tzinfo=UTC)
    shift = timedelta(days=cfg.backdate_days)

    data = DayData(day=day, customers=customers, products=products)
    event_seq = 0

    for order_seq in range(1, cfg.orders_per_day + 1):
        order_id = f"ord_{day:%Y%m%d}_{order_seq:06d}"
        customer = rng.choice(customers)
        order_ts = day_start + timedelta(seconds=rng.randrange(86_400)) - shift

        line_products = rng.sample(products, rng.randint(1, cfg.max_lines))
        total_cents = 0
        line_rows: list[dict] = []

        for product in line_products:
            quantity = rng.randint(1, 3)
            amount_cents = quantity * product.list_price_cents
            total_cents += amount_cents

            row = {
                "order_id": order_id,
                "product_id": product.product_id,
                "quantity": quantity,
                "unit_price_cents": product.list_price_cents,
                "amount_cents": amount_cents,
            }
            data.order_items.append(row)
            line_rows.append(row)

            event_seq += 1
            data.events.append(
                Event(
                    event_id=event_id(cfg.seed, day, event_seq),
                    event_type="order_created",
                    event_ts=iso_utc(order_ts),
                    order_id=order_id,
                    customer_id=customer.customer_id,
                    product_id=product.product_id,
                    quantity=quantity,
                    unit_price_cents=product.list_price_cents,
                    amount_cents=amount_cents,
                )
            )

        roll = rng.random()
        if roll < cfg.cancel_rate:
            status = "cancelled"
            event_seq += 1
            data.events.append(
                Event(
                    event_id=event_id(cfg.seed, day, event_seq),
                    event_type="order_cancelled",
                    event_ts=iso_utc(order_ts + timedelta(minutes=1)),
                    order_id=order_id,
                    customer_id=customer.customer_id,
                    product_id=None,
                    quantity=0,
                    unit_price_cents=0,
                    amount_cents=0,
                )
            )
        else:
            status = "refunded" if roll < cfg.cancel_rate + cfg.refund_rate else "paid"
            paid_ts = order_ts + timedelta(seconds=rng.randint(30, 3600))

            data.payments.append(
                {
                    "payment_id": f"pay_{day:%Y%m%d}_{order_seq:06d}",
                    "order_id": order_id,
                    "amount_cents": total_cents,
                    "paid_ts": iso_utc(paid_ts),
                    "status": "refunded" if status == "refunded" else "succeeded",
                }
            )

            event_seq += 1
            data.events.append(
                Event(
                    event_id=event_id(cfg.seed, day, event_seq),
                    event_type="order_paid",
                    event_ts=iso_utc(paid_ts),
                    order_id=order_id,
                    customer_id=customer.customer_id,
                    product_id=None,
                    quantity=0,
                    unit_price_cents=0,
                    amount_cents=total_cents,
                )
            )

            if status == "refunded":
                full_refund = rng.random() < 0.5
                if full_refund:
                    refund_amount = total_cents
                    refund_product = None
                else:
                    line = rng.choice(line_rows)
                    refund_amount = int(line["amount_cents"])
                    refund_product = str(line["product_id"])

                returned_ts = paid_ts + timedelta(days=rng.randint(1, 14))
                data.returns.append(
                    {
                        "return_id": f"ret_{day:%Y%m%d}_{order_seq:06d}",
                        "order_id": order_id,
                        "product_id": refund_product,
                        "amount_cents": refund_amount,
                        "returned_ts": iso_utc(returned_ts),
                    }
                )

                event_seq += 1
                data.events.append(
                    Event(
                        event_id=event_id(cfg.seed, day, event_seq),
                        event_type="refund_issued",
                        event_ts=iso_utc(returned_ts),
                        order_id=order_id,
                        customer_id=customer.customer_id,
                        product_id=refund_product,
                        quantity=0,
                        unit_price_cents=0,
                        amount_cents=refund_amount,
                    )
                )

        data.orders.append(
            {
                "order_id": order_id,
                "customer_id": customer.customer_id,
                "order_ts": iso_utc(order_ts),
                "order_status": status,
                "currency": CURRENCY,
            }
        )

    data.events.sort(key=lambda e: (e.event_ts, e.event_id))
    data.orders.sort(key=lambda o: (o["order_ts"], o["order_id"]))
    data.ground_truth = _build_ground_truth(cfg, day, data)
    return data


def _build_ground_truth(cfg: GeneratorConfig, day: date, data: DayData) -> dict:
    per_customer: defaultdict[str, int] = defaultdict(int)
    revenue_by_product: defaultdict[str, int] = defaultdict(int)

    for event in data.events:
        if event.event_type == "order_paid":
            per_customer[event.customer_id] += event.amount_cents
        elif event.event_type == "refund_issued":
            per_customer[event.customer_id] -= event.amount_cents

    # Revenue by product only counts orders that were actually paid for.
    # Cancelled orders never become revenue, so they must not appear here.
    paid_order_ids = {
        row["order_id"] for row in data.orders if row["order_status"] in ("paid", "refunded")
    }
    lines_by_order: defaultdict[str, list[dict]] = defaultdict(list)
    for line in data.order_items:
        lines_by_order[line["order_id"]].append(line)
        if line["order_id"] in paid_order_ids:
            revenue_by_product[str(line["product_id"])] += line["amount_cents"]

    for return_row in data.returns:
        product_id = return_row["product_id"]
        if product_id:
            revenue_by_product[str(product_id)] -= return_row["amount_cents"]
        else:
            # Full refund: allocate the refund back across every line in the order.
            for line in lines_by_order[return_row["order_id"]]:
                revenue_by_product[str(line["product_id"])] -= line["amount_cents"]

    counts = Counter(event.event_type for event in data.events)
    ids = sorted(event.event_id for event in data.events)

    return {
        "batch_id": f"{day:%Y%m%d}-{cfg.seed}",
        "seed": cfg.seed,
        "day": day.isoformat(),
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "event_counts": dict(sorted(counts.items())),
        "total_events": len(data.events),
        "distinct_event_ids": len(set(ids)),
        "event_id_sha256": hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest(),
        "per_customer_balance_cents": dict(sorted(per_customer.items())),
        "revenue_by_product_cents": dict(sorted(revenue_by_product.items())),
        "total_revenue_cents": sum(per_customer.values()),
        "orders": len(data.orders),
        "order_items": len(data.order_items),
        "payments": len(data.payments),
        "returns": len(data.returns),
    }


def generate_events(cfg: GeneratorConfig):
    """Yield events for every configured day, in generation order."""
    for offset in range(cfg.days):
        day = cfg.start_date + timedelta(days=offset)
        yield from generate_day(cfg, day).events
