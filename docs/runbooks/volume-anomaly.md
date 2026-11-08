# Runbook: volume anomaly

**Alert:** `Ledgerline — Volume anomaly`
**Meaning:** `assert_daily_volume_within_band` found a day whose order count
deviates from the trailing 7-day average by more than
`volume_tolerance_pct` (default 0.3). The data can be perfectly valid row by
row and still be wrong in aggregate.

## Triage (5 minutes)

1. Confirm the size and direction:
   ```sql
   SELECT order_date, count(*) AS orders
   FROM `PROJECT.marts.fct_orders`
   GROUP BY order_date
   ORDER BY order_date DESC
   LIMIT 14;
   ```
2. Compare with the dashboard and with the streaming ledger. A drop visible in
   both paths means upstream; a drop only in batch means ingestion.
3. Check the raw load for the day:
   ```sql
   SELECT table_name, row_count, status
   FROM `PROJECT.ops.load_audit`
   WHERE day = DATE 'YYYY-MM-DD';
   ```
   A raw count that matches the manifest but not the baseline means a truncated
   extract — the manifest cannot detect this by design. The GX
   `volume.row_count_vs_baseline` check normally blocks it before load; if it
   did not, the generator contract changed or the check was bypassed with
   `--force`.
4. A spike is usually a duplicate load or a replayed file. Check:
   ```sql
   SELECT order_id, count(*) AS copies
   FROM `PROJECT.raw.raw_orders`
   GROUP BY order_id HAVING copies > 1
   ORDER BY copies DESC LIMIT 20;
   ```

## Recover

- **Truncated/low:** do not patch the mart. Re-extract and re-run the pipeline
  for that day; the loader is idempotent per `(batch_id, table)`.
- **Spike/duplicates:** the staging dedupe keeps one row per key, so marts may
  already be correct. Fix the raw duplicate, then rebuild the mart:
  ```bash
  cd warehouse && GCP_PROJECT=PROJECT uv run dbt build --profiles-dir .
  ```

## Prevent

- Alert on the *band*, not a fixed threshold; seasons and campaigns change
  volume legitimately.
- Keep `eventforge` ground truth in the batch directory so volume is provable.
- When the business changes volume on purpose, record it and widen the band for
  that day rather than disabling the test.
