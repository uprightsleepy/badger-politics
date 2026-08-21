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
# cumulative: current biennium plus every archived session, or the
# import wipes history and the bill-count gate kills the run
python -m importer.import_openstates _data/wi _data/sessions/*/ ../data/wi.sqlite

# --- Phase 2: derived features + elections (CYCLE = active election year) ---
CYCLE="${CYCLE:-2026}"
python -m scraper.fetch_wec                   # WEC ballot-access report (PDF)
python -m importer.wec_pdf _data/wec/ballot-access.pdf _data/wec/candidates-${CYCLE}.csv
python -m importer.elections ../data/wi.sqlite --cycle "$CYCLE"
python -m importer.import_wec _data/wec/candidates-${CYCLE}.csv ../data/wi.sqlite --cycle "$CYCLE"

python -m scraper.fetch_wec_results           # pinned canvass files (no-op when present)
python -m importer.import_wec_results _data/wec-results ../data/wi.sqlite

python -m scraper.fetch_cfis map ../data/wi.sqlite
python -m scraper.fetch_cfis transactions     # nightly delta (past months cached)
python -m scraper.fetch_cfis audit --sample 3 # rotating amendment check on history
python -m importer.import_cfis _data/cfis ../data/wi.sqlite

python -m scraper.fetch_lobbying --refresh    # per-bill registered principals
python -m importer.import_lobbying _data/lobbying ../data/wi.sqlite

python -m importer.enrich_lrb ../data/wi.sqlite
python -m importer.checks ../data/wi.sqlite   # hard gate: abort deploy on failure

# --- Phase 3: static JSON API, feeds, calendars, bulk exports ---
python -m dataproducts.build ../data/wi.sqlite ../site/public/

# --- Phase 5+: site build, deploy ---
# (cd ../site && npm run build)               # astro reads data/wi.sqlite
# npx pagefind --site ../site/dist
# firebase deploy --only hosting --project "$FB_PROJECT" --non-interactive
# gsutil cp ../data/wi.sqlite "gs://$BUCKET/snapshots/wi-$(date +%F).sqlite"
