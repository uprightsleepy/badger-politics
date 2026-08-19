# Badger Politics — Implementation Plan
*A free one-stop shop for Wisconsin politics. v1 = the legislature module: bills, statuses, roll calls, legislators, and who's up for reelection. Later modules: campaign finance, statewide officials, ballot measures.*

**Domains (owned):** `badgerpolitics.org` (primary) · `badgerpolitics.com` (301 → .org)
*This document is written to be handed to Claude Code phase-by-phase.*

---

## 1. Goals & Non-Goals

**Goals**
- Wisconsinites can look up any bill (current + historical sessions), see its full status timeline, per-legislator roll call votes, and whether it died in committee without a hearing.
- Legislator pages: vote history, sponsorships, district, party, and **reelection status** (next election they face, declared challengers when available).
- "Graveyard" view: bills that failed to pass pursuant to SJR 1 without ever receiving a hearing — grouped by the committee (and chair) where they sat.
- Total infrastructure cost ≈ **$0–2/month + domains (~$25/yr)**. No paid API tiers, ever.
- Every page footer carries: **"Badger Politics is an independent project, not affiliated with the State of Wisconsin."** (Badger-prefixed names read state-official — BadgerCare, BadgerVoters — so this is non-negotiable.)
- URL structure anticipates the umbrella: `/bills/...`, `/legislators/...`, `/elections/...` are modules; future modules (`/money/`, `/officials/`) slot in without redesign.
- **Personalization without accounts:** a voter enters their address once ("Find My Legislators"); their Assembly + Senate district is remembered in localStorage and every page adapts (your reps' votes pinned on bill pages, your ballot on election pages). No logins, no server-side user data, address never stored.
- **Data is a product:** a static JSON API, bulk downloads, RSS/iCal feeds — journalists, researchers, and civic hackers integrate Badger Politics data with zero friction (provenance-filtered: openstates/manual rows only).

**Non-Goals (v1)**
- No user accounts, comments, or email alerts (Phase 6+ if ever).
- No live intra-day updates. Nightly freshness is the contract; say so on the site.
- No LLM features in the serving path (keeps cost + trust simple).

---

## 2. Architecture (decided)

```
                 ┌─────────────────────────────────────────────┐
 Cloud Scheduler │  Cloud Run Job (nightly, ~20 min)           │
 (5:15am CT) ───▶│  1. openstates-scrapers wi → JSON           │
                 │  2. importer: JSON → SQLite (+integrity)     │
                 │  3. astro build (reads SQLite at build time) │
                 │  4. firebase deploy + upload SQLite to GCS   │
                 └─────────────────────────────────────────────┘
                          │                      │
                          ▼                      ▼
                   GCS bucket             Firebase Hosting
                   (SQLite snapshots,     (static site, free SSL,
                    scraper JSON archive)  custom domain)
```

**Why this shape**
- **SQLite is the entire database.** No Cloud SQL (~$10+/mo minimum — the single biggest cost trap here). The dataset is small (a WI biennium ≈ ~2,000 bills, ~1,500 roll calls, 132 legislators; whole DB well under 100 MB), read-only at serve time, and rebuilt nightly.
- **Static site generation, not a server.** Every page is pre-rendered. Firebase Hosting free tier serves it with CDN + SSL. Scale-to-zero isn't needed because there's nothing to scale.
- **One container, one job, one schedule.** Scrape → import → build → deploy in a single Cloud Run Job execution. Fewer moving parts than job-chaining; a failure anywhere fails loudly in one place.
- **Search is client-side** via Pagefind (builds a static search index during `astro build`). Zero servers, zero cost, works offline.

**GCP resources**
| Resource | Purpose | Cost |
|---|---|---|
| Cloud Run Job | nightly pipeline | free tier (180k vCPU-sec/mo ≫ ~40k used) |
| Cloud Scheduler | trigger @ 5:15am America/Chicago | free (3 jobs free) |
| GCS (standard) | SQLite snapshots, JSON archive, tfstate | < $0.50/mo |
| Artifact Registry | pipeline image | ~$0–0.50/mo |
| Firebase Hosting | site @ badgerpolitics.org (+ .com 301 redirect) | free tier (10 GB storage / 360 MB-day transfer) |
| Cloud Monitoring | log-based alert on job failure → email | free tier |
| Secret Manager | LegiScan API key (backfill only) | ~$0.06/mo |

Everything in a dedicated GCP project (e.g. `wi-bills-prod`) so billing is isolated and visible.

---

## 3. Repo Layout (monorepo)

```
badger-politics/
├── CLAUDE.md                  # see §8
├── pipeline/
│   ├── Dockerfile             # python 3.11 + node 20 + firebase-tools
│   ├── run.sh                 # orchestrates scrape → import → build → deploy
│   ├── scraper/               # thin wrapper invoking openstates-scrapers (wi)
│   ├── importer/              # Python: openstates JSON → SQLite
│   │   ├── schema.sql
│   │   ├── import_openstates.py
│   │   ├── import_legiscan.py    # backfill only (local)
│   │   ├── import_wec.py         # candidates / election cycle
│   │   └── checks.py             # integrity gates (fail loud)
│   └── tests/
├── site/                      # Astro + Tailwind + Pagefind
│   ├── src/pages/...
│   └── src/lib/db.ts          # better-sqlite3 reads at build time
├── infra/                     # OpenTofu
│   ├── main.tf                # project services, bucket, AR, job, scheduler, SA, alert
│   └── versions.tf
├── data/                      # local dev SQLite lives here (gitignored)
└── .github/workflows/ci.yml   # lint + tests + tofu validate (free)
```

**Licensing note:** `openstates-scrapers` is GPL-3.0. Keep it as a pinned pip dependency (or git submodule) invoked by `pipeline/`, not copied into your source tree. Running GPL code server-side creates no obligations for your site code; if you ever publish the pipeline image, publish your patches too (you'd want to upstream WI fixes anyway).

---

## 4. Data Model (SQLite, `schema.sql`)

```sql
sessions(id PK, identifier, name, start_date, end_date, adjourned_sine_die,
         data_quality TEXT CHECK(data_quality IN ('full','partial')))  -- full = actions+roll calls; partial = actions only
people(id PK, name, party, current_role, chamber, district INT, image_url, openstates_id)
bills(id PK, session_id FK, identifier, title, chamber, classification,
      status,               -- derived: introduced|in_committee|passed_chamber|passed|enacted|vetoed|failed_sjr1
      latest_action_date, latest_action_desc,
      lrb_analysis TEXT,              -- LRB plain-language analysis, extracted from bill text page
      died_without_hearing BOOLEAN,   -- the graveyard flag
      committee_at_death TEXT, committee_chair_at_death TEXT,
      source TEXT CHECK(source IN ('openstates','legiscan','manual')))
sponsorships(bill_id FK, person_id FK, classification, is_primary)
actions(id PK, bill_id FK, date, chamber, description, classification)
vote_events(id PK, bill_id FK, date, chamber, motion, result,
            yes_count, no_count, nv_count, source_url, source TEXT)
vote_records(vote_event_id FK, person_id FK, option CHECK(option IN ('yes','no','not voting','excused')))
committees(id PK, chamber, name, chair_person_id FK)
hearings(id PK, committee_id FK, date, time, location, agenda_bill_ids_json, source_url)
elections(person_id FK, cycle_year INT, office, district, on_ballot BOOLEAN,
          is_incumbent BOOLEAN, opponents_json TEXT, source TEXT)
provenance(table_name, row_id, source, fetched_at)   -- optional; `source` cols may suffice
```

**Rules baked into the importer**
- `died_without_hearing`: true when a bill's action history contains a referral but no hearing/executive-session action before a "Failed to pass pursuant to Senate Joint Resolution 1" action. This powers the site's signature feature.
- **Integrity gates (`checks.py`) — abort the deploy, never publish bad data:**
  - Σ per-legislator vote_records per event == stored yes/no/nv counts (mirrors the scraper's own invariant).
  - Bill count for the active session must be ≥ last run's count − small tolerance (catches a silently broken scrape).
  - Every vote_record.person_id resolves to a person (name-matching failures fail the run, logged with the unmatched name).
- **Election-cycle rule (WI-specific, hardcoded with tests):** Assembly = every even year, all 99 districts. Senate = odd-numbered districts in midterm years (2026, 2030…), even-numbered in presidential years (2028, 2032…). `import_wec.py` overlays WEC's certified candidate list (CSV download) for the active cycle to fill `on_ballot` and `opponents_json`.
- **LegiScan rows are display-only.** `source='legiscan'` rows must never be included in any future bulk-export/download feature (ToS boundary). Openstates/manual rows are public-domain-clean.

---

## 5. Pipeline Details

**`run.sh` (the whole nightly job):**
```bash
set -euo pipefail
os-update wi bills --scrape --fastmode        # openstates scraper → _data/wi/*.json
os-update wi events --scrape                  # committee hearing schedules (scrapers/wi/events.py)
python -m importer.import_openstates _data/wi data/wi.sqlite
python -m importer.checks data/wi.sqlite      # hard gate
python -m dataproducts.build data/wi.sqlite site/public/   # static JSON API, feeds, iCal, bulk files
(cd site && npm run build)                    # astro reads data/wi.sqlite
npx pagefind --site site/dist
firebase deploy --only hosting --project "$FB_PROJECT" --non-interactive
gsutil cp data/wi.sqlite "gs://$BUCKET/snapshots/wi-$(date +%F).sqlite"
```
- Use **scrape phase only** from openstates-scrapers (JSON output). Do **not** stand up their full Django/Postgres import stack — your importer replaces it and is ~10× simpler.
- Politeness: openstates-scrapers already rate-limits and retries against docs.legis. Don't lower its delays. Nightly at 5:15am CT lands after journal postings and off business hours.
- **Backfill strategy: walk backward until it breaks.** Session identifiers are the odd year of each two-year biennium (2025 = 2025-26, currently active and owned by the nightly job until the next Legislature convenes in Jan 2027; roll it into the historical set then). Backfill covers completed biennia only, newest → oldest, so it starts at 2023 (= 2023-24). Historical sessions are immutable — scrape each once, locally (`os-update wi bills --scrape --session=2023R`). For each session run the integrity checks; when a session imports actions but roll calls fail structurally (older sessions keep votes in journal PDFs, not structured vote pages), mark it `data_quality='partial'` and continue; when a session fails entirely, that's the floor — stop and document it. Expected outcome: `full` back to ~2011, `partial` best-effort into the late '90s, nothing earlier. Keep `import_legiscan.py` as fallback for any stubborn session (`getDatasetList`/`getDataset`, one call per session, trivially inside the 30k/mo free quota).

**Failure handling:** Cloud Monitoring log-based alert on `severity>=ERROR` from the job OR job-execution-failed → email. The site simply keeps serving yesterday's build — stale-but-correct by design. Add a small "data through {date}" badge in the site footer sourced from a `meta` table.

---

## 6. Site (Astro) — Page Inventory

| Route | Content |
|---|---|
| `/` | search box, recently-acted bills, session stats |
| `/bills/{session}/{id}` | **LRB plain-language analysis as the lead** (not legalese), visual how-a-bill-becomes-law progress stepper, sponsors, action timeline, roll calls inline, "Your reps voted…" pinned when district is set, Hearing None banner if applicable |
| `/votes/{id}` | full roll call: sortable table of every legislator + vote, party breakdown chart |
| `/legislators/{slug}` | photo, district, party, sponsorships, full vote history, **"Up for reelection: Nov 2026 — on ballot ✓, challengers: …"** |
| `/hearing-none/{session}` | **"Hearing None"** — bills that died without a hearing, grouped by committee + chair, with counts ("Committee X, Chair Y: 47 bills, 0 hearings") |
| `/committees/{id}` | members, bills referred, hearing rate |
| `/elections/2026` | every seat on the ballot, incumbent, filed candidates |
| `/my-reps` | **Find My Legislators**: address → Census geocoder (free, keyless) **for coordinates only** → client-side point-in-polygon against bundled LTSB district GeoJSON (**the authoritative boundary source** — Census SLD layers can lag WI's 2024 remedial maps). Browser-geolocation option = zero third parties. District saved to localStorage; a "Your reps" chip then appears site-wide |
| `/hearings` | upcoming committee hearings (from events scrape) with **"Add to calendar" .ics** per hearing + election-day .ics — showing up to testify is the highest-leverage thing a voter can do |
| `/api/v1/...` | **static JSON API**: pre-generated at build (`/api/v1/bills/2025/ab656.json`, `/api/v1/legislators/{id}.json`, `/api/v1/votes/{id}.json`, session indexes). Free CDN-served integration surface |
| `/data` | bulk downloads: per-session CSV + the SQLite snapshot itself (provenance-filtered to openstates/manual rows), methodology, freshness, corrections contact |
| RSS/Atom | per-bill, per-legislator, per-committee feeds + "this week in the legislature" digest feed — free alerts via any feed reader, IFTTT, or Slack, with zero email infrastructure |
| `/about` | mission, independence disclaimer, how it's built (link to public repo) |

Design: server-rendered-at-build HTML, Tailwind, no client JS except Pagefind + a tiny sort/filter helper. Fast on rural connections; that's the audience. Mobile-first.

---

## 7. Phases for Claude Code (each = one working session, with acceptance criteria)

> **Local-first guarantee: Phases 0–5 require no GCP, no credentials, and no secrets** — everything runs on a laptop (uv + Node + sqlite3) against public, keyless sources. The optional LegiScan fallback key is the only possible secret and can wait. **Phase 6 is the first moment deploy credentials exist anywhere**, which is exactly when hands-on infrastructure vetting happens. Remote Claude Code sessions through Phase 5 never touch anything sensitive.

**Phase 0 — Scaffold**
Public GitHub repo (`badger-politics`), Apache-2.0 LICENSE, repo layout above, CLAUDE.md, `.gitignore`, `schema.sql`, CI stub, devcontainer or `mise`/`uv` setup.
✅ Repo public with LICENSE + README; `sqlite3 data/wi.sqlite < schema.sql` succeeds; CI green.

**Phase 1 — Scrape + Import (local, current session)**
Wrapper invokes openstates-scrapers (bills + events) for the 2025 biennium; importer populates SQLite incl. LRB analysis extraction and hearings; checks pass.
✅ `SELECT COUNT(*) FROM bills` ≈ known session total; AB 656 present with `died_without_hearing=1`, committee "Children and Families", non-empty `lrb_analysis`; a sampled Assembly roll call matches docs.legis exactly; hearings table populated.

**Phase 2 — Derived Features + Elections + Districts**
Status derivation, Hearing None logic, committees, election-cycle rules + WEC candidate import; download LTSB district shapefiles and produce a simplified (<300 KB) GeoJSON artifact for client-side lookup.
✅ Unit tests for cycle rules (2024/2026/2028 cases); Hearing None query returns plausible counts; spot-check 3 legislators' 2026 ballot status against WEC; a West Allis lat/lng resolves to the correct AD/SD via the GeoJSON.

**Phase 3 — Data Products (the backend API layer)**
`dataproducts.build`: static JSON API tree, per-session bulk CSVs + filtered SQLite download, RSS/Atom feeds (bill/legislator/committee/weekly digest), iCal for hearings + election days. All provenance-filtered.
✅ `curl` of a locally served `/api/v1/bills/2025/ab656.json` returns full bill+votes; feeds pass W3C validator; a hearing .ics imports cleanly into Google Calendar; no `source='legiscan'` rows appear in any export.

**Phase 4 — Historical Backfill (local)**
Walk-backward import (2023 → older, per §5) until structural failure; per-session `data_quality` tagging; identity resolution stress-tested against decades of rosters (duplicate surnames, district changes, party switches); prebuilt historical page artifact generated for later merge.
✅ Every importable session in SQLite with correct `full`/`partial` tag; documented floor session; zero ambiguous-name best-guesses across all sessions (hard-fail proof); data products regenerate cleanly with history included.

**Phase 5 — Site MVP (local)**
Astro pages for bills/votes/legislators/hearing-none/hearings + Pagefind; Find My Legislators (Census geocoder with GeoJSON fallback) + localStorage district; "Your reps voted" pinning; bill progress stepper; GoatCounter (no-cookie) in base layout. Build reads SQLite directly.
✅ `npm run build` < 5 min for full biennium; Lighthouse ≥ 95 on a bill page; search finds "child marriage" → AB 656; a West Allis street address surfaces the correct two legislators and, after saving, AB 656's page pins their votes; GoatCounter registers a pageview from local preview.

**Phase 6 — Infrastructure + Launch (the vetted session)**
Dockerfile, Cloud Run Job, Scheduler, GCS, Firebase Hosting, least-privilege SAs, log alert, `tofu apply`.
✅ Manually triggered job execution deploys end-to-end at https://badgerpolitics.org; badgerpolitics.com 301s to .org; forced failure (bad selector) triggers email alert and does NOT deploy.

Also in Phase 6: Firebase preview-channel staging + smoke test, deploy decoupling via GitHub Actions (WIF), dead-man's switch, second scheduler job for events, rollback rehearsal, Cloudflare front, DNS cutover, per-session quality badges live, sitemap/OG/about pages final.
Additional ✅: badgerpolitics.com 301s; every historical session browsable with correct badge; snapshot publishing to GitHub Releases works; forced failure alerts AND missed-run alerts both fire in tests; rollback executed once successfully; total monthly cost in README verified against billing.

---

## 8. CLAUDE.md (draft — place at repo root)

```markdown
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
```

---

## 9. Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| docs.legis markup change breaks scraper | ~1–2×/session (per issue-tracker history) | loud alert, site serves stale-but-correct, patch (~450-line scraper) & upstream |
| Name-matching drift (legislator turnover) | after each election | importer fails on unmatched names; update people table from openstates/people YAML |
| Firebase free-tier transfer exceeded | only if the site gets popular | Cloudflare free CDN in front, or GCS+LB; revisit at >50k views/mo |
| LegiScan ToS ambiguity | low (display-only use) | provenance column + no-export rule; prefer full self-scrape backfill so LegiScan rows → zero |
| WEC changes candidate-list format | each cycle | import is a small CSV mapper; update per cycle |
| Census geocoder CORS/availability | low | it's geocoding-only; PIP against bundled LTSB GeoJSON is authoritative and offline-capable |
| Vote misattribution (same-surname legislators) | medium, catastrophic for trust | session-scoped roster matching; ambiguity = hard build failure; regression test on known duplicate surnames |
| Supply-chain compromise of nightly job → defacement | low, high impact (pre-election target) | hash-pinned lockfiles, `--ignore-scripts`, least-priv SAs, branch protection, no PR deploys, rehearsed Firebase rollback |
| Free-tier transfer exhaustion via bulk downloads takes site offline | medium | SQLite/CSV snapshots on GitHub Releases (free bandwidth); Cloudflare free tier in front of the site |
| Job silently never runs (vs. failing) | medium | dead-man's switch: success ping to healthchecks.io; missed ping alerts |
| Stale election data during cycle (dropped candidates, results window) | medium | automated WEC fetch, weekly in-cycle; election-night banner posture linking official WEC results |
| State objects to scraping (robots.txt) | low | identifying User-Agent w/ contact email, cached/delta fetching, published methodology; fallback = LegiScan display-only + WI notification service |

---

## 10. Decisions — ALL RESOLVED ✅

1. **Name + domains:** Badger Politics — badgerpolitics.org (primary), badgerpolitics.com (301 redirect). Both owned.
2. **Backfill depth:** as far back as the data allows — walk backward from 2023 until structural failure, `full`/`partial` quality tiers per session (see §5).
3. **Analytics:** GoatCounter (no-cookie, no consent banner). GA is banned in CLAUDE.md.
4. **Repo:** public from day one, Apache-2.0. (Owner note: Google personal-project/CIIAA clearance is Henry's to confirm before first push.)

**Green light: hand Phase 0 to Claude Code.**

---

## 11. Red-Team Hardening (fold into phases as noted)

**Correctness**
- Identity resolution (Phase 1): importer builds a per-session legislator roster; vote-page names resolve against it; ambiguous surnames (multiple Johnsons) hard-fail the build. Regression test with a known duplicate-surname session.
- Districts (Phase 2/5): LTSB GeoJSON is authoritative for AD/SD; Census used solely for address→coordinates; offer browser geolocation as a no-third-party path.
- Hearings (Phase 6 infra): second Cloud Scheduler job runs the events scrape ~3×/day (still inside the 3-free-jobs limit); every .ics embeds "confirm against the official hearing notice" + source link.
- Trust surface (Phase 5): "view official source" link on every vote event and action (source_url already in schema); published corrections policy on /about with a contact.

**Availability & operations**
- Decouple deploys (Phase 6): nightly job = data + full build; site-only code changes deploy via GitHub Actions (Workload Identity Federation, keyless, main branch only). Scraper breakage never blocks a site fix.
- Staging (Phase 6): deploy to a Firebase preview channel, smoke-test key pages (`curl` bill page, meta.json freshness), then promote to live.
- Dead-man's switch (Phase 6): job pings healthchecks.io on success; a missed ping alerts even when nothing "errored."
- Build scaling (Phase 4 generates the prebuilt historical artifact; Phase 6 wires the nightly merge): nightly build renders only the current biennium and merges the prebuilt history before deploy — keeps job time/memory flat.
- Bulk distribution (Phase 3): SQLite + CSV snapshots publish to GitHub Releases (free bandwidth); site origin never serves large files. Cloudflare free tier in front of badgerpolitics.org for cache/absorption.

**Security**
- Supply chain: hash-pinned lockfiles, `npm ci --ignore-scripts`, pip with `--require-hashes`; Artifact Registry vulnerability scanning on the pipeline image.
- Least privilege: the job's SA can deploy Hosting + write the snapshot bucket, nothing else; the Actions SA can deploy Hosting only; no long-lived JSON keys anywhere.
- Repo: branch protection on main, required review, no secrets in repo, no deploy from PRs.
- Rollback: documented one-command Firebase Hosting rollback in the runbook; rehearse once in Phase 5.
- Scrape posture: identifying User-Agent with contact email, scrapelib caching, off-hours schedule; if the Legislature ever objects, the continuity plan is LegiScan (display-only) + the state's own email notification service while negotiating.

**Product**
- Election-night posture (Phase 5): dated banner during election windows linking official WEC results + "when results are certified" explainer. We never look abandoned on the biggest traffic night; we also never pretend to do live results.
- WEC ingestion (Phase 2): automated fetch with schema-drift alarm; weekly cadence in-cycle, monthly off-cycle.

---

## 12. Feature Backlog (post-launch, in rough value order)

1. Build-time OG images per bill/legislator (satori/resvg) — shares look professional, drives adoption.
2. Embeddable widgets (iframe bill-status card, roll-call table) for local newsrooms and bloggers.
3. "This week in the legislature" digest as a static page (feed already exists in Phase 3).
4. Attendance / missed-vote counts per legislator — pure data, presented without grades to stay nonpartisan.
5. Email alerts (Buttondown free tier or similar) driven by the existing feeds.
6. Spanish translations of UI chrome + LRB analyses.
7. Campaign finance module (`/money/`) from Wisconsin CFIS exports — the ledger grows up.
8. In-browser SQL playground: sql.js-httpvfs (SQLite-in-WASM over HTTP range requests against the hosted snapshot) — arbitrary queries for power users, zero servers. Strictly more expressive than GraphQL at $0.
9. GraphQL endpoint — **only if** real integration partners request it. Implementation: Cloud Run scale-to-zero over the same SQLite, persisted queries + depth/complexity limits mandatory. Note: Open States sunset their own public GraphQL API (Dec 2023) for maintenance cost; treat that as the cautionary default.
