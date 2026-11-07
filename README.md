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

This repo currently contains **Phases 0–2**: the deterministic generator, the zero-cost Terraform layout, and the ingestion path with its Great Expectations gate. dbt models come next.

Phase 0 exit criteria:

- [x] `uv sync` works from a clean clone (Python 3.11, workspace package)
- [x] `pytest` green — 11 tests covering determinism, manifest integrity, balances, and incident modes
- [x] same seed ⇒ byte-identical manifest hashes; different seed ⇒ different data
- [x] `truncated` produces a self-consistent dataset at ~40% volume (manifest matches the file, so only the mart volume test can catch it)
- [x] `schema_drift`, `duplicate_pk`, `stale` each produce a plausible single failure
- [x] toolchain installed: uv/Python 3.11, Terraform 1.17, JDK 17, Maven 3.10, gcloud 592 — see `../docs/toolchain.md`
- [ ] Docker (macOS 12 compatibility — see `../docs/toolchain.md`), Git identity for the first commit

## Quickstart

Requires `uv` (https://docs.astral.sh/uv/).

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

## Layout

```
packages/eventforge/     deterministic generator (installed by ledgerline-stream too)
ingest/                  CSV load jobs, GX gate, BigQuery helpers
dq/                      GX suites + runbooks                            [Phase 4]
warehouse/               dbt project                                     [Phase 3]
orchestration/           Airflow DAGs + Slack callback                    [Phase 4]
infra/                   Terraform                                        [Phase 1]
bench/                   BigQuery partition/cluster cost benchmark        [Phase 5]
docs/adr, docs/incidents ADRs and real-incident postmortems               [Phase 5]
```
