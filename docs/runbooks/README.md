# Runbooks

Every alert links to one of these. The rule is the same in all of them: find
the failing invariant, decide whether the batch is recoverable, and only then
re-run. Re-running without diagnosis usually converts one bad batch into two.

| Alert | Runbook |
|---|---|
| Raw quality gate failed | [gx-gate-failure.md](gx-gate-failure.md) |
| dbt build failed | [dbt-test-failure.md](dbt-test-failure.md) |
| Pipeline is stale | [stale-pipeline.md](stale-pipeline.md) |
| Volume anomaly | [volume-anomaly.md](volume-anomaly.md) |

## Common commands

```bash
# what failed in the last gate run
bq query --use_legacy_sql=false '
  SELECT table_name, expectation, observed, expected, checked_at
  FROM `PROJECT.ops.dq_results`
  WHERE success = false
  ORDER BY checked_at DESC
  LIMIT 50'

# load history for a batch
bq query --use_legacy_sql=false '
  SELECT table_name, row_count, status, message, loaded_at
  FROM `PROJECT.ops.load_audit`
  WHERE batch_id = "BATCH_ID"
  ORDER BY loaded_at'

# re-run only the gate (no writes to raw)
uv run python -m ingest.validate --day-dir data/raw/DAY --project PROJECT --no-write
```

## Slack setup

1. Create an incoming webhook for the `#ledgerline-alerts` channel.
2. Export it locally: `export SLACK_WEBHOOK_URL=https://hooks.slack.com/...`
3. In GitHub, store it as the repository secret `SLACK_WEBHOOK_URL`.
4. Test without sending: `uv run python -m dq.alerts --stage gx --batch-id test --project PROJECT --summary test --dry-run`

Alerts are best-effort. A missing webhook prints the payload instead of failing
the pipeline, so the batch failure is never hidden by an alerting error.
