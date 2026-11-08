# ADR-0001 — GCP + BigQuery on the sandbox, not a billed project

**Status:** Accepted · 2026-11-07

## Context

The platform is meant to demonstrate cloud-native data engineering on GCP:
BigQuery, IAM, service accounts, and Workload Identity Federation. The
available Google account has **no billing account**. Cloud Storage, Composer,
budget alerts, and streaming inserts all require one, even inside the free
tier.

## Decision

Run against a **BigQuery sandbox** project (`ledgerline-514016`,
`billingEnabled=false`) and move the edges that need billing to local
equivalents:

| Concern | Paid design | This build |
|---|---|---|
| Warehouse | BigQuery + billing | BigQuery sandbox |
| Landing zone | GCS bucket | local CSV → BigQuery load jobs |
| Orchestration | Composer | GitHub Actions + local Airflow |
| Terraform state | GCS backend | local (gitignored) |
| Budget alerts | $10/$25/$50 | measured cost benchmark (`bench/report.md`) |

Terraform, IAM, and WIF are real cloud resources. Only the services that
require a payment method are substituted.

## Alternatives considered

1. **Attach a billing account.** Rejected: not available.
2. **AWS free tier / local Postgres + DuckDB.** Would lose the GCP/IAM story
   that the target roles ask for. BigQuery remains the system of record.
3. **Emulators only.** Rejected: emulators cannot demonstrate WIF, IAM, or
   load-job semantics.

## Consequences

- **No DML:** `MERGE`, `DELETE`, `UPDATE` are rejected. This drives ADR-0009
  (table/view-only dbt) and makes load jobs the only write path.
- **No streaming inserts:** irrelevant for the batch path; the streaming
  project is fully local.
- **60-day table expiry:** acceptable because every batch is reproducible from
  `eventforge` seed + Terraform.
- **10 GiB storage / 1 TiB queries per month:** the whole demo uses ~0.7 MiB of
  storage and ~0.02 TiB of queries per month per the measured benchmark.
- **Honest cost story:** the paid equivalent is measured, not estimated —
  roughly **$0.30/month** for the demo workload at list prices.

Upgrade path: attach a billing account, flip `create_landing_bucket` and
`enable_budget` in Terraform, migrate state, re-point the dbt profile. No model
changes.
