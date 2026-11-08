# DR-001 — Join fan-out in `fct_orders` (game day)

| | |
|---|---|
| **Date** | 2026-11-08 |
| **Type** | Deliberate fault injection (game day), not a production incident |
| **Target** | `warehouse/models/marts/fct_orders.sql` |
| **Fault** | Extra `join stg_order_items using (order_id)` at order grain |
| **Detected by** | dbt test `unique_fct_orders_order_id` (gate 2) |
| **Result** | Caught; model restored; warehouse back to 800/800 |

## Why this drill

`fct_orders` is order-grain. Joining it to line-grain `stg_order_items` without
aggregating first multiplies every order by its line count. This is the most
common warehouse bug that survives column-level checks: every value is valid,
every key is present, and the totals still match — there are just more rows
than there are orders.

The clean model is in git; a local backup used during the drill is at
`artifacts/drills/fct_orders.sql.bak`; the full dbt output is committed at
`docs/incidents/evidence/dbt-fanout.log`.

## What was injected

```sql
with financials as (
    select * from {{ ref('int_order_financials') }}
),
lines as (
    select order_id from {{ ref('stg_order_items') }}
)
select financials.order_id, …
from financials
join lines using (order_id)
```

## Result

```
72 of 72 FAIL 615 unique_fct_orders_order_id .......... [FAIL 615 in 1.63s]
Done. PASS=69 WARN=0 ERROR=1 SKIP=0 NO-OP=2 TOTAL=72
```

Measured damage before restoring:

| Metric | Value |
|---|---:|
| `fct_orders` rows after the bad build | 2,050 |
| Distinct `order_id` | 800 |
| Clean order count (`stg_orders`) | 800 |
| Phantom rows | 1,250 |
| Duplicate key groups reported by dbt | 615 |

`dbt build` stopped publishing downstream nodes and exited 1; the alert path
would classify this as a generic `dbt` failure and link
`docs/runbooks/dbt-test-failure.md`, which names fan-out as the first suspect
for `unique` failures.

## What the drill revealed

1. **The uniqueness test is the right detector.** Duplication is a grain
   problem, and only a grain-level test sees it.
2. **The volume band did not catch it.** `assert_daily_volume_within_band`
   **passed**: the fan-out multiplies every day by roughly the same factor, so
   each day stays inside its trailing-average band. Aggregate volume detects
   level shifts, not uniform row multiplication. Both tests are needed; neither
   subsumes the other.
3. **The financial invariants passed.** `assert_order_totals_match_payments`
   compares order totals with payments; duplication scales both sides equally,
   so the equality holds. This is why “the numbers reconcile” is not proof of
   correct grain.
4. **Tests run after materialization.** `fct_orders` was replaced by the bad
   result and existed that way for ~8 seconds until the test failed. dbt tests
   gate downstream models and CI publication, not the write itself — a
   dashboard reading the table in that window would have shown inflated
   revenue. The production mitigation is to build in CI/staging and promote
   only after tests pass (or expose marts as views over tested intermediates for
   low-latency datasets).

## Restoration

```bash
cp artifacts/drills/fct_orders.sql.bak warehouse/models/marts/fct_orders.sql
cd warehouse && GCP_PROJECT=ledgerline-514016 uv run dbt build --profiles-dir .
# PASS=70 WARN=0 ERROR=0 SKIP=0 NO-OP=2 TOTAL=72
```

Full restore output: `docs/incidents/evidence/dbt-restored.log`.

Post-restore verification: `fct_orders` = **800 rows, 800 distinct orders**.

## Action items

| # | Action | Status |
|---|---|---|
| 1 | Keep a uniqueness test at every fact grain | Done — `unique_fct_orders_order_id`, `unique_fct_returns_return_id` |
| 2 | Do not rely on aggregate bands to detect duplication | Documented here and in the volume runbook |
| 3 | Re-check grain tests whenever a join is added to a fact | Added to the dbt failure runbook |
| 4 | Promote marts only after tests pass in CI | Open — current demo rebuilds in place; CI runs the same gate before any publish step |
