# Badger Politics

Static tracker for the Wisconsin Legislature at
[badgerpolitics.org](https://badgerpolitics.org): bills, roll calls,
hearings, campaign finance, and lobbying registrations since 2009, rebuilt
nightly from official records.

> **Badger Politics is an independent project, not affiliated with the State of Wisconsin.**

## Architecture

```
openstates-scrapers (wi, pinned, CLI-only)  ┐
WEC ballot access + canvass PDFs/CSVs       ├─→ archived JSON/CSV (_data/) → SQLite → integrity gates → data products + Astro static build → Firebase Hosting
CFIS tRPC API (campaignfinance.wi.gov)      │
Eye on Lobbying (lobbying.wi.gov)           ┘
```

One nightly job ([pipeline/run.sh](pipeline/run.sh)). SQLite is the only
database and is rebuilt from the archived raw data on every run. The served
site is fully static: no servers, no functions, no runtime LLM calls.
Target infrastructure cost ~$2/month plus domains.

## Data sources

| Data | Source | Mechanism |
|---|---|---|
| Bills, actions, votes, hearings | docs.legis.wisconsin.gov | [openstates-scrapers](https://github.com/openstates/openstates-scrapers) pinned as a git submodule, invoked only as a CLI (`os-update`); fixes live in `pipeline/patches/` |
| Legislator roster, photos, committees | openstates people files + docs.legis membership listings + openstates legacy CSV (2009-2012) | fetched YAML/CSV, session-windowed rosters |
| Candidates and election results | Wisconsin Elections Commission | ballot access report PDF → CSV; certified canvass files |
| District boundaries | LTSB 2024 official files | bundled GeoJSON; Census geocoder is used for address→point only |
| Campaign finance | CFIS tRPC API (campaignfinance.wi.gov) | monthly windows since 2008-01, receipts only, filtered to mapped committees |
| Lobbying registrations | Eye on Lobbying (lobbying.wi.gov) | per-session matter grid + per-bill principal lists |
| Cross-check only | FollowTheMoney API (CC BY-NC-SA) | verification input, never imported or republished |
| Org logos | logo.dev (`LOGO_DEV_TOKEN`) | build-time fetch for hand-verified org domains only |

## Data mandates

These are hard rules. A change that violates one is wrong even if it works.

1. **SQLite is the only database.** No Cloud SQL, Firestore, or Postgres.
2. **Integrity gates block deploys and are never weakened to make a run
   pass.** Fix the scraper or importer, or let the run fail. When source
   data is genuinely defective, the gate is re-specified narrowly, the
   reasoning documented in-code, and the behavior surfaced — never
   silently loosened.
3. **Attribution never guesses.**
   - Votes and sponsorships resolve against per-session, per-chamber
     rosters. An ambiguous name is a build failure. Upstream duplicates
     and gaps are fixed only via the human-verified curation tables
     (`person_merges`, `person_aliases`, `person_terms`,
     `candidate_committees`), each entry with its basis.
   - Campaign committees auto-link only on unambiguous full-name matches;
     surname-only committee names ("Testin for Senate") always go through
     human curation. Committees whose office words don't match a
     legislative seat are excluded from auto-matching.
   - Donors aggregate by CFIS entity id, never by name.
   - Site-side name→profile links resolve only exact, unique names.
4. **Coverage gaps over inference.** A legislator without a verified
   committee link shows "isn't linked yet", never $0. A member whose
   linked committees have zero receipts in all recorded history is
   treated as unlinked (an all-time zero is a mapping gap, not a fact).
5. **Money framing ships with the data.** Corporations cannot contribute
   to Wisconsin candidates; PAC money is the PAC's, not a corporate
   payment; occupations are donor-reported; a contribution is not an
   endorsement of a vote. Donations are never displayed next to votes.
   Individual donors appear only in aggregate. Totals are windowed to
   each member's time in office (first recorded floor vote; electronic
   records floor 2008).
6. **Provenance filtering.** Rows with `source='legiscan'`, if ever
   present, never leave the SQLite via any export. FollowTheMoney data is
   cross-check input only and is never read by the importer or the site
   build. Org logos render only for entities in
   `site/src/data/org-domains.json`, each entry human-verified with a
   dated basis string, re-verified by the fetcher before download.
7. **GPL boundary.** openstates-scrapers is GPL-3.0 and is only invoked
   as a subprocess CLI. Its modules are never imported into this
   Apache-2.0 codebase. In-tree patches to the pinned submodule are
   applied at runtime from `pipeline/patches/` and documented for
   upstreaming.
8. **Privacy.** No accounts, no tracking cookies, no ads. Analytics is
   GoatCounter only. Personalization is localStorage-only. Addresses are
   sent to the Census geocoder solely for coordinates and are never
   stored; only the resulting district (and an optionally saved polling
   place string) persist, on the device.
9. **Static serving path.** No paid GCP resources beyond the ~$2/month
   ceiling; deploys never run from a PR; dependencies are hash-pinned
   (`uv.lock`, `package-lock.json`, `npm ci --ignore-scripts`).
10. **Every page links its official source**, and the footer carries the
    independence disclaimer.

## Verification gates

Pipeline (every nightly run, deploy aborts on failure):

- Roll call yes/no sums reconcile exactly with official counts; NV is
  all-or-none (docs.legis sometimes omits the NV name list).
- Bill counts per session cannot fall more than 2% versus the previous run.
- Referential integrity: votes→people, votes→events, events→bills,
  bills→sessions, actions/sponsorships→bills, contributions→people,
  every contribution traces to a live (committee, person) mapping, no
  committee maps to two people, no person appears twice on one roll call,
  hearing chairs resolve.
- CFIS: every fetched month reconciles exactly against the server's own
  transaction count (the newest month retries, and accepts a stable
  mismatch only when a plain-view diff proves every omitted row is
  outside our data). Month windows carry end-of-day timestamps because
  bare date bounds drop rows with timezone-artifact times.
- A rotating nightly audit re-fetches three archived months and refreshes
  any the state amended.

Cross-checks (manual):

- `python -m scraper.crosscheck_ftm --cycle YYYY` compares per-member
  cycle totals against FollowTheMoney's independent pipeline
  (cache-first; 1,000 record/year API quota).

Site (`site/scripts/`, run against a build):

| Script | Checks |
|---|---|
| `verify.mjs` | 10 functional checks in headless Edge (search quality, district lookup, roll-call pinning, disclaimers, analytics) |
| `a11y.mjs` | axe-core WCAG 2.2 AA over 22 representative pages at desktop and 360px viewports; 0 violations required |
| `responsive.mjs` | no horizontal overflow on 18 pages at 344/360/412/540/768/1280/1920px |
| `links.mjs` | every internal path and fragment anchor resolves; `--external` probes deduplicated outbound URLs with per-host pacing |

## Data products

Everything on the site is also data, keyless: static JSON API
(`/api/v1/...`), Atom feeds per bill/legislator/committee plus a weekly
digest, iCal calendars for hearings and election days, per-session CSVs,
and a provenance-filtered SQLite snapshot.

## Coverage

| Data | Coverage |
|---|---|
| Bills, actions, roll calls | 2011-12 through 2025-26 full; 2009-10 partial (official pages list vote totals, not names) |
| Campaign finance | electronic records 2008 to present; members with a verified committee link (see `docs/curation-worklist.md` for the human-verification queue) |
| Lobbying | current session |
| Election results | certified WEC canvasses per seat |

## Local development

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 20+, Docker
(scrapes only), Microsoft Edge (headless test harnesses).

### Pipeline

```sh
cd pipeline
uv run pytest tests            # 80 tests
uv run ruff check . --exclude vendor
uv run ./run.sh --local --skip-deploy   # full nightly chain
uv run python -m scraper.backfill       # historical sessions (idempotent)
uv run python -m importer.checks ../data/wi.sqlite
```

Scrapes run in the vendored container: `python -m scraper.scrape bills`
wraps `docker compose run --rm scrape` against
`pipeline/vendor/openstates-scrapers/docker-compose.yml` (in the deployed
image, `os-update` is on PATH instead). `os-update` wipes `_data` at run
start — never run two scrapes concurrently. `pipeline/Dockerfile` is the
Phase 6 Cloud Run Job image (stub until deploy).

Secrets/keys live in gitignored `pipeline/.env` (`FTM_API_KEY`) and
`site/.env` (`LOGO_DEV_TOKEN`); both are optional, features degrade
gracefully without them.

### Site

```sh
cd site
npm ci
npm run dev                    # local dev server against ../data/wi.sqlite
npm run build                  # current sessions only (fast dev builds)
BUILD_SESSIONS=all npm run build   # full history; required for valid profile links; deploy default
npx astro check                # TypeScript; 0 errors expected
node scripts/verify.mjs && node scripts/a11y.mjs && node scripts/responsive.mjs && node scripts/links.mjs
```

`CYCLE` (default 2026) selects the active election year in `run.sh`.

## Repo layout

| Path | Contents |
|---|---|
| `pipeline/` | scraper wrappers, importers, integrity checks, data products, nightly `run.sh` |
| `pipeline/importer/schema.sql` | the entire data model |
| `pipeline/importer/*.json` | human-verified curation tables |
| `pipeline/patches/` | documented fixes applied to the pinned scraper at runtime |
| `pipeline/_data/` | archived raw scrapes and API responses (the rebuild source) |
| `site/` | Astro 5 + Tailwind 4 + Pagefind static site; `src/lib/db.ts` is the only DB access |
| `site/scripts/` | build-time logo fetcher and the four test harnesses |
| `infra/` | OpenTofu for the GCP free-tier resources (Phase 6) |
| `docs/` | plan, backfill record, data research, money methodology, cross-check reports, curation worklist |

## Licensing

Code is [Apache-2.0](LICENSE). Legislative and campaign finance data is
Wisconsin public record. openstates-scrapers is GPL-3.0, subprocess-only
(see mandate 7). FollowTheMoney data is CC BY-NC-SA and is not
redistributed. Corrections are the highest-priority issues:
[open one here](https://github.com/uprightsleepy/badger-politics/issues).
