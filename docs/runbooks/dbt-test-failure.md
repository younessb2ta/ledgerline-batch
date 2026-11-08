# Runbook: dbt build failed

**Alert:** `Ledgerline — dbt build failed`
**Meaning:** raw data passed the GX gate and was loaded, but a model or test in
`staging`, `intermediate`, or `marts` failed. Because dbt builds in dependency
order, some marts may hold the previous run's data.

## Triage (5 minutes)

1. Identify the test class from the alert details:
   - `unique` / `not_null` → duplicate or missing keys after a join.
   - `relationships` → orphan foreign key; usually a dimension not rebuilt or a
     partial load of `raw_customers` / `raw_products`.
   - `accepted_values` → upstream contract changed after the GX gate.
   - `assert_order_totals_match_payments` → line items and payments disagree:
     join fan-out, duplicated `raw_order_items`, or a truncated payment file.
   - `assert_refunds_within_payments` → refund exceeds the payment, or a
     cancelled order carries a payment.
   - `assert_non_negative_amounts` → sign error or zero/negative quantity.
   - `assert_daily_volume_within_band` → see [volume-anomaly.md](volume-anomaly.md).
   - `assert_pipeline_freshness` → see [stale-pipeline.md](stale-pipeline.md).

2. Reproduce with a single selector:
   ```bash
   cd warehouse
   GCP_PROJECT=PROJECT uv run dbt test --profiles-dir . --select <test_name>
   ```

3. Inspect the failing rows. dbt prints the failing query; run it with a
   `LIMIT 20` to see the offending keys.

## Recover

```bash
# rebuild only the affected branch, then the whole project
cd warehouse
GCP_PROJECT=PROJECT uv run dbt build --profiles-dir . --select +fct_orders
GCP_PROJECT=PROJECT uv run dbt build --profiles-dir .
```

Do not delete marts to force a rebuild: `table` materialization already
replaces them atomically. If a singular test fails because the *test* is wrong,
fix the test with a regression case — do not loosen it silently.

## Prevent

- Keep singular tests at the grain where the bug lives (order, line, refund).
- After adding a join, re-check the affected fact's uniqueness test.
- Reconcile against ground truth when the generator changes.
