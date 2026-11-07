variable "billing_account_id" {
  type = string
}

variable "project_id" {
  type = string
}

variable "display_name" {
  type = string
}

variable "amount_usd" {
  type    = number
  default = 50
}

resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account_id
  display_name    = var.display_name

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.amount_usd)
    }
  }

  budget_filter {
    projects = ["projects/${var.project_id}"]
  }

  threshold_rules {
    threshold_percent = 0.2
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 1.0
  }
}

output "name" {
  value = google_billing_budget.monthly.name
}
