# ledgerline-batch

Batch ELT, warehouse models, and data quality for the Ledgerline platform.

```
eventforge ──► local CSV + manifest ──► GX gate ──► BigQuery sandbox raw ──► dbt (staging → marts)
                                             │                                   │
                                             └── ops.dq_results                  ├── dbt tests
                                                                                 ├── dbt docs → GitHub Pages
                                                                                 └── GitHub Actions / Airflow
```

The default path is **zero-cost**: BigQuery sandbox (no billing account), local file loads, local Terraform state. GCS and Composer are optional paid upgrades — see `infra/README.md`.

This repo contains **Phases 0–5**: the deterministic generator, the zero-cost Terraform layout, the ingestion path with its Great Expectations gate, the dbt star schema, the operational layer (freshness/volume gates, Slack alerting, runbooks, orchestration), and the evidence package (measured cost benchmark, ADRs, incident postmortem and game-day drill). The real-time path (Phases 6–8) lives in [`../ledgerline-stream`](../ledgerline-stream) and consumes the same `eventforge` generator.

Phase 0 exit criteria:

- [x] `uv sync` works from a clean clone (Python 3.11, workspace package)
- [x] `pytest` green — 38 tests covering determinism, manifest integrity, balances, incident modes, the GX gate, dbt-adjacent logic, orchestration, and the cost benchmark
- [x] same seed ⇒ byte-identical manifest hashes; different seed ⇒ different data
- [x] `truncated` produces a self-consistent dataset at ~40% volume; the manifest matches the file, so only the **volume-vs-ground-truth** check catches it
- [x] `schema_drift`, `duplicate_pk`, `stale` each produce a plausible single failure
- [x] toolchain installed: uv/Python 3.11, Terraform 1.17, JDK 17, Maven 3.10, gcloud 592 — see `../docs/toolchain.md`
- [x] commits authored as `younessb2ta <youness.bgamer@gmail.com>` (via Dulwich until Xcode CLT is restored)
- [x] Docker not required: macOS 12 lacks it, so the streaming phase runs Kafka, Flink, and Postgres natively from tarballs — see [`../ledgerline-stream`](../ledgerline-stream)

## Quickstart

