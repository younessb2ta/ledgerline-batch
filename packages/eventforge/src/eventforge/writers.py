from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

from .generator import DayData
from .model import GENERATOR_VERSION, SCHEMA_VERSION

CSV_FIELDS: dict[str, list[str]] = {
    "customers.csv": ["customer_id", "customer_name", "email", "country", "created_at"],
    "products.csv": ["product_id", "product_name", "category", "list_price_cents"],
    "orders.csv": ["order_id", "customer_id", "order_ts", "order_status", "currency"],
    "order_items.csv": ["order_id", "product_id", "quantity", "unit_price_cents", "amount_cents"],
    "payments.csv": ["payment_id", "order_id", "amount_cents", "paid_ts", "status"],
    "returns.csv": ["return_id", "order_id", "product_id", "amount_cents", "returned_ts"],
}

TS_FIELDS: dict[str, str] = {
    "customers.csv": "created_at",
    "orders.csv": "order_ts",
    "payments.csv": "paid_ts",
    "returns.csv": "returned_ts",
    "events.jsonl": "event_ts",
}


def _timestamp_range(rows: list[dict], field_name: str | None) -> dict[str, str | None]:
    if not field_name:
        return {}
    values = sorted(str(row[field_name]) for row in rows if row.get(field_name))
    return {
        "min_ts": values[0] if values else None,
        "max_ts": values[-1] if values else None,
    }


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> dict:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: ("" if row.get(key) is None else row[key]) for key in fields})

    payload = buffer.getvalue().encode("utf-8")
    path.write_bytes(payload)
    return {
        "rows": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(),
        **_timestamp_range(rows, TS_FIELDS.get(path.name)),
    }


def _write_jsonl(path: Path, rows: list[dict]) -> dict:
    lines = [json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows]
    body = "\n".join(lines)
    payload = (body + "\n" if body else "").encode("utf-8")
    path.write_bytes(payload)
    return {
        "rows": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(),
        **_timestamp_range(rows, TS_FIELDS.get(path.name)),
    }


def _write_json(path: Path, obj: dict) -> dict:
    payload = (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return {"rows": 1, "sha256": hashlib.sha256(payload).hexdigest()}


def _incident_meta(incident: str, truncate_pct: float) -> dict:
    if incident == "none":
        return {"type": "none"}
    if incident == "truncated":
        return {"type": "truncated", "truncate_pct": truncate_pct}
    return {"type": incident}


def apply_incident(data: DayData, incident: str, truncate_pct: float) -> DayData:
    """Return a broken-but-plausible copy of the dataset.

    Every incident leaves the data *shape* valid so the ingestion schema gate can
    still pass. The truncation and staleness cases are exactly what the mart-layer
    volume and freshness tests exist to catch.
    """
    if incident == "truncated":
        keep = max(1, round(len(data.orders) * (1 - truncate_pct)))
        orders = sorted(data.orders, key=lambda row: (row["order_ts"], row["order_id"]))[:keep]
        keep_ids = {row["order_id"] for row in orders}
        return replace(
            data,
            orders=orders,
            order_items=[row for row in data.order_items if row["order_id"] in keep_ids],
            payments=[row for row in data.payments if row["order_id"] in keep_ids],
            returns=[row for row in data.returns if row["order_id"] in keep_ids],
            events=[event for event in data.events if event.order_id in keep_ids],
        )

    if incident == "duplicate_pk":
        count = max(1, round(len(data.orders) * 0.05))
        return replace(
            data,
            orders=data.orders + [dict(row) for row in data.orders[:count]],
        )

    # "schema_drift" is applied at write time by renaming a column.
    return replace(data)


def write_day(
    data: DayData,
    out_root: str | Path,
    *,
    incident: str = "none",
    truncate_pct: float = 0.6,
) -> Path:
    """Write one day of data plus manifest and ground truth. Returns the output directory."""
    out = Path(out_root) / data.day.isoformat()
    out.mkdir(parents=True, exist_ok=True)

    shaped = apply_incident(data, incident, truncate_pct)
    files: dict[str, dict] = {}

    files["customers.csv"] = _write_csv(
        out / "customers.csv",
        CSV_FIELDS["customers.csv"],
        [customer.to_dict() for customer in shaped.customers],
    )
    files["products.csv"] = _write_csv(
        out / "products.csv",
        CSV_FIELDS["products.csv"],
        [product.to_dict() for product in shaped.products],
    )
    files["orders.csv"] = _write_csv(out / "orders.csv", CSV_FIELDS["orders.csv"], shaped.orders)
    files["payments.csv"] = _write_csv(
        out / "payments.csv", CSV_FIELDS["payments.csv"], shaped.payments
    )
    files["returns.csv"] = _write_csv(
        out / "returns.csv", CSV_FIELDS["returns.csv"], shaped.returns
    )

    if incident == "schema_drift":
        fields = ["order_id", "product_id", "quantity", "unit_price", "amount_cents"]
        items = [
            {
                "order_id": row["order_id"],
                "product_id": row["product_id"],
                "quantity": row["quantity"],
                "unit_price": row["unit_price_cents"],
                "amount_cents": row["amount_cents"],
            }
            for row in shaped.order_items
        ]
        files["order_items.csv"] = _write_csv(out / "order_items.csv", fields, items)
    else:
        files["order_items.csv"] = _write_csv(
            out / "order_items.csv", CSV_FIELDS["order_items.csv"], shaped.order_items
        )

    files["events.jsonl"] = _write_jsonl(
        out / "events.jsonl", [event.to_dict() for event in shaped.events]
    )

    ground_truth = dict(shaped.ground_truth)
    ground_truth["incident"] = _incident_meta(incident, truncate_pct)
    files["ground_truth.json"] = _write_json(out / "ground_truth.json", ground_truth)

    manifest = {
        "batch_id": shaped.ground_truth["batch_id"],
        "day": data.day.isoformat(),
        "seed": shaped.ground_truth["seed"],
        "generator_version": GENERATOR_VERSION,
        "schema_version": SCHEMA_VERSION,
        "incident": _incident_meta(incident, truncate_pct),
        "files": files,
        "totals": {
            "orders": len(shaped.orders),
            "order_items": len(shaped.order_items),
            "payments": len(shaped.payments),
            "returns": len(shaped.returns),
            "events": len(shaped.events),
        },
    }
    _write_json(out / "manifest.json", manifest)
    return out
