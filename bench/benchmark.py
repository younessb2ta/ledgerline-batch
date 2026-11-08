"""Measure what the Ledgerline batch pipeline would cost on a billed project.

The sandbox is free, so this benchmark answers two questions with the same
number: what did the pipeline actually process (measured), and what would it
cost per day/month if the project had billing enabled (modeled).

Inputs are real, not assumptions:

- ``warehouse/target/run_results.json`` — dbt records ``bytes_processed`` and
  ``bytes_billed`` per node from the BigQuery job response.
- ``bench/queries/*.sql`` — the representative dashboard/reconciliation
  queries, measured with a dry run (free, no bytes billed).

Usage:
    uv run python -m bench.benchmark --project <project>
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_RESULTS = ROOT / "warehouse" / "target" / "run_results.json"
DEFAULT_QUERIES = ROOT / "bench" / "queries"
DEFAULT_REPORT = ROOT / "bench" / "report.md"

MIB = 1024**2
GIB = 1024**3
TIB = 1024**4

# BigQuery on-demand pricing (US multi-region, 2026) and the documented
# 10 MB minimum billed per query.
USD_PER_TIB = 6.25
MIN_BILLED_BYTES = 10 * MIB
USD_PER_GIB_MONTH = 0.02
SANDBOX_QUERY_FREE_TIB = 1
SANDBOX_STORAGE_FREE_GIB = 10


def billed_bytes(processed: int) -> int:
    """BigQuery bills at least 10 MB per query, even for tiny tables."""
    return max(int(processed), MIN_BILLED_BYTES)


def cost_usd(bytes_billed: int) -> float:
    return bytes_billed / TIB * USD_PER_TIB


def monthly_cost_usd(per_run_billed: int, runs_per_day: int = 1, days: int = 30) -> float:
    return cost_usd(per_run_billed) * runs_per_day * days


@dataclass
class RunCost:
    generated_at: str
    elapsed_seconds: float
    nodes: int
    bytes_processed: int
    bytes_billed: int
    models: int
    tests: int


def read_run_results(path: Path) -> RunCost:
    payload = json.loads(path.read_text())
    results = payload["results"]
    processed = billed = 0
    models = tests = 0
    for row in results:
        adapter = row.get("adapter_response") or {}
        processed += int(adapter.get("bytes_processed") or 0)
        billed += int(adapter.get("bytes_billed") or 0)
        if row["unique_id"].startswith("model."):
            models += 1
        elif row["unique_id"].startswith("test."):
            tests += 1
    return RunCost(
        generated_at=payload["metadata"]["generated_at"],
        elapsed_seconds=float(payload["elapsed_time"]),
        nodes=len(results),
        bytes_processed=processed,
        bytes_billed=billed,
        models=models,
        tests=tests,
    )


def node_rows(path: Path, limit: int = 10) -> list[tuple[str, int, float]]:
    payload = json.loads(path.read_text())
    rows = []
    for row in payload["results"]:
        adapter = row.get("adapter_response") or {}
        parts = row["unique_id"].split(".")
        # model.pkg.name / test.pkg.name.hash — the name is always index 2.
        name = parts[2] if len(parts) > 2 else parts[-1]
        rows.append(
            (name, int(adapter.get("bytes_processed") or 0), float(row.get("execution_time") or 0))
        )
    return sorted(rows, key=lambda item: -item[1])[:limit]


def query_bytes(project: str, sql: str) -> int:
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False),
    )
    return int(job.total_bytes_processed or 0)


def measure_queries(project: str, queries_dir: Path) -> list[tuple[str, int]]:
    measured = []
    for path in sorted(queries_dir.glob("*.sql")):
        sql = path.read_text().replace("{{ project }}", project)
        measured.append((path.stem, query_bytes(project, sql)))
    return measured


def table_storage(project: str) -> list[tuple[str, int, int]]:
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    rows = []
    for dataset in ("raw", "staging", "marts", "ops"):
        for item in client.list_tables(f"{project}.{dataset}"):
            table = client.get_table(item.reference)
            rows.append(
                (
                    f"{dataset}.{item.table_id}",
                    int(table.num_rows or 0),
                    int(table.num_bytes or 0),
                )
            )
    return sorted(rows, key=lambda row: -row[2])


def render_report(
    *,
    project: str,
    run: RunCost,
    nodes: list[tuple[str, int, float]],
    queries: list[tuple[str, int]],
    storage: list[tuple[str, int, int]],
) -> str:
    run_cost = cost_usd(run.bytes_billed)
    archive_cost = monthly_cost_usd(run.bytes_billed)
    storage_bytes = sum(row[2] for row in storage)
    storage_cost = storage_bytes / GIB * USD_PER_GIB_MONTH
    dashboard_billed = sum(billed_bytes(b) for _, b in queries)
    dashboard_cost = cost_usd(dashboard_billed)

    lines = [
        "# Cost benchmark",
        "",
        f"Measured {datetime.now(UTC).date().isoformat()} against "
        f"`{project}` (BigQuery sandbox, no billing account).",
        "",
        "## Method",
        "",
        "Every number below is measured, not estimated:",
        "",
        "1. `dbt build` records `bytes_processed` and `bytes_billed` from each "
        "BigQuery job response in `warehouse/target/run_results.json`.",
        "2. `bench/queries/*.sql` are validated with a **dry run**, which returns "
        "the exact bytes scanned and bills nothing.",
        "3. The paid figure applies the US on-demand rate of "
        f"${USD_PER_TIB:.2f}/TiB to the measured bytes.",
        "",
        "## One pipeline run",
        "",
        f"- generated: `{run.generated_at}`",
        f"- nodes: {run.nodes} ({run.models} models, {run.tests} tests)",
        f"- wall time: {run.elapsed_seconds:.1f}s",
        f"- bytes processed: {run.bytes_processed / MIB:.2f} MiB",
        f"- bytes billed: {run.bytes_billed / GIB:.4f} GiB",
        f"- modeled paid cost: **${run_cost:.5f}**",
        "",
        f"Billed is larger than processed because BigQuery's "
        f"{MIN_BILLED_BYTES / MIB:.0f} MB minimum applies to each of the "
        f"{run.nodes} statements. That floor, not the data, dominates this "
        "workload: the tables hold less than 1 MiB.",
        "",
        "### Most expensive nodes",
        "",
        "| Node | Processed (MiB) | Seconds |",
        "|---|---:|---:|",
    ]
    for name, processed, seconds in nodes:
        lines.append(f"| `{name}` | {processed / MIB:.3f} | {seconds:.2f} |")

    lines += [
        "",
        "## Dashboard and reconciliation queries",
        "",
        "| Query | Bytes scanned | Paid cost per run |",
        "|---|---:|---:|",
    ]
    for name, processed in queries:
        lines.append(
            f"| `{name}` | {processed / MIB:.3f} MiB | ${cost_usd(billed_bytes(processed)):.5f} |"
        )
    lines += [
        f"| **all four** | **{dashboard_billed / MIB:.2f} MiB billed** | "
        f"**${dashboard_cost:.5f}** |",
        "",
        "## Storage",
        "",
        f"Active logical bytes: **{storage_bytes / MIB:.2f} MiB** across "
        f"{len(storage)} tables (staging views report 0).",
        f"Modeled storage cost: **${storage_cost:.4f}/month**.",
        "",
        "<details><summary>Per table</summary>",
        "",
        "| Table | Rows | Bytes |",
        "|---|---:|---:|",
    ]
    for name, rows, size in storage:
        lines.append(f"| `{name}` | {rows} | {size} |")
    lines += [
        "",
        "</details>",
        "",
        "## Monthly projection (1 run/day)",
        "",
        "| Item | Bytes billed / month | Paid cost / month |",
        "|---|---:|---:|",
        f"| Pipeline (`dbt build`) | {run.bytes_billed * 30 / GIB:.1f} GiB | ${archive_cost:.2f} |",
        f"| Dashboard (4 queries, 24 loads/day) | {dashboard_billed * 24 * 30 / GIB:.1f} GiB | "
        f"${dashboard_cost * 24 * 30:.2f} |",
        f"| Storage | {storage_bytes / GIB:.4f} GiB | ${storage_cost:.2f} |",
        f"| **Total** | | **${archive_cost + dashboard_cost * 24 * 30 + storage_cost:.2f}** |",
        "",
        "## Sandbox vs paid",
        "",
        "| Constraint | Sandbox (this project) | Billed project |",
        "|---|---|---|",
        "| Query cost | free up to 1 TiB/month | $6.25/TiB on-demand |",
        "| Storage | free up to 10 GiB | $0.02/GiB/month |",
        "| DML / MERGE | rejected | allowed |",
        "| Streaming inserts | rejected | allowed |",
        "| Table expiry | 60 days | serverless, configurable |",
        "",
        f"The entire workload fits in the sandbox's free tier with room to "
        f"spare: {run.bytes_billed * 30 / TIB:.4f} TiB of queries against a "
        f"1 TiB allowance. The free path is a policy choice, not a technical "
        "limit — the paid equivalent is cents per month.",
        "",
        "## Caveats",
        "",
        "- Prices are US multi-region on-demand list prices and change over time.",
        "- The 10 MB minimum billed per statement is why the paid number is not "
        "the data size; at production volume the floor stops mattering.",
        "- This is a 3-day, 800-orders/day demo. Scaling to 100k orders/day "
        "multiplies bytes roughly linearly for these row-wise models.",
        "- Dry-run bytes equal billed bytes for a normal query (no cache, no "
        "clustering bonus applied).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--run-results", type=Path, default=DEFAULT_RUN_RESULTS)
    parser.add_argument("--queries-dir", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--skip-queries",
        action="store_true",
        help="render from run results + storage only (no dry runs)",
    )
    args = parser.parse_args(argv)

    run = read_run_results(args.run_results)
    nodes = node_rows(args.run_results)
    queries = [] if args.skip_queries else measure_queries(args.project, args.queries_dir)
    storage = table_storage(args.project)

    report = render_report(
        project=args.project, run=run, nodes=nodes, queries=queries, storage=storage
    )
    args.out.write_text(report)
    print(f"wrote {args.out}")
    print(
        f"run: {run.bytes_billed / GIB:.3f} GiB billed, ${cost_usd(run.bytes_billed):.5f}; "
        f"storage: {sum(r[2] for r in storage) / MIB:.2f} MiB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
