# Infrastructure

Terraform for the Ledgerline platform, with a **zero-cost default path**.

## Free path (default)

| Concern | Choice |
|---|---|
| Warehouse | BigQuery **sandbox** — no billing account, 1 TiB queries/month, 10 GiB storage, 60-day expiry |
| Data landing | Local CSV → BigQuery load job (no GCS) |
| Terraform state | Local, gitignored |
| Orchestration | GitHub Actions + local Airflow (no Composer) |
| Budget alerts | Not available without billing (documented in `COST.md`) |

```bash
cp envs/dev/terraform.tfvars.example envs/dev/terraform.tfvars   # set project_id
make init
make validate
make plan
make apply
```

What gets created: APIs (BigQuery, IAM), datasets `raw`/`staging`/`marts`/`ops`, three service accounts, project IAM, and a GitHub OIDC workload identity pool. No billable resources.

### Sandbox constraints that shape the design

- **No DML** → no dbt incremental models, no snapshots. Every model is a `table` or `view`.
- **No streaming inserts** → the batch path uses load jobs. (The streaming project runs entirely locally.)
- **No GCS** → the loader uploads local files directly to BigQuery.
- **60-day expiry** → demo data is disposable; the pipeline is re-runnable from a seed.

## Paid path (optional upgrade)

If you attach a billing account later:

1. `cp envs/dev/terraform.tfvars.example envs/dev/terraform.tfvars` and set:
   ```hcl
   create_landing_bucket = true
   enable_budget         = true
   billing_account_id    = "XXXXXX-XXXXXX-XXXXXX"
   ```
2. `make bootstrap` — creates the `gs://<project>-tfstate` bucket.
3. Migrate state:
   ```bash
   terraform -chdir=envs/dev init -migrate-state \
     -backend-config="bucket=$(terraform -chdir=bootstrap output -raw state_bucket)"
   ```
   and replace the `local` backend in `envs/dev/backend.tf` with the `gcs` block.
4. `make apply`.

This unlocks GCS, budget alerts, and (with a separate module) Composer.

## Ownership boundary

| Owner | Resources |
|---|---|
| Terraform | datasets, IAM, service accounts, WIF, API enablement, optional bucket/budget |
| dbt | tables and views inside `staging` and `marts` |
| ingestion jobs | tables inside `raw` and `ops` |

Terraform owns the blast radius (who can read/write, retention, cost); dbt owns transformation DDL. Duplicating table DDL in both would create two sources of truth.
