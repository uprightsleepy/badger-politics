# Badger Politics infrastructure. Never apply without approval.
# Site releases already use GitHub Actions and Workload Identity Federation.
# The nightly parser reuses free public-repository runners and the
# existing private GCS bucket; see docs/nightly-parser-hosting.md for costs
# and activation instructions. Terraform does not enable a schedule.

locals {
  # Cloud data and identities live in prod; hosting also has a dev target.
  prod_project    = "badgerpolitics-prod"
  dev_project     = "badgerpolitics-dev"
  region          = "us-central1"
  snapshot_bucket = "badgerpolitics-prod-snapshots"
  github_repo     = "uprightsleepy/badger-politics"
}

provider "google" {
  project = local.prod_project
  region  = local.region
}
