terraform {
  # Free path: local state (gitignored).
  # If you later enable billing, switch to the GCS backend created by infra/bootstrap
  # and run: terraform init -migrate-state -backend-config="bucket=<project>-tfstate"
  backend "local" {
    path = "terraform.tfstate"
  }
}
