# INC-001 — Truncated upstream extract blocks the batch gate

| | |
|---|---|
| **Date** | 2026-11-08 |
| **Batch** | `20261105-99` (event day 2026-11-05) |
| **Severity** | SEV-3 — no customer impact; batch refused |
| **Status** | Resolved (batch rejected, source to be re-extracted) |
| **Detected by** | Great Expectations gate 1, `volume.row_count_vs_baseline` |
| **Time to detect** | 7.09 s (gate runtime) |
| **Owner** | younessb2ta |

## Summary

The 2026-11-05 extract arrived with roughly 40% of its rows missing from every
transactional file. The extractor wrote a manifest over the files it had
produced, so the manifest was internally consistent: every SHA-256, row count,
and timestamp span matched. The only signal was volume: the batch claimed 480
orders where the ground truth for the day is 800.

The Great Expectations gate compared each table to the generator's ground truth
before the load stage, failed all four volume expectations, and exited non-zero.
`orchestration/run_pipeline.py` stopped at the gate, so no row from this batch
entered `raw_*`, the warehouse kept serving the last good batch, and the alert
linked the correct runbook.

## Impact

- No data loaded: `ops.load_audit` has **0** rows for `20261105-99`.
- No marts rebuilt: dashboards still show the last successful day.
- No customer or finance impact. This is a demo platform; in production the
  impact would be a delayed daily close, not wrong numbers.

## Timeline (UTC)

| Time | Event |
|---|---|
| ~11:59 | Upstream extract for 2026-11-05 produced with a fault that dropped 40% of rows (`incident.type=truncated`, `truncate_pct=0.4`). Manifest written from the truncated files. |
| 12:13:05 | `orchestration.run_pipeline` starts stage `gx`; 70 expectations evaluated in 7.09 s. |
| 12:13:05 | 66 pass, **4 fail**: `raw_orders` 480/800, `raw_order_items` 1189/1965, `raw_payments` 462/774, `raw_returns` 14/27. |
| 12:13:12 | Gate exits 1. Pipeline stops before `load`. Alert built with stage `gx`, batch `20261105-99`, runbook `docs/runbooks/gx-gate-failure.md`; delivery is a dry run here because no webhook is configured. |
| 12:13:12 | Run summary written to `artifacts/runs/20261105-99-20261108T121312Z.json` (`failed=true`, only the `gx` stage recorded); committed copy at `docs/incidents/evidence/run-20261105-99.json`. |

## Evidence

Failed expectations, from `ops.dq_results`:

```sql
SELECT table_name, expectation, observed, expected
FROM `ledgerline-514016.ops.dq_results`
WHERE batch_id = '20261105-99' AND success = false
ORDER BY table_name;
```

| table_name | expectation | observed | expected |
|---|---|---:|---:|
| raw_order_items | volume.row_count_vs_baseline | 1189 | 1965 |
| raw_orders | volume.row_count_vs_baseline | 480 | 800 |
| raw_payments | volume.row_count_vs_baseline | 462 | 774 |
| raw_returns | volume.row_count_vs_baseline | 14 | 27 |

Gate totals: **70 checks, 66 passed, 4 failed**, all at the same timestamp.

Why the manifest did not catch it:

```json
"files": {
  "orders.csv": { "rows": 480, "sha256": "…" },
  "order_items.csv": { "rows": 1189, "sha256": "…" }
},
"totals": { "orders": 480, "order_items": 1189, "payments": 462, "returns": 14 },
"incident": { "type": "truncated", "truncate_pct": 0.4 }
```

The manifest describes the bytes that were written. A truncated file has a
matching, smaller manifest — integrity, not completeness. Ground truth retains
the expected counts (800 / 1965 / 774 / 27), which is what the volume check uses.

Artifacts: the run summary is
`docs/incidents/evidence/run-20261105-99.json`; the failed rows are also saved as
`docs/incidents/evidence/dq-results-20261105-99.csv`, and both are queryable live
from `ops.dq_results` with the SQL above.

## Root cause

A truncation fault in the extract step. The pipeline's first gate is designed
for exactly this: it compares each transactional table with an **independent**
expected volume rather than with the file's own metadata.

The incident is intentionally reproducible: `eventforge` supports
`--incident truncated --truncate-pct 0.4`, and `ingest/tests/test_gate.py`
asserts that this mode fails the gate.

## What went well

1. **Gate ordering.** The gate runs before the load, so bad data never reached
   `raw_*`. Recovery is a re-extract, not a cleanup of loaded rows.
2. **Independent baseline.** The manifest was self-consistent; volume against
   ground truth was the only available signal.
3. **Actionable alert.** The payload named the stage, batch, project, failed
   expectations, and the runbook path — enough to start triage without reading
   logs.
4. **Auditability.** Every expectation result is a row in `ops.dq_results`, and
   the run summary is a file, so the postmortem is written from evidence.

## What did not go well

1. **The alert was not delivered.** No Slack webhook is configured on the
   zero-cost path, so delivery fell back to printing the payload. Fine for a
   demo, a real gap for on-call; tracked below.
2. **No automatic source retry.** The pipeline stops (correct) but does not ask
   the extractor for a corrected file. The runbook is a manual step.

## Recovery

```bash
# 1. regenerate the day without the fault (same seed as batch 20261105-99)
uv run eventforge batch --seed 99 --start 2026-11-05 --days 1 --out data/raw

# 2. gate the corrected extract (read-only; no writes to raw)
uv run python -m ingest.validate \
  --day-dir data/raw/2026-11-05 --project ledgerline-514016 --no-write

# 3. load + rebuild (idempotent per (batch_id, table))
uv run python -m orchestration.run_pipeline \
  --day-dir data/raw/2026-11-05 --project ledgerline-514016
```

The loader resumes safely: `ops.load_audit` is keyed on `(batch_id, table)`, so
a partially completed batch never duplicates rows.

## Action items

| # | Action | Status |
|---|---|---|
| 1 | Fail the gate when a table's row count differs from ground truth | Done — `volume.row_count_vs_baseline` |
| 2 | Add a mart-level band test for silent aggregate drift | Done — `assert_daily_volume_within_band` |
| 3 | Keep every incident mode replayable and tested | Done — `ingest/tests/test_gate.py` |
| 4 | Route gate failures to a runbook automatically | Done — `dq/alerts.py` + `docs/runbooks/gx-gate-failure.md` |
| 5 | Configure a real Slack webhook and test delivery | Open — blocked on the zero-cost path (no workspace webhook provisioned) |
| 6 | Automate a re-extract request on a gate failure | Open — needs an upstream control plane; out of scope for the demo |
