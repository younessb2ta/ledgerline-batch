"""Load one day of generated CSVs into BigQuery.

Idempotent per (batch_id, table): successful tables are skipped on retry, so a
partial failure can be resumed without duplicating data. Staging models also
dedupe on primary keys as a second line of defence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .bq import Warehouse
from .schemas import LOAD_AUDIT, RAW_TABLES


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def verify_manifest(day_dir: Path) -> dict:
    manifest_path = day_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    manifest = json.loads(manifest_path.read_text())
    for name, meta in manifest["files"].items():
        path = day_dir / name
        if not path.exists():
            raise SystemExit(f"missing file declared in manifest: {name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != meta["sha256"]:
            raise SystemExit(
                f"sha256 mismatch for {name}: manifest={meta['sha256']} actual={digest}"
            )
    return manifest


def already_loaded(warehouse: Warehouse, batch_id: str) -> set[str]:
    rows = warehouse.query(
        f"""
        SELECT table_name
        FROM `{warehouse.table_id("ops", "load_audit")}`
        WHERE batch_id = @batch_id AND status = 'success'
        """,
        {"batch_id": batch_id},
    )
    return {row["table_name"] for row in rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day-dir", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="US")
    parser.add_argument(
        "--force",
        action="store_true",
        help="load even when the audit table says this batch already succeeded",
    )
    args = parser.parse_args(argv)

    day_dir = args.day_dir
    manifest = verify_manifest(day_dir)
    batch_id = manifest["batch_id"]
    day = manifest["day"]

    warehouse = Warehouse(args.project, args.location)
    for spec in RAW_TABLES.values():
        warehouse.ensure_table("raw", spec)
    warehouse.ensure_table("ops", LOAD_AUDIT)

    done = set() if args.force else already_loaded(warehouse, batch_id)
    if done:
        print(f"batch {batch_id}: already loaded tables -> {sorted(done)}")

    audits: list[dict] = []
    loaded = 0
    for spec in RAW_TABLES.values():
        if spec.name in done:
            continue

        source = day_dir / str(spec.source)
        digest = manifest["files"][spec.source]["sha256"]
        try:
            rows = warehouse.load_csv("raw", spec, source)
        except Exception as exc:  # noqa: BLE001 - surfaced in the audit table
            audits.append(
                {
                    "batch_id": batch_id,
                    "day": day,
                    "table_name": spec.name,
                    "source_sha256": digest,
                    "row_count": 0,
                    "status": "failed",
                    "loaded_at": _now(),
                    "message": str(exc)[:1000],
                }
            )
            warehouse.append_rows("ops", LOAD_AUDIT, audits)
            print(f"FAILED {spec.name}: {exc}", file=sys.stderr)
            return 1

        loaded += rows
        audits.append(
            {
                "batch_id": batch_id,
                "day": day,
                "table_name": spec.name,
                "source_sha256": digest,
                "row_count": rows,
                "status": "success",
                "loaded_at": _now(),
                "message": "",
            }
        )
        print(f"loaded {spec.name:<18} {rows:>6} rows")

    warehouse.append_rows("ops", LOAD_AUDIT, audits)
    print(f"batch {batch_id}: {loaded} rows loaded, {len(audits)} tables audited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
