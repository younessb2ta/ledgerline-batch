# ADR-0009 — dbt models are tables and views only; no incremental models or snapshots

**Status:** Accepted · 2026-11-08 (forced by ADR-0001)

## Context

The BigQuery sandbox rejects DML (`INSERT`, `UPDATE`, `DELETE`, `MERGE`).
dbt's `incremental` materialization is built on `MERGE`; snapshots use
`MERGE`/inserts; `table` materialization uses `CREATE OR REPLACE TABLE` and
`view` uses `CREATE OR REPLACE VIEW`, both of which are DDL and allowed.

This is a platform constraint, not a modeling preference, and it removes two
things a data engineer would normally reach for: incremental fact loads and
SCD2 history.

## Decision

- **staging + intermediate** → `view` (cheap, always fresh, no storage).
- **marts** → `table` (dashboard queries do not re-run the whole DAG).
- **No** `incremental` models, **no** snapshots, **no** `dbt run --full-refresh`
  as a recovery mechanism (a full `dbt build` is the recovery).
- Every mart is rebuilt from raw by a single `dbt build`, which is affordable
  at demo scale: 13 models + 57 tests run in ~36 s and scan ~1 MiB.

## Alternatives considered

1. **Attach billing and use incremental models.** The production answer. Would
   enable `merge` on `event_id`, snapshots for `dim_customers`, and
   partitioned incremental facts. Documented as the upgrade path.
2. **Fake incrementality with `CREATE OR REPLACE TABLE AS SELECT` filtered by
   date.** Does not reduce scanned bytes (the filter still reads the source)
   and hides the lack of merge semantics. Rejected as dishonest.
3. **Move marts to views to avoid rebuild cost.** Rejected: every dashboard
   query would re-scan the whole chain; the measured per-run cost is trivial,
   but latency would not be.

## Consequences

- Full rebuilds are the norm; idempotency comes from `CREATE OR REPLACE`, not
  from `MERGE`.
- SCD2 (`dim_customers` history) is a documented stretch goal that requires
  the paid path.
- The project stays portable: the same models run on a billed project by
  changing materializations, with no SQL changes.
- Verified by `dbt build` on every run; the sandbox would reject the DAG at the
  first incremental node if this decision were violated.
