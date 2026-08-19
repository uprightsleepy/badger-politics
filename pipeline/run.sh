#!/usr/bin/env bash
# The entire nightly job: scrape -> import -> check -> build -> deploy.
# Flags: --local (skip GCS snapshot upload), --skip-deploy (skip firebase deploy).
# Steps are enabled phase-by-phase; anything not yet implemented fails loudly.
set -euo pipefail

echo "Phase 1+: pipeline steps are not implemented yet." >&2
exit 1

# --- target shape (docs plan §5) ---
# os-update wi bills --scrape --fastmode        # openstates scraper -> _data/wi/*.json
# os-update wi events --scrape                  # committee hearing schedules
# python -m importer.import_openstates _data/wi data/wi.sqlite
# python -m importer.checks data/wi.sqlite      # hard gate
# python -m dataproducts.build data/wi.sqlite site/public/
# (cd site && npm run build)                    # astro reads data/wi.sqlite
# npx pagefind --site site/dist
# firebase deploy --only hosting --project "$FB_PROJECT" --non-interactive
# gsutil cp data/wi.sqlite "gs://$BUCKET/snapshots/wi-$(date +%F).sqlite"
