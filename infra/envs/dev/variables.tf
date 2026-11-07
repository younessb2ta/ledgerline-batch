variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "Default region."
  type        = string
  default     = "us-central1"
}

variable "bq_location" {
  description = "BigQuery dataset location."
  type        = string
  default     = "US"
}

variable "billing_account_id" {
  description = "Billing account ID (without the billingAccounts/ prefix)."
  type        = string
}

variable "budget_amount_usd" {
  description = "Monthly budget. Threshold alerts fire at 20%, 50%, and 100%."
  type        = number
  default     = 50
}

variable "github_repo" {
  description = "GitHub repository allowed to impersonate the CI service account (owner/name)."
  type        = string
  default     = "younessb2ta/ledgerline-batch"
}

variable "labels" {
  description = "Labels applied to billable resources."
  type        = map(string)
  default = {
    platform = "ledgerline"
    env      = "dev"
    owner    = "younessb2ta"
  }
}

variable "datasets" {
  description = "BigQuery datasets owned by Terraform."
  type = map(object({
    description     = string
    expiration_days = optional(number)
  }))
  default = {
    raw = {
      description     = "Landing tables loaded from GCS by the ingestion job."
      expiration_days = null
    }
    staging = {
      description     = "dbt staging models."
      expiration_days = null
    }
    marts = {
      description     = "dbt marts: star schema served to dashboards."
      expiration_days = null
    }
    ops = {
      description     = "Data quality results, load audit, cost benchmarks. Short retention."
      expiration_days = 30
    }
  }
}
