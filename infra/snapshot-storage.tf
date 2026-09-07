# Adopt the existing bucket. Import is planned, not executed until apply.
# Never recreate it: it already contains the production SQLite snapshots.
import {
  to = google_storage_bucket.snapshots
  id = "badgerpolitics-prod-snapshots"
}

resource "google_storage_bucket" "snapshots" {
  project                     = local.prod_project
  name                        = local.snapshot_bucket
  location                    = "US-CENTRAL1"
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  # Preserve the existing seven-day recovery window. Soft-deleted bytes
  # still incur storage charges; the cost model includes them.
  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  # The existing rule expires every object after 30 days. Scope it so a
  # paused parser cannot lose its only seed or the latest manifest.
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age            = 30
      matches_prefix = ["snapshots/"]
    }
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age            = 7
      matches_prefix = [local.parser_checkpoint_prefix]
    }
  }

  # parser-state/seed/ and parser-state/latest.json have no expiry.
  # This bucket is not a Terraform backend; do not put state files here.
  lifecycle {
    prevent_destroy = true
  }
}
