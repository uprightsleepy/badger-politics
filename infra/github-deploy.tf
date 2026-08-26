# Keyless CI deploys: GitHub Actions federates into a deploy service account
# through Workload Identity, so nothing long-lived is stored in the repo.
#
# There is no service-account key here on purpose. A JSON key in a GitHub
# secret is a credential that never expires and is exfiltrable by anything
# that can read the runner; a federated token lasts an hour and is minted
# only for a run whose OIDC claims match the conditions below.

resource "google_project_service" "deploy_apis" {
  for_each = toset([
    "iamcredentials.googleapis.com", # mints the short-lived access token
    "sts.googleapis.com",            # exchanges the GitHub OIDC token
    "iam.googleapis.com",
    "firebasehosting.googleapis.com",
  ])
  project            = local.prod_project
  service            = each.value
  disable_on_destroy = false
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = local.prod_project
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  description               = "Federated identity for ${local.github_repo}"
  depends_on                = [google_project_service.deploy_apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = local.prod_project
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # First gate: the token must come from this repository. Without this, any
  # GitHub repo anywhere could exchange a token against this pool.
  attribute_condition = "assertion.repository == '${local.github_repo}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  project      = local.prod_project
  account_id   = "gha-site-deployer"
  display_name = "GitHub Actions site deployer"
  description  = "Reads a SQLite snapshot and releases Firebase Hosting. No write access to data."
}

# Second gate: only main may impersonate the deployer. A pull request runs
# with a ref of refs/pull/N/merge, so it cannot assume this identity even
# though it comes from the right repository -- deploys never run from a PR.
resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member = join("", [
    "principalSet://iam.googleapis.com/",
    google_iam_workload_identity_pool.github.name,
    "/attribute.repository/${local.github_repo}",
  ])
  condition {
    title       = "main branch only"
    description = "Blocks pull requests and every other ref from deploying"
    expression  = "request.auth.claims['attribute.ref'] == 'refs/heads/main'"
  }
}

# Release Firebase Hosting. Deliberately not roles/editor: the deployer can
# publish the site and nothing else in the project.
resource "google_project_iam_member" "deployer_hosting" {
  project = local.prod_project
  role    = "roles/firebasehosting.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Read the newest SQLite snapshot. Object-level read only: CI can never
# overwrite or delete a snapshot, so a compromised run cannot destroy the
# only copy of the database.
resource "google_storage_bucket_iam_member" "deployer_snapshots" {
  bucket = local.snapshot_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.deployer.email}"
}

# Listing lives on the bucket, not the object, and `gcloud storage ls`
# needs it to find the newest snapshot.
resource "google_storage_bucket_iam_member" "deployer_list" {
  bucket = local.snapshot_bucket
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.deployer.email}"
}

output "workload_identity_provider" {
  description = "Value for the workflow's google-github-actions/auth step"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "Service account the workflow impersonates"
  value       = google_service_account.deployer.email
}

# The dev project is the rehearsal target: workflow_dispatch can release
# there to prove a change before main releases to production.
resource "google_project_iam_member" "deployer_hosting_dev" {
  project = local.dev_project
  role    = "roles/firebasehosting.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}