Requires `uv` (https://docs.astral.sh/uv/). The 3-minute recording guide is in
[`docs/demo-script.md`](docs/demo-script.md).

```bash
make install          # uv sync (creates .venv, installs eventforge + pytest)
make test             # unit tests
make gen              # 1 day of seeded data in data/raw/
make gen DAYS=3 START=2026-11-01 SEED=42
```

Generate a broken dataset on purpose:

```bash
make gen-day INCIDENT=truncated TRUNCATE_PCT=0.6
make gen-day INCIDENT=schema_drift
make gen-day INCIDENT=duplicate_pk
make gen-day INCIDENT=stale
```

## Ingest and quality gate

```bash
make validate START=2026-11-01     # GX gate only; exits 1 on any failure
make load START=2026-11-01         # validate passes → CSV load jobs into raw_*
```

Both read `data/raw/<day>/manifest.json` and target `$PROJECT` (defaults to the active `gcloud` project).

The gate writes one row per expectation to `ops.dq_results` (`run_id`, `table_name`, `expectation`, `success`, `observed`, `expected`). It checks:

| Check | Catches |
|---|---|
| column set + per-column existence | `schema_drift` |
| primary key / composite key uniqueness | `duplicate_pk` |
| required and timestamp-regex checks | producer contract breaks |
| accepted values, non-negative money | domain violations |
| row count vs manifest | file tampering / partial writes |
| row count vs ground-truth baseline | `truncated` (a truncated file has a matching smaller manifest) |
| `raw_orders.order_ts` within the batch day | `stale` |

`make test` runs the gate against all four incidents and asserts exit code 1, plus the clean-day case at exit 0.

Idempotency: `ingest.load_day` skips tables already marked `success` for the `(batch_id, table_name)` pair in `ops.load_audit`, so a partial failure resumes without duplicating rows. Writes are load jobs only — the sandbox has no DML.

> `make` needs Xcode Command Line Tools on macOS. If `make` is unavailable, run the underlying commands directly, e.g. `uv run python -m ingest.validate --day-dir data/raw/2026-11-01 --project <project>`.

## Warehouse (dbt)

```bash
cd warehouse
GCP_PROJECT=<project> uv run dbt build --profiles-dir .   # run + all tests
GCP_PROJECT=<project> uv run dbt docs generate --profiles-dir . && uv run dbt docs serve --profiles-dir .
```

| Layer | Materialization | Models |
|---|---|---|
| staging | view | `stg_customers`, `stg_products`, `stg_orders`, `stg_order_items`, `stg_payments`, `stg_returns` — dedupe on natural keys, cast, normalize |
| intermediate | view | `int_order_financials` — order-level rollup, one row per order, no join fan-out |
| marts | table | `dim_customers`, `dim_products`, `dim_date`, `fct_orders`, `fct_order_items`, `fct_returns` |

Star schema: `fct_orders` is order-grain, `fct_order_items` is line-grain, `fct_returns` is refund-grain. All money columns are integer cents. `dim_date` is a conformed spine over order and refund dates.

Gate 2 — 57 tests, including five singular tests that a column-level suite cannot express:

- every non-cancelled order's line total equals its payment (`assert_order_totals_match_payments`) — catches join fan-out and duplicated line loads
- refunds never exceed the payment they reverse, and cancelled orders carry no payment (`assert_refunds_within_payments`)
- no negative or zero-quantity money rows (`assert_non_negative_amounts`)
- the newest successful load is inside the freshness SLA (`assert_pipeline_freshness`)
- the latest day is within a band of its trailing 7-day average (`assert_daily_volume_within_band`)

Sandbox constraints are encoded in `dbt_project.yml`: marts are `table`, staging is `view`; there are no incremental models or snapshots because the sandbox rejects DML. `maximum_bytes_billed` in `profiles.yml` is a hard 1 GB cost guard per query. Exposures declare the dashboard and reconciliation report, so `dbt docs` shows lineage from `raw_*` to the dashboard.

## Orchestration and alerting

```bash
uv run python -m orchestration.run_pipeline \
  --day-dir data/raw/2026-11-01 --project <project> --dry-run-alerts
```

Stage order is a gate chain: GX validate → BigQuery load → `dbt build` (models + 57 tests). A failure stops the pipeline, writes a JSON run summary to `artifacts/runs/`, and sends a Slack alert that links the matching runbook. The GX gate runs first, so bad data never reaches `raw_*`; `dbt build` re-checks invariants at the mart layer.

Operational tests added in this phase:

| Test | Catches |
|---|---|
| `assert_pipeline_freshness` | no successful load inside `freshness_sla_hours` (default 26 h) — wall-clock staleness |
| `assert_daily_volume_within_band` | a day deviating from its trailing 7-day average by more than `volume_tolerance_pct` (default 0.3) |

Slack is optional. With `SLACK_WEBHOOK_URL` set (env or repo secret) the alert posts; without it the payload prints, so the runbook path is testable locally. `RUN_URL` adds a link to the CI run. See [`docs/runbooks/`](docs/runbooks/) for triage and recovery.

Deployment wrappers: `.github/workflows/pipeline.yml` (scheduled, keyless WIF auth) and `orchestration/dags/ledgerline_batch.py` (Airflow, for environments that have it). `orchestration/run_pipeline.py` is the single implementation both call.

## Cost benchmark

[`bench/report.md`](bench/report.md) is generated by the code in `bench/`, from
real BigQuery job metadata — not estimates:

```bash
uv run python -m bench.benchmark --project <project>
```

Every number is measured. `dbt build` records `bytes_processed` and
`bytes_billed` per node in `warehouse/target/run_results.json`; the four
dashboard/reconciliation queries in `bench/queries/` are validated with a free
dry run. Headline results for the demo workload:

| Item | Measured | Paid equivalent |
|---|---:|---:|
| One full `dbt build` (72 nodes) | 0.72 GiB billed, 35.6 s | $0.00441 |
| Four dashboard queries | 40 MiB billed (10 MB/query floor) | $0.00024 |
| Storage (21 tables) | 0.62 MiB | $0.0000/month |
| **Monthly (1 run/day + 24 dashboard loads/day)** | 49.8 GiB billed | **$0.30** |

The sandbox is free up to 1 TiB of queries and 10 GiB of storage per month, so
the workload uses ~2% of the query allowance. The full report also lists the
most expensive nodes and every table's size, and the report explains why
billed bytes (10 MB minimum per statement) exceed processed bytes (~1 MiB).
[`COST.md`](COST.md) records the monthly projection, the partition/clustering
experiment (honest result: $0 delta at demo scale, because of the billing
floor), and the services rejected to stay free.

## Incidents and decisions

- [`docs/incidents/`](docs/incidents/) — a postmortem built from a real blocked
  run (truncated extract, INC-001) and a game-day drill that deliberately broke
  `fct_orders` with a join fan-out (DR-001). Both link the artifacts that
  prove the timeline.
- [`docs/adr/`](docs/adr/) — seven accepted decisions: sandbox vs billed
  project, batch + streaming authority, at-least-once + idempotent sink,
  dual quality gate, volume-band method, orchestration on the free path, and
  table/view-only dbt.

## Output contract

Each day is written to `data/raw/<YYYY-MM-DD>/`:

| File | Grain | Notes |
|---|---|---|
| `customers.csv` | one row per customer | dimension |
| `products.csv` | one row per product | dimension |
| `orders.csv` | one row per order | status: paid / refunded / cancelled |
| `order_items.csv` | one row per order line | money in integer cents |
| `payments.csv` | one row per payment | |
| `returns.csv` | one row per refund | |
| `events.jsonl` | one row per event | canonical stream, event-time sorted |
| `manifest.json` | — | row counts, sha256, min/max timestamps, incident tag |
| `ground_truth.json` | — | event counts, per-customer balance, revenue — always the *intended* full dataset |

`ground_truth.json` intentionally does **not** shrink when an incident is injected. The gap between manifest and ground truth is what the volume baseline test is supposed to detect.

## Determinism

- `event_id = uuidv5(seed, day, sequence)` — replaying a seed produces identical IDs, which makes duplicate detection provable.
- Per-day RNG is seeded with `"<seed>:<day>"`, so days are independent and reproducible.
- Manifests contain no timestamps, so two runs of the same seed produce byte-identical hashes.

## Known limitations

- **Sandbox, not production BigQuery.** There is no DML and no streaming
  insert, so the batch path is idempotent through load jobs plus
  `CREATE OR REPLACE` rebuilds rather than incremental `MERGE`. A production
  version would partition the facts and use incremental models.
- **Local Terraform state.** No remote backend or locking, and a single
  operator. The modules are structured so moving to a GCS backend is a small
  diff, but it is not claimed here.
- **Orchestration is GitHub Actions or local Airflow, not Composer.** The
  wrapper handles one day at a time; there is no dependency-aware scheduler,
  automatic backfill, or SLA alerting beyond the alert policy in `dq/`.
- **The volume band is a trailing average with a fixed tolerance**, not a
  seasonal model or median/MAD. It needs a few days of history before it can
  alarm, and a slow multi-day decline can stay inside the band.
- **Demo-scale data.** At 800 orders/day the partition/clustering experiment
  shows a $0 delta because of BigQuery's 10 MB per-statement billing floor. The
  benchmark measures that honestly instead of extrapolating.
- **The batch path is not late-aware.** Events that miss a day's extract land in
  the next one; the streaming path is where lateness is classified and
  restated.

### What I'd do differently

Start with the remote Terraform backend and WIF from the first commit instead of
retrofitting them, and write the volume check against a seasonal baseline rather
than a flat trailing average. I would also keep the generator as a separate
published package from day one — the streaming repo consumes it as an editable
sibling path, which is convenient locally and awkward in CI.

## Layout

```
packages/eventforge/     deterministic generator (installed by ledgerline-stream too)
ingest/                  CSV load jobs, GX gate, BigQuery helpers
dq/                      Slack alerting + alert policy
warehouse/               dbt project (staging → intermediate → marts)
orchestration/           pipeline runner, Airflow DAG
infra/                   Terraform
bench/                   measured BigQuery cost benchmark
docs/adr/                architecture decision records
docs/incidents/          postmortem and game-day drill
docs/runbooks/           on-call triage and recovery per alert
```

## License

MIT — see [`LICENSE`](LICENSE).
