# Infrastructure

Two-stage Terraform setup:

1. **`bootstrap/`** — local state. Enables APIs and creates the GCS bucket that will hold the real state. Run once per project.
2. **`envs/dev/`** — remote GCS state. Datasets, landing bucket, service accounts, Workload Identity Federation, budget alerts.

```bash
make bootstrap        # first time only, local state
make init             # reads the state bucket from bootstrap output
make validate
make plan
make apply
```

## Why two stages

Terraform can't store its state in a bucket it hasn't created yet. The standard resolution is a small bootstrap layer with local state, then `-backend-config` for the real environment. The bootstrap layer is intentionally tiny and rarely changes.

## Ownership boundary

| Owner | Resources |
|---|---|
| Terraform | datasets, landing bucket, IAM, service accounts, WIF, budgets, API enablement |
| dbt | tables and views inside `staging` and `marts` |
| ingestion jobs | tables inside `raw` and `ops` |

This is deliberate. dbt already owns table DDL and lineage; duplicating it in Terraform creates two sources of truth. Terraform owns the blast radius (who can read/write, how long data lives, how much it costs), dbt owns the transformation layer.

## Before apply

- `gcloud auth application-default login` must be done.
- `terraform.tfvars` must exist in `envs/dev/` (copy `terraform.tfvars.example`).
- The GitHub repo must match `github_repo` for the WIF attribute condition.
