# Incidents and drills

| ID | Title | Type | Status |
|---|---|---|---|
| [INC-001](001-truncated-batch.md) | Truncated upstream extract blocks the batch gate | Incident (simulated source fault) | Resolved |
| [DR-001](002-fanout-drill.md) | Join fan-out in `fct_orders` | Game-day drill | Caught and restored |

Both documents are written from artifacts that are committed with the repo:

- [`evidence/run-20261105-99.json`](evidence/run-20261105-99.json) — failed run summary
- [`evidence/dq-results-20261105-99.csv`](evidence/dq-results-20261105-99.csv) — the four failed expectations
- [`evidence/dbt-fanout.log`](evidence/dbt-fanout.log) — full dbt output of the drill
- [`evidence/dbt-restored.log`](evidence/dbt-restored.log) — post-restore verification
- `ops.dq_results` — every gate-1 expectation result, queryable
- `warehouse/target/run_results.json` — every gate-2 node result (copy in
  `bench/run_results_clean.json`)

The difference between the two: INC-001 is a fault the pipeline **received**
(the generator injected a truncation to make the failure reproducible); DR-001
is a fault **we injected** into a model to test the gate. Neither is presented
as a production event.
