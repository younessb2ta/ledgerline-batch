variable "project_id" {
  description = "GCP project ID. A project without billing works (BigQuery sandbox)."
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

variable "github_repo" {
  description = "GitHub repository allowed to impersonate the CI service account (owner/name)."
  type        = string
  default     = "younessb2ta/ledgerline-batch"
}

variable "labels" {
  description = "Labels applied to resources."
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
      description     = "Landing tables loaded from local CSV batches."
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

# --- paid-path toggles (all default false for the sandbox) -------------------

variable "create_landing_bucket" {
  description = "Create the GCS landing bucket. Requires billing; local file loads are used instead."
  type        = bool
  default     = false
}

variable "enable_budget" {
  description = "Create a Cloud Billing budget. Requires a billing account."
  type        = bool
  default     = false
}

variable "billing_account_id" {
  description = "Billing account ID, only used when enable_budget = true."
  type        = string
  default     = ""
}

variable "budget_amount_usd" {
  description = "Monthly budget when enable_budget = true. Alerts at 20%, 50%, 100%."
  type        = number
  default     = 50
}
