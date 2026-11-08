# Runbook: raw quality gate failed

**Alert:** `Ledgerline — Raw quality gate failed`
**Meaning:** a Great Expectations check failed on `raw_*`. No data was loaded
(`make load` depends on the gate), so the warehouse still holds the last good
batch.

## Triage (5 minutes)

1. Read the alert details. The failing expectation names the table and the
   invariant. Match it to a cause:

   | Expectation | Likely cause | First check |
   |---|---|---|
   | `expect_table_columns_to_match_set`, `column.exists` | producer schema drift | diff the CSV header against `ingest/schemas.py` |
   | `expect_column_values_to_be_unique`, `expect_compound_columns_to_be_unique` | duplicated extract or replayed file | count duplicate keys in the CSV |
   | `expect_table_row_count_to_equal` / `manifest.sha256` | file changed after the manifest was written | re-verify the manifest |
   | `volume.row_count_vs_baseline` | truncated extract (manifest is self-consistent) | compare row count to ground truth |
   | `freshness.order_ts_within_batch_day` | stale upstream feed | max(`order_ts`) vs batch day |
   | `expect_column_values_to_be_in_set` | new status/category value | compare distinct values to `ingest/validate.py` |

2. Confirm the scope:
   ```sql
   SELECT table_name, expectation, observed, expected
   FROM `PROJECT.ops.dq_results`
   WHERE batch_id = 'BATCH_ID' AND success = false;
   ```

3. Decide:
   - **Bad file, good upstream** → ask for a corrected extract, regenerate the
     manifest, re-run the gate with `--no-write`, then load.
   - **Upstream genuinely changed** (new status, new column) → update the
     contract in `ingest/schemas.py` and `ingest/validate.py`, add a test, and
     land the change before re-running. Never loosen a check just to get green.
   - **Truncation** → do not load. A partial batch that looks complete is worse
     than a missing batch.

## Recover

```bash
uv run python -m ingest.validate --day-dir data/raw/DAY --project PROJECT --no-write
# only after the gate passes:
uv run python -m ingest.load_day --day-dir data/raw/DAY --project PROJECT
cd warehouse && GCP_PROJECT=PROJECT uv run dbt build --profiles-dir .
```

## Prevent

- Add an expectation for every new failure mode found here.
- Keep the incident tag in the manifest so a drill can replay the failure.
- `ingest/tests/test_gate.py` asserts each incident mode fails the gate; extend
  it with the new expectation.
