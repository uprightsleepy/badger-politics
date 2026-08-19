# Badger Politics infrastructure (applied in Phase 6 — never `tofu apply`
# without asking). Planned resources, all free-tier or near-zero cost:
#   - project services (run, cloudscheduler, artifactregistry, secretmanager)
#   - GCS bucket: SQLite snapshots, scraper JSON archive, tfstate
#   - Artifact Registry: pipeline image
#   - Cloud Run Job: nightly scrape -> import -> build -> deploy
#   - Cloud Scheduler: 5:15am America/Chicago trigger
#   - least-privilege service accounts (job SA, GitHub Actions WIF SA)
#   - Cloud Monitoring log-based alert on job failure -> email

locals {
  project_id = "wi-bills-prod"
  region     = "us-central1"
}
