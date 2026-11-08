"""Run the batch pipeline end to end.

This is the local stand-in for Airflow/Composer (neither is available on the
zero-cost path): the same stages, the same alerting, callable from a laptop,
GitHub Actions, or the Airflow DAG wrapper.

Stages are ordered so that bad data never reaches the warehouse:

    GX gate -> load jobs -> dbt build (tests included) -> alert on failure
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from dq import alerts
from ingest.load_day import main as load_main
from ingest.validate import main as validate_main

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "warehouse"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _batch_id(day_dir: Path) -> str:
    manifest = json.loads((day_dir / "manifest.json").read_text())
    return str(manifest["batch_id"])


def run_dbt(project: str) -> tuple[int, str]:
    """Run `dbt build` (models + tests) against the sandbox."""
    env = {**os.environ, "GCP_PROJECT": project}
    process = subprocess.run(
        ["uv", "run", "dbt", "build", "--profiles-dir", "."],
        cwd=WAREHOUSE,
        env=env,
        capture_output=True,
        text=True,
    )
    output = process.stdout + process.stderr
    print(output)
    return process.returncode, output


def classify_dbt_failure(output: str) -> str:
    """Route the alert to the right runbook from the failing test name."""
    if "assert_pipeline_freshness" in output:
        return "freshness"
    if "assert_daily_volume_within_band" in output:
        return "volume"
    return "dbt"


def _tail(output: str, lines: int = 40) -> str:
    return "\n".join(output.splitlines()[-lines:])


def notify(
    *,
    stage: str,
    batch_id: str,
    project: str,
    summary: str,
    details: str = "",
    dry_run: bool = False,
) -> alerts.Delivery:
    payload = alerts.build_alert(
        stage=stage,
        batch_id=batch_id,
        project=project,
        summary=summary,
        details=details,
        run_url=os.environ.get("RUN_URL"),
    )
    delivery = alerts.send(payload, dry_run=dry_run)
    print(f"[pipeline] alert {stage}: delivered={delivery.delivered} ({delivery.reason})")
    return delivery


def run(
    *,
    day_dir: Path,
    project: str,
    location: str = "US",
    skip_dbt: bool = False,
    no_alert: bool = False,
    dry_run_alerts: bool = False,
) -> int:
    day_dir = day_dir.resolve()
    batch_id = _batch_id(day_dir)
    started = time.monotonic()
    stages: list[dict] = []

    def record(name: str, code: int, seconds: float, detail: str = "") -> None:
        stages.append(
            {"stage": name, "exit_code": code, "seconds": round(seconds, 2), "detail": detail}
        )

    steps: list[tuple[str, Callable[[], tuple[int, str]]]] = [
        (
            "gx",
            lambda: (
                validate_main(
                    ["--day-dir", str(day_dir), "--project", project, "--location", location]
                ),
                "",
            ),
        ),
        (
            "load",
            lambda: (
                load_main(
                    ["--day-dir", str(day_dir), "--project", project, "--location", location]
                ),
                "",
            ),
        ),
    ]
    if not skip_dbt:
        steps.append(("dbt", lambda: run_dbt(project)))

    for name, step in steps:
        print(f"\n=== {name} ===", flush=True)
        began = time.monotonic()
        code, output = step()
        elapsed = time.monotonic() - began
        record(name, code, elapsed)

        if code != 0:
            summary = f"Stage `{name}` failed with exit code {code} after {elapsed:.1f}s."
            details = ""
            stage_for_alert = name
            if name == "dbt":
                details = _tail(output)
                stage_for_alert = classify_dbt_failure(output)
            if not no_alert:
                notify(
                    stage=stage_for_alert,
                    batch_id=batch_id,
                    project=project,
                    summary=summary,
                    details=details,
                    dry_run=dry_run_alerts,
                )
            _write_summary(batch_id, project, day_dir, stages, started, failed=True)
            return code

    _write_summary(batch_id, project, day_dir, stages, started, failed=False)
    print(f"\n=== pipeline OK: batch {batch_id} ===")
    return 0


def _write_summary(
    batch_id: str,
    project: str,
    day_dir: Path,
    stages: list[dict],
    started: float,
    failed: bool,
) -> None:
    out_dir = ROOT / "artifacts" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{batch_id}-{stamp}.json"
    path.write_text(
        json.dumps(
            {
                "batch_id": batch_id,
                "project": project,
                "day_dir": str(day_dir),
                "failed": failed,
                "total_seconds": round(time.monotonic() - started, 2),
                "stages": stages,
                "finished_at": _now(),
            },
            indent=2,
        )
    )
    print(f"[pipeline] run summary: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day-dir", required=True, type=Path)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", default="US")
    parser.add_argument("--skip-dbt", action="store_true")
    parser.add_argument("--no-alert", action="store_true", help="do not send Slack alerts")
    parser.add_argument(
        "--dry-run-alerts",
        action="store_true",
        help="print the Slack payload instead of posting it",
    )
    args = parser.parse_args(argv)

    return run(
        day_dir=args.day_dir,
        project=args.project,
        location=args.location,
        skip_dbt=args.skip_dbt,
        no_alert=args.no_alert,
        dry_run_alerts=args.dry_run_alerts,
    )


if __name__ == "__main__":
    raise SystemExit(main())
