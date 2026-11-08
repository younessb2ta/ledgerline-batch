# Runbook: pipeline is stale

**Alert:** `Ledgerline — Pipeline is stale`
**Meaning:** `assert_pipeline_freshness` found no successful load inside the SLA
(`freshness_sla_hours`, default 26 h). The warehouse is serving old data. The
most dangerous failure is silence: the dashboard looks fine.

## Triage (5 minutes)

1. Is the scheduler running?
   - GitHub Actions: check the scheduled workflow's run history.
   - Local/Airflow: check the DAG run list for failed or skipped tasks.
2. Did loads fail or just not run?
   ```sql
   SELECT status, count(*) AS attempts, max(loaded_at) AS last_attempt
   FROM `PROJECT.ops.load_audit`
   WHERE loaded_at > timestamp_sub(current_timestamp(), interval 3 day)
   GROUP BY status;
   ```
   - No rows at all → scheduler/auth problem, not data.
   - Only `failed` rows → go to [gx-gate-failure.md](gx-gate-failure.md).
3. Check upstream arrival: does `data/raw/DAY/manifest.json` exist for today?
4. Check credentials: Workload Identity Federation tokens expire; a rotated
   repository or service account breaks auth silently in scheduled runs.

## Recover

```bash
# backfill the missing day(s)
uv run eventforge batch --seed 42 --start YYYY-MM-DD --days 1 --out data/raw
uv run python -m orchestration.run_pipeline --day-dir data/raw/YYYY-MM-DD --project PROJECT
```

Then confirm:
```sql
SELECT max(loaded_at) FROM `PROJECT.ops.load_audit` WHERE status = 'success';
```

## Prevent

- Alert on **absence** (this test), not only on failures.
- Keep the SLA shorter than the dashboard's promised freshness.
- Test WIF/auth on a schedule (`workflow_dispatch`) before relying on cron.
- Historical demo batches intentionally have old event dates; freshness is
  measured on `loaded_at`, so backfills still count as fresh loads.
