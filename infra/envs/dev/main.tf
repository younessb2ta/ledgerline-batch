provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  name   = "ledgerline"
  labels = merge(var.labels, { app = local.name })
}

module "warehouse" {
  source = "../../modules/warehouse"

  project_id  = var.project_id
  region      = var.region
  bq_location = var.bq_location
  labels      = local.labels
  datasets    = var.datasets
}

module "wif" {
  source = "../../modules/wif"

  project_id  = var.project_id
  github_repo = var.github_repo
}

module "budget" {
  source = "../../modules/budget"

  billing_account_id = var.billing_account_id
  project_id         = var.project_id
  display_name       = "${local.name} monthly"
  amount_usd         = var.budget_amount_usd
}

# --- service accounts -------------------------------------------------------

resource "google_service_account" "loader" {
  account_id   = "sa-loader"
  display_name = "Ledgerline ingestion loader"
}

resource "google_service_account" "dbt" {
  account_id   = "sa-dbt"
  display_name = "Ledgerline dbt runner"
}

resource "google_service_account" "ci" {
  account_id   = "sa-ci-runner"
  display_name = "Ledgerline GitHub Actions (WIF)"
}

# --- roles ------------------------------------------------------------------

locals {
  bq_editors = {
    for key, sa in {
      loader = google_service_account.loader.email
      dbt    = google_service_account.dbt.email
      ci     = google_service_account.ci.email
    } : key => sa
  }
}

resource "google_project_iam_member" "bq_data_editor" {
  for_each = local.bq_editors

  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${each.value}"
}

resource "google_project_iam_member" "bq_job_user" {
  for_each = local.bq_editors

  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${each.value}"
}

resource "google_storage_bucket_iam_member" "loader_objects" {
  bucket = module.warehouse.landing_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.loader.email}"
}

resource "google_storage_bucket_iam_member" "dbt_read" {
  bucket = module.warehouse.landing_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_service_account_iam_member" "ci_wif" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${module.wif.pool_name}/attribute.repository/${var.github_repo}"
}
