# Cost

**Actual spend on this project: $0.00.** The GCP project has no billing account
(`billingEnabled=false`), so no chargeable service can be enabled by accident.
This file records what the workload *would* cost and which services were
rejected to keep it free.

All numbers are measured, not estimated. Regenerate them with:

```bash
cd ledgerline-batch
uv run python -m bench.benchmark --project <project>
```

The generated report is [`bench/report.md`](bench/report.md); this file is the
short version and the decision record.

## Measured — one full pipeline run

| Metric | Value |
|---|---:|
| Nodes | 72 (13 models, 57 tests) |
| Wall time | 35.6 s |
| Bytes processed | 1.03 MiB |
| Bytes billed | 0.72 GiB |
| Paid equivalent @ $6.25/TiB | **$0.00441** |

`bytes_billed` is ~700× `bytes_processed` because BigQuery bills a **10 MB
minimum per statement** and this run issues 72 statements. At production data
volume the floor stops mattering; at demo volume it dominates.

## Measured — dashboard and storage

| Item | Measured | Paid equivalent |
|---|---:|---:|
| 4 representative dashboard/reconciliation queries | 40 MiB billed | $0.00024 per load |
| Active storage, 21 tables | 0.62 MiB | $0.0000/month |
| Staging/intermediate | views (0 bytes) | $0 |

## Monthly projection

| Item | Volume / month | Cost / month |
|---|---:|---:|
| Pipeline, 1 run/day | 21.7 GiB billed | $0.13 |
| Dashboard, 24 loads/day | 28.1 GiB billed | $0.17 |
| Storage | 0.0006 GiB | $0.00 |
| **Total** | **49.8 GiB billed** | **$0.30** |

Against the sandbox allowance of 1 TiB of queries and 10 GiB of storage, the
workload uses **~5% of the query allowance and 0.006% of storage**.

## Partition and clustering experiment

`raw_orders` is partitioned by `DAY(order_ts)` and clustered by `customer_id`;
`raw_payments` is partitioned by `DAY(paid_ts)` and clustered by `order_id`.
A clone of `raw_payments` was created without partitioning and the same three
queries were dry-run against both, then the clone was dropped.

| Query | Partitioned table | Unpartitioned clone | Billed cost delta |
|---|---:|---:|---:|
| full scan (`sum(amount_cents)`) | ~6 KB | ~6 KB | $0 |
| one-day filter (`paid_ts >= 2026-11-03`) | 0 B (pruned) | ~12 KB | $0 |
| cluster filter (`order_id = …`) | ~22 KB | ~22 KB | $0 |

Two honest conclusions:

1. **At demo scale the dollar delta is exactly $0.** Every query hits the 10 MB
   billing floor, so pruning cannot show up in the invoice. Reporting a
   "savings percentage" here would be meaningless.
2. **The pruning works; the table is just too small to price.** Partition
   pruning reduced scanned bytes for the day filter to zero (metadata-based
   short-circuit). At production scale — say a 1 TiB table and a one-day filter
   over a year of partitions — the same pruning scans ~1/365 of the data:
   $6.25 becomes ~$0.02 for that query. That is the number to quote in an
   interview, clearly labeled as a scaled model rather than a measurement.

Dry runs do not apply cluster pruning to their byte estimate, so the cluster
row is not evidence either way; clustering savings would only appear in real
execution on a table large enough to matter.

## Services rejected to stay at $0

| Service | Why it was rejected | Free-path substitute |
|---|---|---|
| Composer | requires billing; runs a GKE cluster hourly | GitHub Actions schedule + local Airflow DAG |
| Cloud Storage | requires billing | local CSV → BigQuery load jobs |
| Streaming inserts | requires billing | batch load jobs; streaming project is local |
| Budget alerts | require a billing account | per-query `maximum_bytes_billed = 1 GB` + measured benchmark |
| GCS Terraform backend | requires billing | local, gitignored state |

Composer has **not** been created or destroyed — it was never created. The DAG
(`orchestration/dags/ledgerline_batch.py`) and the Terraform flags exist so the
upgrade is a configuration change, not a rewrite.

## Guardrails that work without billing

- `warehouse/profiles.yml`: `maximum_bytes_billed: 1073741824` — a query that
  would scan more than 1 GB fails instead of running.
- The pipeline only queries tables it just loaded; there are no unbounded
  ad-hoc scans in the scheduled path.
- Sandbox quota itself is the hard stop: 1 TiB/month of queries and 10 GiB of
  storage. Exceeding it fails the query; it cannot generate a bill.
- Demo data is reproducible from `eventforge` seed + Terraform, so the 60-day
  table expiry has no recovery cost.
