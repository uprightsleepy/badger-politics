#!/usr/bin/env bash
# The entire nightly job: scrape -> import -> enrich -> check (-> build -> deploy).
# Flags: --local (skip GCS snapshot upload), --skip-deploy (skip firebase deploy).
# Later-phase steps stay commented until implemented; nothing fails silently.
set -euo pipefail

cd "$(dirname "$0")"

# --- Phase 1: scrape + import (never run two scrapes concurrently) ---
python -m scraper.scrape bills            # os-update wi bills --scrape --fastmode
python -m scraper.scrape events           # os-update wi events --scrape
python -m scraper.fetch_people            # openstates/people WI roster (YAML)
python -m scraper.fetch_committees        # committee rosters + chairs (YAML)
python -m importer.import_openstates _data/wi ../data/wi.sqlite
python -m importer.enrich_lrb ../data/wi.sqlite
python -m importer.checks ../data/wi.sqlite   # hard gate: abort deploy on failure

# --- Phase 3+: data products, site build, deploy ---
# python -m dataproducts.build ../data/wi.sqlite ../site/public/
# (cd ../site && npm run build)               # astro reads data/wi.sqlite
# npx pagefind --site ../site/dist
# firebase deploy --only hosting --project "$FB_PROJECT" --non-interactive
# gsutil cp ../data/wi.sqlite "gs://$BUCKET/snapshots/wi-$(date +%F).sqlite"
