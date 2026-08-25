# Badger Politics

Free, static Wisconsin politics site (v1: legislature module). badgerpolitics.org. Nightly Cloud Run Job:
openstates-scrapers (wi) → SQLite → Astro static build → Firebase Hosting.

## Commands
- Pipeline (local): `cd pipeline && uv run ./run.sh --local --skip-deploy`
- Import only: `uv run python -m importer.import_openstates _data/wi data/wi.sqlite`
- Checks: `uv run python -m importer.checks data/wi.sqlite`
- Site dev: `cd site && npm run dev`   Build: `npm run build`
- Tests: `uv run pytest pipeline/tests`
- Infra: `cd infra && tofu plan` (never apply without asking)
- Deploy dev: `cd pipeline && ./run.sh --local` (FB_PROJECT defaults to badgerpolitics-dev)
- Deploy prod: `FB_PROJECT=badgerpolitics-prod ./run.sh` (explicit on purpose)
- Site only: `firebase deploy --only hosting --project badgerpolitics-dev`

## Deploy targets
- `badgerpolitics-dev` -> https://badgerpolitics-dev.web.app
- `badgerpolitics-prod` -> https://badgerpolitics-prod.web.app, badgerpolitics.org (www 301s to apex; .com 301s via Porkbun forwarding)
- Snapshots: `gs://badgerpolitics-prod-snapshots/snapshots/` (private, 30-day lifecycle)
- run.sh defaults to dev; prod requires setting FB_PROJECT explicitly.

## Hard rules
- SQLite is the only database. Never introduce Cloud SQL/Firestore/Postgres.
- Integrity checks gate deploys. Never weaken a check to make a run pass;
  fix the scraper/importer or fail the run.
- Rows with source='legiscan' must never be exposed via bulk export.
- Do not modify vendored/pinned openstates-scrapers code in-tree; write
  patches in pipeline/patches/ and document upstream PR intent.
- Keep the serving path 100% static. No servers, no functions, no LLM calls.
- Cost ceiling is ~$2/mo: reject any change that adds a paid GCP resource.
- Every page footer must include the independence disclaimer (see site/src/components/Footer).
- Analytics = GoatCounter only. Never add Google Analytics, tracking cookies, or any consent-banner-requiring script.
- Personalization is localStorage-only. No accounts, no server-side user data; addresses are never transmitted except to the Census geocoder, never stored.
- The static JSON API and all exports are provenance-filtered: source='legiscan' rows never leave the SQLite.
- Interact with openstates-scrapers ONLY as a subprocess CLI (os-update). Never `import` their modules into our Apache-2.0 code (GPL boundary).
- Vote attribution: match against a session-scoped roster; any ambiguous surname is a hard failure, never a best guess.
- Dependencies are hash-pinned (uv.lock / package-lock.json); `npm ci --ignore-scripts` in the pipeline image. No deploy ever runs from a PR.
- LTSB GeoJSON is the authoritative district source; Census is geocoding only.

## Gotchas
- docs.legis subject-index page is infinite-scrolled; scraper handles it — don't "fix".
- Assembly roll calls: Y/N/NV table cells; scraper raises if name counts ≠ header counts. That's intentional.
- WI election cycle: Assembly all seats every 2 yrs; Senate odd districts in midterms, even in presidential years.
