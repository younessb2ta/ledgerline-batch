"""Great Expectations gate over the raw landing files (gate 1 of 2).

Runs before the load. Every CSV is checked against three independent sources
of truth:

1. its declared column contract (`ingest/schemas.py`),
2. the generator's manifest (row count, sha256, timestamp span),
3. domain rules (primary keys, accepted values, non-negative money).

One row per expectation is written to `ops.dq_results` so the dashboard and
the alert runbook can query history instead of scraping logs. The exit code is
non-zero when any expectation fails: that is what makes this a gate, not a
report.

Gate 2 is dbt's test suite, which re-checks the same invariants *after*
transformation, where joins can introduce new nulls and fan-out.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import great_expectations as gx
import pandas as pd
from great_expectations.data_context.types.base import ProgressBarsConfig

from eventforge.generator import CATEGORIES
from eventforge.model import CURRENCY

from .bq import Warehouse
from .schemas import COMPOSITE_KEYS, DQ_RESULTS, PRIMARY_KEYS, RAW_TABLES, TableSpec

# --- domain contract ---------------------------------------------------------

ACCEPTED_VALUES: dict[str, dict[str, set[str]]] = {
    "raw_orders": {
        "order_status": {"paid", "refunded", "cancelled"},
        "currency": {CURRENCY},
    },
    "raw_payments": {"status": {"succeeded", "refunded"}},
    "raw_products": {"category": set(CATEGORIES)},
}

MINIMUMS: dict[str, dict[str, int]] = {
    "raw_products": {"list_price_cents": 0},
    "raw_order_items": {"quantity": 1, "unit_price_cents": 0, "amount_cents": 0},
    "raw_payments": {"amount_cents": 0},
    "raw_returns": {"amount_cents": 0},
}

# Columns that are nullable in the warehouse but must never be null on the
# wire; a null here means the producer broke its contract.
REQUIRED_NULLABLE: dict[str, tuple[str, ...]] = {
    "raw_customers": ("email", "created_at"),
    "raw_orders": ("order_ts",),
    "raw_order_items": ("quantity", "amount_cents"),
    "raw_payments": ("amount_cents", "paid_ts"),
    "raw_returns": ("amount_cents", "returned_ts"),
}

TIMESTAMP_COLUMNS: dict[str, tuple[str, ...]] = {
    "raw_customers": ("created_at",),
    "raw_orders": ("order_ts",),
    "raw_payments": ("paid_ts",),
    "raw_returns": ("returned_ts",),
}

ISO_TS_REGEX = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"

# A manifest describes the bytes that were written, so it cannot detect a
# truncated batch: a truncated file has a matching (smaller) manifest. The
# generator's ground truth is the expected volume, standing in for the
# trailing-volume baseline a production pipeline would compute from history.
VOLUME_BASELINE: dict[str, str] = {
    "raw_orders": "orders",
    "raw_order_items": "order_items",
    "raw_payments": "payments",
    "raw_returns": "returns",
}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _load_manifest(day_dir: Path) -> dict:
    manifest_path = day_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text())


def _read_table(spec: TableSpec, day_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(
        day_dir / str(spec.source),
        dtype=str,
        keep_default_na=False,
        na_values=[""],
    )
    # A schema-drift incident may drop or rename columns. Coerce what exists;
    # the column-set expectation is what reports the drift, not a crash here.
    for column in spec.columns:
        if column.name in df.columns and column.type == "INT64":
            df[column.name] = pd.to_numeric(df[column.name], errors="coerce")
    return df


class Gate:
    """Collects results and writes them to `ops.dq_results` in one load job."""

    def __init__(self, run_id: str, batch_id: str) -> None:
        self.run_id = run_id
        self.batch_id = batch_id
        self.rows: list[dict] = []

    def add(
        self,
        *,
        table: str,
        expectation: str,
        success: bool,
        observed: object = "",
        expected: object = "",
        detail: object = "",
        layer: str = "raw",
    ) -> None:
        self.rows.append(
            {
                "run_id": self.run_id,
                "batch_id": self.batch_id,
                "checked_at": _now(),
                "layer": layer,
                "table_name": table,
                "expectation": expectation,
                "success": bool(success),
                "observed": _clip(observed),
                "expected": _clip(expected),
                "detail": _clip(detail),
            }
        )

    @property
    def failures(self) -> list[dict]:
        return [row for row in self.rows if not row["success"]]

    def write(self, warehouse: Warehouse) -> None:
        warehouse.ensure_table("ops", DQ_RESULTS)
        warehouse.append_rows("ops", DQ_RESULTS, self.rows)


def _clip(value: object, limit: int = 1000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:limit]


def _describe_result(result) -> tuple[str, str]:
    """Return (observed, detail) from a GX expectation result."""
    payload = result.result or {}
    if "observed_value" in payload:
        observed = payload["observed_value"]
    elif "unexpected_count" in payload:
        observed = f"{payload.get('unexpected_count')} unexpected"
        percent = payload.get("unexpected_percent")
        if percent is not None:
            observed += f" ({percent:.2f}%)"
    else:
        observed = ""

    detail = ""
    sample = payload.get("partial_unexpected_list")
    if sample:
        detail = json.dumps(sample[:5], default=str)
    return str(observed), detail


def run_gx_suite(ctx, gate: Gate, spec: TableSpec, df: pd.DataFrame, expected_rows: int):
    source = ctx.data_sources.add_pandas(f"local-{spec.name}")
    asset = source.add_dataframe_asset(name=spec.name)
    batch_definition = asset.add_batch_definition_whole_dataframe("whole-file")
    batch = batch_definition.get_batch(batch_parameters={"dataframe": df})
    validator = ctx.get_validator(batch=batch)

    present = set(df.columns)

    validator.expect_table_columns_to_match_set(
        column_set=[column.name for column in spec.columns], exact_match=True
    )
    validator.expect_table_row_count_to_equal(value=expected_rows)

    # Declare existence explicitly: GX dedupes repeated `expect_column_to_exist`
    # calls, so one missing column per table would otherwise be the only one
    # reported.
    for column in spec.columns:
        if column.name not in present:
            gate.add(
                table=spec.name,
                expectation="column.exists",
                success=False,
                observed="missing",
                expected=column.name,
            )
        elif column.mode == "REQUIRED":
            validator.expect_column_values_to_not_be_null(column.name)

    for column in REQUIRED_NULLABLE.get(spec.name, ()):
        if column in present:
            validator.expect_column_values_to_not_be_null(column)

    for column in TIMESTAMP_COLUMNS.get(spec.name, ()):
        if column in present:
            validator.expect_column_values_to_match_regex(column, ISO_TS_REGEX)

    composite = COMPOSITE_KEYS.get(spec.name)
    if composite:
        if set(composite) <= present:
            validator.expect_compound_columns_to_be_unique(column_list=list(composite))
    elif PRIMARY_KEYS[spec.name] in present:
        validator.expect_column_values_to_be_unique(PRIMARY_KEYS[spec.name])

    for column, values in ACCEPTED_VALUES.get(spec.name, {}).items():
        if column in present:
            validator.expect_column_values_to_be_in_set(column, value_set=sorted(values))

    for column, minimum in MINIMUMS.get(spec.name, {}).items():
        if column in present:
            validator.expect_column_values_to_be_between(column, min_value=minimum)

    validation = validator.validate()
    for result in validation.results:
        observed, detail = _describe_result(result)
        gate.add(
            table=spec.name,
            expectation=result.expectation_config.type,
            success=result.success,
            observed=observed,
            expected=result.expectation_config.kwargs,
            detail=detail,
        )
    return validation


def check_manifest_span(
    gate: Gate, spec: TableSpec, df: pd.DataFrame, meta: dict, day_dir: Path
) -> None:
    """The file on disk must match the manifest it was declared with."""
    path = day_dir / str(spec.source)
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
    gate.add(
        table=spec.name,
        expectation="manifest.sha256",
        success=digest == meta["sha256"],
        observed=digest,
        expected=meta["sha256"],
    )

    ts_column = meta.get("ts_column")
    if not ts_column or ts_column not in df.columns:
        return
    ordered = df[ts_column].dropna()
    if ordered.empty:
        return
    gate.add(
        table=spec.name,
        expectation="manifest.min_ts",
        success=str(ordered.min()) == meta["min_ts"],
        observed=str(ordered.min()),
        expected=meta["min_ts"],
    )
    gate.add(
        table=spec.name,
        expectation="manifest.max_ts",
        success=str(ordered.max()) == meta["max_ts"],
        observed=str(ordered.max()),
        expected=meta["max_ts"],
    )


def check_volume(gate: Gate, spec: TableSpec, df: pd.DataFrame, ground_truth: dict) -> None:
    key = VOLUME_BASELINE.get(spec.name)
    if key is None or key not in ground_truth:
        return
    expected = int(ground_truth[key])
    gate.add(
        table=spec.name,
        expectation="volume.row_count_vs_baseline",
        success=len(df) == expected,
        observed=len(df),
        expected=expected,
        detail="ground truth row count for the batch",
    )


def check_freshness(gate: Gate, day: str, df: pd.DataFrame) -> None:
    """The batch day must contain events from that day (catches stale feeds)."""
    if "order_ts" not in df.columns:
        return
    day_start = f"{day}T00:00:00.000Z"
    latest = df["order_ts"].dropna().max()
    gate.add(
        table="raw_orders",
        expectation="freshness.order_ts_within_batch_day",
        success=bool(latest) and str(latest) >= day_start,
        observed=str(latest),
        expected=f">= {day_start}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day-dir", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="US")
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="validate only; do not write results to ops.dq_results",
    )
    args = parser.parse_args(argv)

    day_dir = args.day_dir
    manifest = _load_manifest(day_dir)
    batch_id = manifest["batch_id"]
    day = manifest["day"]

    ground_truth_path = day_dir / "ground_truth.json"
    ground_truth = json.loads(ground_truth_path.read_text()) if ground_truth_path.exists() else {}

    # TS columns used by the manifest span check.
    ts_by_table = {
        "orders.csv": "order_ts",
        "payments.csv": "paid_ts",
        "returns.csv": "returned_ts",
        "customers.csv": "created_at",
    }

    ctx = gx.get_context(mode="ephemeral")
    # Ephemeral contexts default to showing tqdm bars per expectation group,
    # which is unusable in CI logs.
    ctx.variables.progress_bars = ProgressBarsConfig(globally=False)
    gate = Gate(run_id=str(uuid.uuid4()), batch_id=batch_id)

    for spec in RAW_TABLES.values():
        meta = manifest["files"][spec.source]
        df = _read_table(spec, day_dir)
        run_gx_suite(ctx, gate, spec, df, expected_rows=int(meta["rows"]))
        check_manifest_span(
            gate,
            spec,
            df,
            {**meta, "ts_column": ts_by_table.get(str(spec.source))},
            day_dir,
        )
        check_volume(gate, spec, df, ground_truth)

    orders = _read_table(RAW_TABLES["raw_orders"], day_dir)
    check_freshness(gate, day, orders)

    failures = gate.failures
    total = len(gate.rows)
    print(f"batch {batch_id}: {total - len(failures)}/{total} expectations passed")

    if failures:
        print("\nFAILED expectations:", file=sys.stderr)
        for row in failures:
            print(
                f"  {row['table_name']:<18} {row['expectation']:<45} "
                f"observed={row['observed']!r} expected={row['expected'][:80]!r}",
                file=sys.stderr,
            )

    if args.no_write:
        print("--no-write: results not written to ops.dq_results")
    else:
        warehouse = Warehouse(args.project, args.location)
        gate.write(warehouse)
        print(f"wrote {total} results to ops.dq_results (run_id={gate.run_id})")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
