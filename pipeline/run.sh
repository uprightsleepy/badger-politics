#!/usr/bin/env bash
# The entire nightly job: scrape -> import -> enrich -> check -> build -> deploy.
# Flags: --local (skip GCS snapshot upload), --skip-deploy (skip firebase deploy).
set -euo pipefail

cd "$(dirname "$0")"

LOCAL=0
SKIP_DEPLOY=0
for arg in "$@"; do
  case "$arg" in
    --local) LOCAL=1 ;;
    --skip-deploy) SKIP_DEPLOY=1 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# Deploy target defaults to dev: promoting to prod is always explicit, so a
# stray or automated run can never overwrite the live site.
FB_PROJECT="${FB_PROJECT:-badgerpolitics-dev}"
BUCKET="${BUCKET:-badgerpolitics-prod-snapshots}"

# Cloud-writing laptop runs share the scheduler's lock. --local retains its
# offline-storage behavior and must still be coordinated with other scrapes.
if [ "$LOCAL" -eq 0 ]; then
  nightly_lock_owner="local-$(python -c 'import uuid; print(uuid.uuid4().hex)')"
  python -m nightly.local_lock acquire --owner "$nightly_lock_owner" --bucket "$BUCKET"
  release_nightly_lock() {
    status=$?
    python -m nightly.local_lock release --owner "$nightly_lock_owner" --bucket "$BUCKET" || status=1
    exit "$status"
  }
  trap release_nightly_lock EXIT
fi

# --- Phase 1: scrape + import (never run two scrapes concurrently) ---
python -m scraper.scrape bills            # os-update wi bills --scrape (policy-checked)
python -m scraper.scrape events           # os-update wi events --scrape
python -m scraper.fetch_people            # openstates/people WI roster (YAML)
python -m scraper.fetch_committees        # committee rosters + chairs (YAML)
# cumulative: current biennium plus every archived session, or the
# import wipes history and the bill-count gate kills the run
python -m importer.import_openstates _data/wi _data/sessions/*/ ../data/wi.sqlite

# --- Phase 2: derived features + elections (CYCLE = active election year) ---
CYCLE="${CYCLE:-2026}"
# WEC downloads paused 2026-09-07: terms recheck returned 403; use local reports.
python -m importer.wec_pdf _data/wec/ballot-access.pdf _data/wec/candidates-${CYCLE}.csv
python -m importer.elections ../data/wi.sqlite --cycle "$CYCLE"
python -m importer.import_wec _data/wec/candidates-${CYCLE}.csv ../data/wi.sqlite --cycle "$CYCLE"

# Existing pinned canvass files remain available offline.
python -m importer.import_wec_results _data/wec-results ../data/wi.sqlite

python -m scraper.fetch_cfis map ../data/wi.sqlite
python -m scraper.fetch_cfis transactions     # nightly delta (past months cached)
python -m scraper.fetch_cfis audit --sample 3 # rotating amendment check on history
python -m importer.import_cfis _data/cfis ../data/wi.sqlite

# non-candidate committee money: PACs, parties, conduits, and express
# advocacy. Same feed as above, windowed by date rather than committee.
python -m scraper.fetch_cf_committees --since 2025-01
python -m importer.import_cf_committees _data/cfis ../data/wi.sqlite

# Automated lobbying retrieval removed 2026-09-07: robots.txt disallows crawling.
# It may return later with site approval and a fresh robots.txt/terms review.
# Retain the complete local archive: the main import rebuilds the database.
python -m importer.import_lobbying _data/lobbying ../data/wi.sqlite

python -m scraper.fetch_subjects              # subject index (current refreshes)
python -m importer.import_subjects _data/subjects ../data/wi.sqlite

# WisconsinEye retrieval paused 2026-09-07 pending approval for metadata reuse
# under its user agreement. Only the existing local archive is read here.
python -m importer.import_wiseye _data/wiseye/videos.json ../data/wi.sqlite

python -m scraper.fetch_contacts --refresh    # Capitol office contacts (docs.legis)
python -m importer.import_contacts _data/contacts/contacts.json ../data/wi.sqlite

python -m scraper.fetch_federal_votes           # U.S. Senate roll calls + roster
python -m importer.import_federal _data/federal ../data/wi.sqlite

python -m scraper.fetch_local_votes             # council votes (Legistar; cached)
python -m scraper.fetch_local_profiles          # portraits + contacts from city pages
python -m importer.import_local _data/local ../data/wi.sqlite

python -m importer.enrich_lrb ../data/wi.sqlite
python -m importer.enrich_companions ../data/wi.sqlite
python -m importer.checks ../data/wi.sqlite   # hard gate: abort deploy on failure

# --- Phase 3: static JSON API, feeds, calendars, bulk exports ---
python -m dataproducts.build ../data/wi.sqlite ../site/public/

# --- Phase 5+: site build, deploy ---
# BUILD_SESSIONS=all: every session gets pages so profile links to
# historical bills and votes always resolve (dev builds default partial).
# npm run build also runs pagefind, so the index matches what was built.
(cd ../site && BUILD_SESSIONS=all npm run build)

# A Hosting release replaces the whole site, so a build that came up short
# deletes every page it omits. Assert the built tree against the database
# that produced it before anything is published.
(cd ../site && node scripts/preflight.mjs)

if [ "$SKIP_DEPLOY" -eq 0 ]; then
  # runs from the repo root: firebase.json maps hosting to site/dist
  (cd .. && firebase deploy --only hosting --project "$FB_PROJECT" --non-interactive)
else
  echo "skipping firebase deploy (--skip-deploy)"
fi

if [ "$LOCAL" -eq 0 ]; then
  # Compressed: the snapshot goes 397MB -> ~90MB, and CI pulls one on every
  # deploy, so uncompressed egress alone would eat most of the cost ceiling.
  # gcloud storage, not gsutil: gsutil is pinned to Python <=3.12
  snapshot_id="$(date -u +%Y-%m-%dT%H%M%S)-$(python -c 'import uuid; print(uuid.uuid4().hex)')"
  gzip -6 -c ../data/wi.sqlite | gcloud storage cp - "gs://$BUCKET/snapshots/wi-${snapshot_id}.sqlite.gz"
else
  echo "skipping snapshot upload (--local)"
fi
