variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "bq_location" {
  type = string
}

variable "labels" {
  type = map(string)
}

variable "datasets" {
  type = map(object({
    description     = string
    expiration_days = optional(number)
  }))
}

resource "google_bigquery_dataset" "datasets" {
  for_each = var.datasets

  project                    = var.project_id
  dataset_id                 = each.key
  friendly_name              = "ledgerline ${each.key}"
  description                = each.value.description
  location                   = var.bq_location
  labels                     = var.labels
  delete_contents_on_destroy = true

  default_table_expiration_ms = try(each.value.expiration_days * 86400000, null)
}

resource "google_storage_bucket" "landing" {
  name                        = "${var.project_id}-ledgerline-landing"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = true
  labels                      = var.labels

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

output "dataset_ids" {
  value = { for key, dataset in google_bigquery_dataset.datasets : key => dataset.dataset_id }
}

output "landing_bucket" {
  value = google_storage_bucket.landing.name
}
