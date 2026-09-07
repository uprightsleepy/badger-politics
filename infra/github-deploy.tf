# Keyless CI deploys: matching GitHub OIDC claims grant short-lived credentials.

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

  # Bind repo and ref through a mapped principal attribute; impersonation
  # conditions cannot read these claims through request.auth.claims.
  attribute_mapping = {
    "google.subject"           = "assertion.sub"
    "attribute.repository"     = "assertion.repository"
    "attribute.repository_ref" = "assertion.repository + '@' + assertion.ref"
    # Separate parser identity: require the named workflow, main, and a
    # scheduled/manual event. In particular, pull_request_target is excluded.
    "attribute.parser_workflow" = "assertion.workflow_ref + ':' + assertion.ref + ':' + assertion.event_name"
  }

  # Accept tokens only from this repository.
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

# Only main may impersonate the deployer; PR refs do not match this principal.
resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member = join("", [
    "principalSet://iam.googleapis.com/",
    google_iam_workload_identity_pool.github.name,
    "/attribute.repository_ref/${local.github_repo}@refs/heads/main",
  ])
}

# Grant Hosting deployment without project-wide editor access.
resource "google_project_iam_member" "deployer_hosting" {
  project = local.prod_project
  role    = "roles/firebasehosting.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# Snapshot reads do not grant overwrite or deletion.
resource "google_storage_bucket_iam_member" "deployer_snapshots" {
  bucket = local.snapshot_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.deployer.email}"
}

# Bucket listing lets gcloud resolve the newest snapshot.
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

# Pushes release to dev; production promotion is manual.
resource "google_project_iam_member" "deployer_hosting_dev" {
  project = local.dev_project
  role    = "roles/firebasehosting.admin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}
