# Pipeline image for the nightly Cloud Run Job (built/deployed in Phase 6).
# Needs: Python 3.11 (importer + openstates-scrapers as a pinned CLI dep),
# Node 20 (astro build, pagefind), firebase-tools, gcloud SDK (gsutil).
FROM python:3.11-slim

# Phase 6 will add:
# - Node 20 + npm ci --ignore-scripts (hash-pinned package-lock.json)
# - uv with --require-hashes installs from uv.lock
# - openstates-scrapers pinned as a pip dependency, invoked via os-update only
# - firebase-tools + gsutil

WORKDIR /app
COPY run.sh ./
CMD ["bash", "run.sh"]
