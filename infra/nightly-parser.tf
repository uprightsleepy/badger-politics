# Infrastructure for .github/workflows/nightly-parser.yml.
# Scheduled collection is gated by the NIGHTLY_PARSER_ENABLED repository variable.
locals {
  nightly_parser_workflow_ref = "${local.github_repo}/.github/workflows/nightly-parser.yml@refs/heads/main"
  parser_state_prefix         = "parser-state/"
  parser_checkpoint_prefix    = "${local.parser_state_prefix}checkpoints/"
  parser_manifest_object      = "${local.parser_state_prefix}latest.json"
  parser_lock_object          = "${local.parser_state_prefix}lock.json"
  storage_object_prefix       = "projects/_/buckets/${local.snapshot_bucket}/objects/"
}

resource "google_service_account" "nightly_parser" {
  project      = local.prod_project
  account_id   = "gha-nightly-parser"
  display_name = "GitHub Actions nightly parser"
  description  = "Reads private source archives and appends validated SQLite snapshots. No hosting role."
  depends_on   = [google_project_service.deploy_apis]
}

resource "google_service_account_iam_member" "nightly_parser_wif" {
  for_each = toset(["schedule", "workflow_dispatch"])

  service_account_id = google_service_account.nightly_parser.name
  role               = "roles/iam.workloadIdentityUser"
  member = join("", [
    "principalSet://iam.googleapis.com/",
    google_iam_workload_identity_pool.github.name,
    "/attribute.parser_workflow/",
    "${local.nightly_parser_workflow_ref}:refs/heads/main:${each.value}",
  ])
  depends_on = [google_iam_workload_identity_pool_provider.github]
}

# Object reads are restricted to source state. The seed is provisioned by
# an operator: the parser cannot replace or delete its recovery baseline.
resource "google_storage_bucket_iam_member" "parser_state_reader" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.nightly_parser.email}"

  condition {
    title       = "read_parser_state"
    description = "Read the source seed, checkpoints, and latest manifest."
    expression  = "resource.name.startsWith('${local.storage_object_prefix}${local.parser_state_prefix}')"
  }
}

# Cloud Storage cannot restrict object listing to a prefix through IAM.
# This grants bucket metadata and object-name listing, not object contents.
resource "google_storage_bucket_iam_member" "parser_list" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.legacyBucketReader"
  member = "serviceAccount:${google_service_account.nightly_parser.email}"
}

# Unique checkpoint/snapshot names plus if-generation-match=0 in the
# uploader prevent overwrites. Lifecycle expiration handles old objects.
resource "google_storage_bucket_iam_member" "parser_append" {
  for_each = {
    checkpoints = local.parser_checkpoint_prefix
    snapshots   = "snapshots/"
  }

  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.nightly_parser.email}"

  condition {
    title       = "append_${each.key}"
    description = "Create new ${each.key}; cannot overwrite or delete existing objects."
    expression  = "resource.name.startsWith('${local.storage_object_prefix}${each.value}')"
  }
}

# Recognize an upload that succeeded before a retried publication was interrupted.
resource "google_storage_bucket_iam_member" "parser_snapshot_reader" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.nightly_parser.email}"

  condition {
    title       = "read_parser_snapshots"
    description = "Verify an already-published snapshot during idempotent recovery."
    expression  = "resource.name.startsWith('${local.storage_object_prefix}snapshots/')"
  }
}

# Replacing the pointer/lock requires delete as well as create. Keep that
# power on exactly these control objects, never on data or the seed.
resource "google_storage_bucket_iam_member" "parser_manifest_writer" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.nightly_parser.email}"

  condition {
    title       = "update_parser_manifest"
    description = "Update the manifest and execution lock with generation preconditions."
    expression = join(" || ", [
      "resource.name == '${local.storage_object_prefix}${local.parser_manifest_object}'",
      "resource.name == '${local.storage_object_prefix}${local.parser_lock_object}'",
    ])
  }
}

output "nightly_parser_service_account" {
  description = "Nightly workflow repository variable GCP_PARSER_SA."
  value       = google_service_account.nightly_parser.email
}

output "nightly_parser_storage" {
  description = "Private storage contract for source restoration and checkpoints."
  value = {
    seed        = "gs://${local.snapshot_bucket}/${local.parser_state_prefix}seed/"
    checkpoints = "gs://${local.snapshot_bucket}/${local.parser_checkpoint_prefix}"
    manifest    = "gs://${local.snapshot_bucket}/${local.parser_manifest_object}"
    lock        = "gs://${local.snapshot_bucket}/${local.parser_lock_object}"
    snapshots   = "gs://${local.snapshot_bucket}/snapshots/"
  }
}
