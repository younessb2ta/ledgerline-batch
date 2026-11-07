from __future__ import annotations

import csv
import hashlib
import json
from datetime import date

import pytest

from eventforge.generator import GeneratorConfig, generate_day
from eventforge.writers import apply_incident, write_day

SMALL = GeneratorConfig(
    seed=7,
    start_date=date(2026, 11, 1),
    days=1,
    n_customers=25,
    n_products=12,
    orders_per_day=40,
    max_lines=3,
)


@pytest.fixture(scope="module")
def day_data():
    return generate_day(SMALL, SMALL.start_date)


def _manifest(path):
    return json.loads((path / "manifest.json").read_text())


def test_same_seed_produces_identical_manifests(tmp_path):
    first = write_day(generate_day(SMALL, SMALL.start_date), tmp_path / "a")
    second = write_day(generate_day(SMALL, SMALL.start_date), tmp_path / "b")

    manifest_a = _manifest(first)
    manifest_b = _manifest(second)

    assert manifest_a["files"] == manifest_b["files"]
    assert manifest_a["batch_id"] == manifest_b["batch_id"]
    assert manifest_a["totals"] == manifest_b["totals"]


def test_different_seeds_produce_different_data(tmp_path):
    other = GeneratorConfig(**{**SMALL.__dict__, "seed": 8})
    first = write_day(generate_day(SMALL, SMALL.start_date), tmp_path / "a")
    second = write_day(generate_day(other, SMALL.start_date), tmp_path / "b")

    assert (
        _manifest(first)["files"]["orders.csv"]["sha256"]
        != (_manifest(second)["files"]["orders.csv"]["sha256"])
    )


def test_manifest_hashes_and_rows_match_files(tmp_path):
    out = write_day(generate_day(SMALL, SMALL.start_date), tmp_path)
    manifest = _manifest(out)

    for name, meta in manifest["files"].items():
        path = out / name
        assert path.exists(), name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == meta["sha256"], name

        if name.endswith(".csv"):
            rows = sum(1 for _ in path.open()) - 1
        elif name.endswith(".jsonl"):
            rows = sum(1 for _ in path.open())
        else:
            continue
        assert rows == meta["rows"], name


def test_event_ids_are_unique(day_data):
    ids = [event.event_id for event in day_data.events]
    assert len(ids) == len(set(ids))
    assert day_data.ground_truth["distinct_event_ids"] == len(ids)
    assert day_data.ground_truth["event_id_sha256"]


def test_balances_reconcile_from_events(day_data):
    computed: dict[str, int] = {}
    for event in day_data.events:
        if event.event_type == "order_paid":
            computed[event.customer_id] = computed.get(event.customer_id, 0) + event.amount_cents
        elif event.event_type == "refund_issued":
            computed[event.customer_id] = computed.get(event.customer_id, 0) - event.amount_cents

    assert computed == day_data.ground_truth["per_customer_balance_cents"]


def test_revenue_rollups_agree(day_data):
    truth = day_data.ground_truth
    assert sum(truth["revenue_by_product_cents"].values()) == truth["total_revenue_cents"]


def test_truncated_incident_drops_whole_orders(day_data):
    truncated = apply_incident(day_data, "truncated", 0.6)

    assert len(truncated.orders) < len(day_data.orders)
    assert len(truncated.order_items) < len(day_data.order_items)

    kept_order_ids = {row["order_id"] for row in truncated.orders}
    assert kept_order_ids
    assert {event.order_id for event in truncated.events} <= kept_order_ids

    # Original dataset must not be mutated.
    assert len(day_data.orders) == SMALL.orders_per_day


def test_duplicate_pk_incident_creates_duplicates(day_data):
    duplicated = apply_incident(day_data, "duplicate_pk", 0.0)
    order_ids = [row["order_id"] for row in duplicated.orders]

    assert len(duplicated.orders) > len(day_data.orders)
    assert len(order_ids) != len(set(order_ids))


def test_schema_drift_renames_a_column(tmp_path):
    out = write_day(
        generate_day(SMALL, SMALL.start_date),
        tmp_path,
        incident="schema_drift",
    )
    with (out / "order_items.csv").open(newline="") as handle:
        header = next(csv.reader(handle))

    assert "unit_price" in header
    assert "unit_price_cents" not in header


def test_stale_incident_backdates_event_time(tmp_path):
    fresh_cfg = SMALL
    stale_cfg = GeneratorConfig(**{**SMALL.__dict__, "backdate_days": 3})

    fresh = write_day(generate_day(fresh_cfg, fresh_cfg.start_date), tmp_path / "fresh")
    stale = write_day(generate_day(stale_cfg, stale_cfg.start_date), tmp_path / "stale")

    fresh_max = _manifest(fresh)["files"]["events.jsonl"]["max_ts"]
    stale_max = _manifest(stale)["files"]["events.jsonl"]["max_ts"]
    assert stale_max < fresh_max


def test_ground_truth_survives_truncation(tmp_path):
    data = generate_day(SMALL, SMALL.start_date)
    out = write_day(data, tmp_path, incident="truncated", truncate_pct=0.9)

    manifest = _manifest(out)
    truth = json.loads((out / "ground_truth.json").read_text())

    assert manifest["totals"]["orders"] < truth["orders"]
    assert truth["incident"] == {"type": "truncated", "truncate_pct": 0.9}
