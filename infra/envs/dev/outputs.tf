output "landing_bucket" {
  description = "Null on the free path; populate by setting create_landing_bucket = true."
  value       = module.warehouse.landing_bucket
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
