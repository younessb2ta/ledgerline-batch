# Architecture decision records

Format: context → decision → alternatives → consequences. Decisions that
changed during the build record the change rather than being rewritten to look
inevitable.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-gcp-bigquery-sandbox.md) | GCP + BigQuery on the sandbox, not a billed project | Accepted |
| [0002](0002-batch-and-streaming.md) | Process the same events twice: provisional stream, authoritative batch | Accepted |
| [0003](0003-at-least-once-idempotent-sink.md) | Exactly-once via at-least-once + idempotent sink, not 2PC | Accepted |
| [0006](0006-dual-quality-gate.md) | Great Expectations before load, dbt tests after transform | Accepted |
| [0007](0007-volume-anomaly-detection.md) | Trailing-average volume band, median/MAD as the upgrade path | Accepted, revisit at 30 days |
| [0008](0008-orchestration-free-path.md) | GitHub Actions + local Airflow instead of Composer | Accepted |
| [0009](0009-dbt-table-view-only.md) | dbt models are tables/views only; no incremental or snapshots | Accepted |

Reserved for the streaming phase: 0004 RocksDB/incremental checkpoints,
0005 late data (side output + restatement) — written in
`../../ledgerline-stream/docs/adr/`.
