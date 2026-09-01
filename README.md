# Badger Politics

Free, independent tracking of the Wisconsin Legislature at
[badgerpolitics.org](https://badgerpolitics.org): every bill, roll call,
hearing, veto, campaign dollar and lobbying registration since 2009, plus
how Wisconsin's members of Congress vote, rebuilt from official records
and served as a fully static site.

> **Badger Politics is an independent project, not affiliated with the State of Wisconsin.**

## What is on the site

| Section | What it holds |
|---|---|
| Bills | Every proposal in every session since 2009, with status, sponsors, the LRB plain-language analysis, fiscal estimates, lobbying interests, companion bills (from the Legislature's own See Also links), and the full official history with legislator names linked |
| Roll calls | Every recorded floor vote, name by name, with party splits and the reader's own legislators pinned |
| Legislators | Profiles with bills led, key votes selected by rule, votes against party, floor attendance by day, committees, campaign money while in office, compensation, and the complete paged record |
| Districts and Find My Legislators | Address to district entirely in the browser (Census geocoder for coordinates, bundled LTSB boundaries for the match); nothing is stored anywhere but the device |
| Committees | Members, hearings, and the bills that died in each committee without a hearing |
| Hearing None | The graveyard: bills that were referred, never heard, and failed at session's end |
| Calendar | Hearings and election days, with iCal feeds and WisconsinEye recordings where they exist |
| New Laws, Governor's Desk, Veto Tracker, Partial Veto | Acts by biennium with passage tallies; bills awaiting signature; every veto, partial veto and override attempt; how the partial veto works |
| Campaign Money | Receipts to sitting legislators windowed to their time in office, contributing committees, and outside spending filing by filing with the Ethics Commission's transaction IDs and report links |
| Lobbying | Registrations by organization and by bill (an interest, never a for-or-against position) |
| Federal Delegation | Both U.S. senators and all eight House members, with every floor roll call from the Senate's and House Clerk's own XML (Senate from the 112th Congress, House from 2005) |
| City Councils | Milwaukee and West Allis Common Council votes, member by member, with every vote that drew a No surfaced and every item linking the clerk's own record; each member page carries the portrait, office contacts, committee assignments, service dates and term end, attendance from the clerk's roll calls, sole No votes, votes on the losing side, motions moved, a paged full record, a follow button, an Atom feed and JSON, like a legislator's; district pages draw each district within its city; the address lookup adds the reader's alderpersons |
| 2026 Ballot | Statewide offices and every legislative seat, with a personal "what is on my ballot" view from the saved district |
| Following | Device-only follows for bills, legislators, committees, districts and races, with what changed since the last visit |
| Data and API | Static JSON API, Atom feeds, iCal calendars, bulk CSV and a provenance-filtered SQLite snapshot, all keyless |

Every page links its official source and carries the independence
disclaimer.

## Architecture

```
openstates-scrapers (wi, pinned, CLI-only)    ┐
docs.legis member pages, subject index, LRB   │
WEC ballot access + certified canvasses       ├─→ archived raw data (_data/) → SQLite → integrity gates → data products + Astro static build → Firebase Hosting
CFIS tRPC API (campaignfinance.wi.gov)        │
Eye on Lobbying, WisconsinEye                 │
Senate LIS + House Clerk roll-call XML        ┘
```

SQLite is the only database and is rebuilt from the archived raw data on
every run ([pipeline/run.sh](pipeline/run.sh)). The served site is fully
static: no servers, no functions, no runtime LLM calls. Target
infrastructure cost is about $2 a month plus domains.

Releases run in GitHub Actions, never from a laptop: a push to `main`
rehearses on dev, and production is a deliberate promotion
(`workflow_dispatch`). CI builds from the newest database snapshot in a
private bucket and runs every gate before publishing. See
[docs/deploys.md](docs/deploys.md). The scheduled Cloud Run job is not yet
enabled; today the pipeline is run from a workstation and uploads the
snapshot CI releases from.

## Data sources

| Data | Source | Mechanism |
|---|---|---|
| Bills, actions, votes, hearings | docs.legis.wisconsin.gov | [openstates-scrapers](https://github.com/openstates/openstates-scrapers) pinned as a git submodule, invoked only as a CLI (`os-update`); fixes live in `pipeline/patches/` |
| LRB analyses, companion bills, fiscal documents | docs.legis bill and proposal pages | fetched once per URL into an on-disk cache; companions come only from the page's own See Also links |
| Legislator roster, photos, committees, service terms | openstates people files, docs.legis membership listings, openstates legacy CSV (2009-2012) | session-windowed rosters; human-verified curation tables for merges, aliases, terms and departures |
| Capitol office contacts | docs.legis member pages | refreshed each run; sitting members only |
| Subject index | docs.legis subject index | matched by exact session and identifier |
| Hearing recordings | WisconsinEye | metadata matched by exact date and committee title; links out, never hosted |
| Candidates and election results | Wisconsin Elections Commission | ballot access report PDF to CSV; certified ward-by-ward canvasses |
| District boundaries | LTSB 2024 official files | bundled GeoJSON; the Census geocoder is used for address-to-point only |
| Campaign finance | CFIS tRPC API (campaignfinance.wi.gov) | legislator receipts in monthly windows since 2008-01 through a verified committee map; every other filer's money since 2025-01, including independent expenditures with their report IDs |
| Lobbying registrations | Eye on Lobbying (lobbying.wi.gov) | per-session matter grid plus per-bill principal lists |
| Federal roll calls | senate.gov LIS XML, clerk.house.gov EVS XML, unitedstates/congress-legislators roster | per-vote files mirrored once and cached forever; positions keyed by each chamber's own member id |
| Council votes and attendance | Legistar Web API (`milwaukee`, `westalliswi` tenants: EventItems, Votes, RollCalls); each meeting's InSite page for item links | meetings cached permanently once minutes are Final; votes keyed by each tenant's own person id; an item links to the page the meeting's own page lists for its file number, because InSite's ids are not the API's |
| Aldermanic district boundaries | Milwaukee open data portal (CC BY shapefile); West Allis city GIS server | one-time generator (`importer/local_shapes.py`), committed GeoJSON; the robots-disallowed city map host is not used |
| West Allis seat roster | the city's own district pages | ten-row curated table (`importer/local_seats.json`), each entry with its basis URL |
| Council member names, portraits, contacts, committees | the tenant's Persons record for the full name where the office record abbreviates it (Milwaukee lists "ALD. BAUMAN"); the cities' own district pages (city.milwaukee.gov, westalliswi.gov, both `Allow: /`); Legistar Persons, OfficeRecords and each tenant's public Departments listing | a portrait attaches only when the city's page labels it with the member's district (Milwaukee) or name (West Allis); an email or phone only when exactly one is on record; committee links by exact body name against the tenant's own listing, plain text otherwise |
| Cross-check only | FollowTheMoney API (CC BY-NC-SA) | verification input, never imported or republished |
| Org logos | logo.dev (`LOGO_DEV_TOKEN`) | build-time fetch for hand-verified org domains only |

## Data mandates

These are hard rules. A change that violates one is wrong even if it works.

1. **SQLite is the only database.** No Cloud SQL, Firestore, or Postgres.
2. **Integrity gates block deploys and are never weakened to make a run
   pass.** Fix the scraper or importer, or let the run fail. When source
   data is genuinely defective, the gate is re-specified narrowly, the
   reasoning documented in code, and the behavior surfaced, never
   silently loosened.
3. **Attribution never guesses.**
   - Votes and sponsorships resolve against per-session, per-chamber
     rosters. An ambiguous name is a build failure. Upstream duplicates
     and gaps are fixed only via the human-verified curation tables
     (`person_merges`, `person_aliases`, `person_terms`, `term_events`,
     `vote_corrections`, `candidate_committees`), each entry with its
     basis.
   - Campaign committees auto-link only on unambiguous full-name matches;
     surname-only committee names ("Testin for Senate") always go through
     human curation. Committees whose office words do not match a
     legislative seat are excluded from auto-matching.
   - Donors aggregate by CFIS entity id, never by name.
   - Federal positions are attributed by the Senate's LIS id or the
     House's bioguide id on each vote record; there is no name matching.
   - Site-side name-to-profile links resolve only exact, unique names.
4. **Coverage gaps over inference.** A legislator without a verified
   committee link shows "isn't linked yet", never $0. A member whose
   linked committees have zero receipts in all recorded history is
   treated as unlinked (an all-time zero is a mapping gap, not a fact).
5. **Money framing ships with the data.** Corporations cannot contribute
   to Wisconsin candidates; PAC money is the PAC's, not a corporate
   payment; occupations are donor-reported; a contribution is not an
   endorsement of a vote. Donations are never displayed next to votes.
   Individual donors appear only in aggregate. Totals are windowed to
   each member's time in office. Outside spending is shown one filing at
   a time, as filed, with the Commission's transaction ID and the report
   it appeared on; nothing is summed by stance.
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
   stored; only the resulting district, follows, and an optionally saved
   polling place persist, on the device.
9. **Static serving path.** No paid GCP resources beyond the ~$2/month
   ceiling; deploys never run from a pull request; dependencies are
   lock-pinned (`uv.lock`, `package-lock.json`, `npm ci --ignore-scripts`).
10. **Every page links its official source**, and the footer carries the
    independence disclaimer.

## Verification gates

Pipeline (`importer/checks.py`, every run; a failure aborts before any
snapshot is written):

- Roll-call yes/no sums reconcile exactly with the official counts; NV is
  all-or-none (docs.legis sometimes omits the NV name list).
- Bill counts per session cannot fall more than 2% against the previous
  run.
- Referential integrity across every table: votes to people and events,
  events to bills, bills to sessions, actions and sponsorships to bills,
  contributions to people and to a live committee mapping, no committee
  mapped to two people, no person twice on one roll call, no vote outside
  a recorded service term, every sitting member with a live term and
  office contacts, hearing chairs and videos resolving, committee money
  tracing to a known filer, advocacy rows naming both candidate and race.
- Federal: recounted Senate tallies equal the stated yeas and nays, every
  Senate vote carries exactly two Wisconsin senators, House rows are
  Wisconsin-only, and the delegation holds ten members.
- Council votes: every vote traces to the tenant's own member id and
  vocabulary, every meeting and item links its public page, every sitting
  member has a seat, every committee assignment names a known member, and
  a tenant with no dissenting vote on record fails (a fetch that stopped
  at consent items).
- CFIS: every fetched month reconciles exactly against the server's own
  transaction count (the newest month retries, and accepts a stable
  mismatch only when a plain-view diff proves every omitted row is
  outside our data). Month windows end at 23:59:59 because bare date
  bounds drop rows with timezone-artifact times. A rotating audit
  re-fetches three archived months each run and refreshes any the state
  amended.

Site (`site/scripts/`, run against a build; CI runs all of them before a
release):

| Script | Checks |
|---|---|
| `preflight.mjs` | the built tree matches the database it came from: every session, one page per bill, legislator and roll call, a search index at least as large as the bill count, data products present, disclaimer shipped |
| `verify.mjs` | 11 functional checks in headless Chrome: search quality and junk-match rejection, address lookup to the right two legislators, roll-call pinning, rep highlighting, Hearing None banner, LRB analysis, disclaimer, analytics |
| `a11y.mjs` | axe-core WCAG 2.2 AA over 41 representative pages at desktop and 360px; 0 violations required |
| `responsive.mjs` | no horizontal overflow on the same 41 pages at 344/360/412/540/768/1280/1920px |
| `links.mjs` | every internal path and fragment anchor resolves; `--external` probes deduplicated outbound URLs with per-host pacing |
| `csp.mjs` | run against the released site: the Content-Security-Policy breaks neither search (WebAssembly) nor the address lookup (Census JSONP) |
| `measure.mjs` | diagnostic, not a gate: names the element that overflows one page at one width, with `--wide-font` to reproduce a Linux-only failure on Windows |

The two browser gates share one page list (`scripts/lib/serve.mjs`), so a
page added to one is scanned by both.

## Data products

Everything on the site is also data, keyless: a static JSON API under
`/api/v1/` (about 41,000 files), Atom feeds per bill, legislator and
committee plus a weekly digest (about 20,600), iCal calendars for every
hearing and for election days (845), per-session CSVs, and a
provenance-filtered SQLite snapshot. See [/data/](https://badgerpolitics.org/data/).

## Coverage

| Data | Coverage |
|---|---|
| Bills, actions, roll calls | 2011-12 through 2025-26 full; 2009-10 partial (official pages list vote totals, not names) |
| Legislator campaign finance | electronic records 2008 to present, for members with a verified committee link (`docs/curation-worklist.md` holds the human-verification queue) |
| Committee, PAC and outside spending | every filer's transactions since January 2025 |
| Lobbying | current session (2025 Regular) |
| Election results | certified WEC canvasses per seat and statewide office |
| Federal roll calls | U.S. Senate from the 112th Congress (2011); U.S. House from 2005 |
| Council votes | Milwaukee from 2008; West Allis from 2015 (earlier minutes record votes inconsistently) |

## Local development

Prerequisites: [uv](https://docs.astral.sh/uv/), Node 22, Docker (scrapes
only), Google Chrome (headless test harnesses; Edge is the fallback, or
set `BROWSER_PATH`).

### Pipeline

```sh
cd pipeline
uv run pytest                            # 114 tests
uv run ruff check .
uv run ./run.sh --local --skip-deploy    # full chain: scrape, import, enrich, check, build
uv run python -m importer.checks ../data/wi.sqlite
uv run python -m scraper.backfill        # historical sessions (idempotent)
```

Scrapes run in the vendored container: `python -m scraper.scrape bills`
wraps `docker compose run --rm scrape` against
`pipeline/vendor/openstates-scrapers/docker-compose.yml`. `os-update`
wipes its output at run start, so never run two scrapes concurrently, and
never build the site while the importer is rebuilding the database.

Secrets live in gitignored `pipeline/.env` (`FTM_API_KEY`) and `site/.env`
(`LOGO_DEV_TOKEN`); both are optional and the features degrade gracefully
without them.

### Site

```sh
cd site
npm ci
npm run dev                          # against ../data/wi.sqlite
npm run build                        # current biennium only, for fast iteration
BUILD_SESSIONS=all npm run build      # full history; what CI releases
npx astro check                      # TypeScript; 0 errors expected
node scripts/preflight.mjs
node scripts/responsive.mjs && node scripts/a11y.mjs && node scripts/verify.mjs && node scripts/links.mjs
```

`CYCLE` (default 2026) selects the active election year in `run.sh`.

## Repo layout

| Path | Contents |
|---|---|
| `pipeline/scraper/` | fetchers for every source; `http.py` is the one HTTP session (identifying User-Agent, retries, page cache), `cfis_api.py` the one CFIS client |
| `pipeline/importer/` | importers, enrichment, `checks.py` (the gates), `schema.sql` (the entire data model), and the human-verified curation JSON |
| `pipeline/dataproducts/` | JSON API, Atom feeds, iCal, bulk exports |
| `pipeline/patches/` | documented fixes applied to the pinned scraper at runtime |
| `pipeline/_data/` | archived raw scrapes and API responses (the rebuild source; gitignored) |
| `site/` | Astro 7 + Tailwind 4 + Pagefind; `src/lib/db.ts` is the only database access, `src/lib/wire.ts` the contract between build-time JSON and browser scripts |
| `site/scripts/` | the build-time logo fetcher, preflight, and the browser harnesses |
| `.github/workflows/` | `ci.yml` (lint, tests, typecheck, workflow guards, tofu validate) and `deploy.yml` (gated release from a snapshot) |
| `infra/` | OpenTofu for the CI deploy identity: the enabled APIs, the Workload Identity pool and provider GitHub federates into, the deployer service account, and its hosting and snapshot-bucket IAM bindings |
| `docs/` | plan, deploy runbook, backfill record, money methodology, cross-check reports, curation worklist, and `research/` notes behind each module |

## Contributing

Corrections are the highest-priority issues:
[open one here](https://github.com/uprightsleepy/badger-politics/issues).
Pull requests to `main` need the code owner's approval and a green CI run
(lint, tests, schema, typecheck, workflow guards, tofu validate); only the
owner pushes directly. Please keep the data mandates above in mind: a
change that makes a number look better by guessing is not a fix.

## Licensing

Code is [Apache-2.0](LICENSE). Legislative, election, campaign finance and
lobbying data is Wisconsin public record; federal roll calls are U.S.
government works. openstates-scrapers is GPL-3.0, subprocess-only (see
mandate 7). FollowTheMoney data is CC BY-NC-SA and is not redistributed.
