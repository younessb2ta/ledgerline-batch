output "landing_bucket" {
  value = module.warehouse.landing_bucket
}

output "datasets" {
  value = module.warehouse.dataset_ids
}

output "ci_service_account" {
  value = google_service_account.ci.email
}

output "workload_identity_provider" {
  description = "Value for google-github-actions/auth workload_identity_provider."
  value       = module.wif.provider_name
}

output "budget_name" {
  value = module.budget.name
}
