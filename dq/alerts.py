"""Slack alerting for failed pipeline gates.

Delivery is optional: when `SLACK_WEBHOOK_URL` is unset the payload is printed
instead, so the runbooks can be exercised locally and in CI without secrets.
Alerting is best-effort and must never mask the original failure — callers keep
the failing exit code regardless of what happens here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import requests

RUNBOOKS: dict[str, tuple[str, str]] = {
    "gx": ("Raw quality gate failed", "docs/runbooks/gx-gate-failure.md"),
    "dbt": ("dbt build failed", "docs/runbooks/dbt-test-failure.md"),
    "freshness": ("Pipeline is stale", "docs/runbooks/stale-pipeline.md"),
    "volume": ("Volume anomaly", "docs/runbooks/volume-anomaly.md"),
    "load": ("Load failed", "docs/runbooks/gx-gate-failure.md"),
}

MAX_SUMMARY = 2800
MAX_DETAILS = 2200


@dataclass
class Delivery:
    delivered: bool
    reason: str
    payload: dict = field(default_factory=dict)


def build_alert(
    *,
    stage: str,
    batch_id: str,
    project: str,
    summary: str,
    details: str = "",
    run_url: str | None = None,
) -> dict:
    title, runbook = RUNBOOKS.get(stage, ("Pipeline failed", "docs/runbooks/README.md"))
    text = f":rotating_light: Ledgerline — {title} (batch {batch_id})"

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": title}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Stage*\n`{stage}`"},
                {"type": "mrkdwn", "text": f"*Batch*\n`{batch_id}`"},
                {"type": "mrkdwn", "text": f"*Project*\n`{project}`"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": summary[:MAX_SUMMARY]},
        },
    ]

    if details:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{details[:MAX_DETAILS]}```",
                },
            }
        )

    context = [{"type": "mrkdwn", "text": f"Runbook: `{runbook}`"}]
    if run_url:
        context.append({"type": "mrkdwn", "text": f"<{run_url}|Pipeline run>"})
    blocks.append({"type": "context", "elements": context})

    return {"text": text, "blocks": blocks}


def send(
    payload: dict,
    *,
    webhook_url: str | None = None,
    dry_run: bool = False,
    timeout: int = 10,
) -> Delivery:
    url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL", "")
    if dry_run or not url:
        reason = "dry run" if dry_run else "SLACK_WEBHOOK_URL not set"
        print(json.dumps(payload, indent=2))
        print(f"[alerts] not delivered: {reason}", file=sys.stderr)
        return Delivery(delivered=False, reason=reason, payload=payload)

    response = requests.post(url, json=payload, timeout=timeout)
    if response.status_code >= 300:
        return Delivery(
            delivered=False,
            reason=f"HTTP {response.status_code}: {response.text[:200]}",
            payload=payload,
        )
    return Delivery(delivered=True, reason="posted", payload=payload)


def fetch_gx_failures(project: str, batch_id: str, location: str = "US") -> list[dict]:
    """Query failed expectations for a batch.

    Reads are covered by the sandbox's 1 TiB monthly query allowance.
    """
    from ingest.bq import Warehouse

    warehouse = Warehouse(project, location)
    rows = warehouse.query(
        f"""
        SELECT table_name, expectation, observed, expected
        FROM `{warehouse.table_id("ops", "dq_results")}`
        WHERE batch_id = @batch_id AND success = false
        ORDER BY table_name, expectation
        """,
        {"batch_id": batch_id},
    )
    return [dict(row) for row in rows]


def summarize_failures(failures: list[dict]) -> tuple[str, str]:
    summary = f"{len(failures)} expectation(s) failed."
    lines = [
        (
            f"{row['table_name']}.{row['expectation']} "
            f"observed={row['observed']} expected={row['expected']}"
        )
        for row in failures
    ]
    return summary, "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=sorted(RUNBOOKS))
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--details", default="")
    parser.add_argument("--details-file", type=Path)
    parser.add_argument("--run-url", default=os.environ.get("RUN_URL"))
    parser.add_argument("--webhook-url", default=None)
    parser.add_argument(
        "--from-dq",
        action="store_true",
        help="populate summary/details from failed rows in ops.dq_results",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    summary, details = args.summary, args.details
    if args.from_dq:
        failures = fetch_gx_failures(args.project, args.batch_id)
        summary, details = summarize_failures(failures)
    if args.details_file:
        details = args.details_file.read_text()

    payload = build_alert(
        stage=args.stage,
        batch_id=args.batch_id,
        project=args.project,
        summary=summary or "No summary provided.",
        details=details,
        run_url=args.run_url,
    )
    delivery = send(payload, webhook_url=args.webhook_url, dry_run=args.dry_run)
    print(
        f"[alerts] delivered={delivery.delivered} reason={delivery.reason}",
        file=sys.stderr,
    )
    return 0 if delivery.delivered or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
