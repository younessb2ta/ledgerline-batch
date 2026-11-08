# ADR-0008 — GitHub Actions + local Airflow instead of Composer

**Status:** Accepted · 2026-11-07

## Context

Composer is the natural GCP orchestrator, but every Composer environment
requires a billing account and runs a GKE cluster, which costs money even for
a 48-hour demo. The zero-cost path has no billing account (ADR-0001).

## Decision

Keep the pipeline as a **plain Python entry point** and provide two thin
wrappers:

- `orchestration/run_pipeline.py` — the single implementation: stage order,
  gates, alerts, run summary.
- `.github/workflows/pipeline.yml` — scheduled (`cron: 0 6 * * *`) and manual
  runs, keyless auth via Workload Identity Federation, run summary uploaded as
  an artifact.
- `orchestration/dags/ledgerline_batch.py` — an Airflow DAG for environments
  that have Airflow; it shells out to the same entry point.

Composer therefore needs no rewrite: deploy the DAG, set `gcp_project` and
`slack_webhook_url` as Airflow variables. Terraform keeps the
`enable_composer`-style flags in the paid path.

## Alternatives considered

1. **Always-on Composer.** Rejected: cost.
2. **Composer 48 h demo.** Rejected: still requires billing, and the value is
   in the DAG, not the managed scheduler.
3. **Cron on a laptop.** Rejected: not portable, no audit trail.
4. **GitHub Actions only.** Viable, but a DAG artifact shows the Airflow
   boundary explicitly and matches what most teams actually run.

## Consequences

- CI auth is keyless (OIDC → WIF); no service-account key exists in the repo.
- Actions cron is best-effort (delays under load); acceptable for a demo, and
  the freshness test measures `loaded_at`, so delays are visible rather than
  silent.
- Alerts are best-effort by design: a missing webhook prints the payload and
  never masks the pipeline's exit code.
- Switching to Composer is a deployment decision, not a code change.
