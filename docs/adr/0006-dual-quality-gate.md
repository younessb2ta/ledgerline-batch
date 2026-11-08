# ADR-0006 — Dual quality gate: Great Expectations before load, dbt after transform

**Status:** Accepted · 2026-11-08

## Context

A warehouse can be wrong in two different places:

1. **Before the load** — the extract is truncated, drifted, duplicated, or
   stale. Once those rows are in `raw_*`, downstream cleanup is expensive.
2. **After the transform** — joins fan out, dimensions are not rebuilt, a
   partial load leaves orphans. Row-level checks on the raw file cannot see
   this: every input row was valid.

One tool cannot own both layers cleanly. GX works on DataFrames/files and
knows nothing about dbt's DAG; dbt tests run SQL in the warehouse and cannot
validate a file before it is loaded.

## Decision

Run **two gates with different scopes**, and treat a failure in either as a
pipeline failure:

| Gate | Tool | Runs | Checks | On failure |
|---|---|---|---|---|
| 1 | Great Expectations | before `load_day` | column contract, PK/composite PK uniqueness, accepted values, non-negative money, manifest sha/span, **volume vs ground truth**, event-time freshness | no rows loaded; alert → `gx-gate-failure.md` |
| 2 | dbt tests | after `dbt build` | staging dedupe, relationships, grain uniqueness, financial invariants, wall-clock freshness, volume band | downstream models not published; alert → `dbt-test-failure.md` |

Gate 2 deliberately re-checks invariants that gate 1 already checked. That is
not duplication: it proves the transform preserved them. A payment can be
positive on input and still be wrong after a fan-out join.

The orchestrator (`orchestration/run_pipeline.py`) owns the order:
`GX → load → dbt build`, stopping at the first failure and writing a JSON run
summary.

## Alternatives considered

1. **GX inside dbt** (via a dbt package or a post-hook). Rejected: GX would
   then run after the load, losing its main advantage. It also couples a
   Python file-level tool to dbt's SQL runtime.
2. **dbt tests only.** Cannot see the raw file before load, so a truncated
   batch would be loaded and then fail late (or pass if the truncation is
   uniform — as DR-001 showed).
3. **GX only.** Cannot express joins, grain, or referential integrity after
   transformation.

## Consequences

- Two suites to maintain. Contract changes must be made in both places
  (`ingest/schemas.py` + dbt `_marts.yml`) — intentional, since they validate
  different artifacts.
- The alert router must know which gate failed to link the right runbook; the
  stage names are stable (`gx`, `load`, `dbt`, `freshness`, `volume`).
- Gate 2 does not roll back the materialization that just succeeded; see
  DR-001 for the exposure window and the CI-promotion mitigation.
- Evidence is queryable: `ops.dq_results` (gate 1) and dbt's
  `run_results.json` (gate 2).
