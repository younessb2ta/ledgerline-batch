terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

# Partial backend: the bucket is supplied at init time from bootstrap output.
#   terraform init -backend-config="bucket=<project>-tfstate"
terraform {
  backend "gcs" {
    prefix = "envs/dev"
  }
}
