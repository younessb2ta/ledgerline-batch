provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  name   = "ledgerline"
  labels = merge(var.labels, { app = local.name })

  # Free-path APIs. BigQuery can be enabled without a billing account (sandbox).
  required_apis = toset([
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "bigquery.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

module "warehouse" {
  source = "../../modules/warehouse"

  project_id    = var.project_id
  region        = var.region
  bq_location   = var.bq_location
  labels        = local.labels
  datasets      = var.datasets
  create_bucket = var.create_landing_bucket

  depends_on = [google_project_service.required]
}

module "wif" {
  source = "../../modules/wif"

  project_id  = var.project_id
  github_repo = var.github_repo

  depends_on = [google_project_service.required]
}

module "budget" {
  source = "../../modules/budget"
  count  = var.enable_budget ? 1 : 0

  billing_account_id = var.billing_account_id
  project_id         = var.project_id
  display_name       = "${local.name} monthly"
  amount_usd         = var.budget_amount_usd
}

# --- service accounts -------------------------------------------------------

resource "google_service_account" "loader" {
  account_id   = "sa-loader"
  display_name = "Ledgerline ingestion loader"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "dbt" {
  account_id   = "sa-dbt"
  display_name = "Ledgerline dbt runner"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "ci" {
  account_id   = "sa-ci-runner"
  display_name = "Ledgerline GitHub Actions (WIF)"

  depends_on = [google_project_service.required]
}

# --- roles ------------------------------------------------------------------

locals {
  bq_editors = {
    loader = google_service_account.loader.email
    dbt    = google_service_account.dbt.email
    ci     = google_service_account.ci.email
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
  count = var.create_landing_bucket ? 1 : 0

  bucket = module.warehouse.landing_bucket
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.loader.email}"
}

resource "google_storage_bucket_iam_member" "dbt_read" {
  count = var.create_landing_bucket ? 1 : 0

  bucket = module.warehouse.landing_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.dbt.email}"
}

resource "google_service_account_iam_member" "ci_wif" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${module.wif.pool_name}/attribute.repository/${var.github_repo}"
}
