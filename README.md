# Badger Politics

A free, independent one-stop shop for Wisconsin politics at
[badgerpolitics.org](https://badgerpolitics.org).

> **Badger Politics is an independent project, not affiliated with the State of Wisconsin.**

## What it does

Sixteen years of the Wisconsin Legislature, in plain language, rebuilt
nightly from official records:

- **Every bill since 2009**: full status timeline, a how-a-bill-becomes-law
  progress view, sponsors with party, and the Legislative Reference Bureau's
  plain-language analysis up top instead of legalese.
- **Every roll call**: person-by-person votes with party and district, on the
  bill page and on a dedicated page per vote, each linked to its official
  source.
- **"Hearing None"**: the signature view. Thousands of bills die each session
  without ever getting a public hearing. They are grouped by the committee
  where they sat and its chair.
- **Legislator pages**: photo, party, district, a running tally of their
  sponsored bills by stage (became law, died at session end, and so on), a
  GitHub-style floor attendance heatmap per year, votes-with-party-majority
  percentages, official election results for their seat, compensation, and
  reelection status for 2026 with declared challengers.
- **Find my legislators**: enter an address once (or use browser location).
  The district is computed in the browser against the Legislature's official
  2024 boundaries and saved on the device only. Addresses are never stored.
  Every roll call then highlights how your two legislators voted. You can
  also save your polling place after looking it up on MyVote.
- **Hearings and a civic calendar**: upcoming committee hearings with
  add-to-calendar files, agenda bills linked, plus an interactive month
  calendar of hearings and election days.
- **2026 ballot**: every seat up in November, retirements, and qualified
  candidates from the Wisconsin Elections Commission.
- **Search**: instant client-side search across bills (Pagefind).

## Data products

Everything on the site is also data. No key, no signup:

- Static JSON API: `/api/v1/bills/{session}/{bill}.json`, roll calls,
  legislator profiles, session indexes, `meta.json` freshness.
- Atom feeds per bill, legislator, and committee, plus a weekly digest.
- iCal calendars for hearings and election days.
- Per-session CSVs and a filtered SQLite snapshot (published via GitHub
  Releases). LegiScan-sourced rows, if ever present, are display-only and
  excluded from every export.

## Data coverage

| Sessions | Quality |
|---|---|
| 2011-12 through 2025-26 (plus specials) | full: actions and individual roll calls |
| 2009-10 | partial: actions and vote totals; the era's pages list no individual names |

Sources: the Legislature's own site (via the open-source openstates-scrapers,
invoked as a CLI), the openstates people files, docs.legis membership
listings, the openstates legacy archive, WEC ballot access reports and
official canvass results, and LTSB district boundaries. See
[docs/backfill.md](docs/backfill.md) for the era-by-era details and
[docs/data-research.md](docs/data-research.md) for the wider free-data map.

## How it stays trustworthy

- **Vote attribution never guesses.** Names resolve against a per-session,
  per-chamber roster. Anything ambiguous fails the build. Duplicate or
  incomplete upstream records are fixed only through human-verified curation
  tables with the basis documented.
- **Integrity gates block deploys.** Roll call sums must reconcile with the
  official counts, bill counts cannot silently shrink, and referential
  integrity is checked on every run.
- **Independence and privacy.** No accounts, no tracking cookies, no ads.
  Analytics is GoatCounter (cookie-free). Personalization lives in
  localStorage only.

## Architecture

```
openstates-scrapers (wi) → SQLite → integrity checks → Astro static build → Firebase Hosting
```

One nightly job. SQLite is the entire database. The served site is fully
static. Target infrastructure cost: about $2/month plus domains.

## Local development

Requires [uv](https://docs.astral.sh/uv/), Node 20+, the `sqlite3` CLI, and
Docker (for the scraper container).

```sh
cd pipeline
uv run pytest                 # 72 tests
uv run ./run.sh               # full nightly pipeline, locally
uv run python -m scraper.backfill   # historical sessions (idempotent)

cd ../site
npm ci
npm run build                 # reads ../data/wi.sqlite; ~90s per biennium
npm run preview
node scripts/verify.mjs       # 10-check browser acceptance harness
```

`BUILD_SESSIONS=all npm run build` renders the full history.

## Repo layout

| Path | Contents |
|---|---|
| `pipeline/` | scraper wrappers, importer, integrity checks, data products, nightly `run.sh` |
| `pipeline/importer/schema.sql` | the entire data model |
| `pipeline/patches/` | documented fixes applied to the pinned scraper at runtime |
| `site/` | Astro + Tailwind + Pagefind static site |
| `infra/` | OpenTofu for the GCP free-tier resources (Phase 6) |
| `docs/` | implementation plan, backfill record, data research |

## Data and licensing

Code is [Apache-2.0](LICENSE). Legislative data comes from Wisconsin's
public record. openstates-scrapers is GPL-3.0 and is only ever invoked as a
subprocess CLI, never linked. Corrections are the highest priority issues:
[open one here](https://github.com/uprightsleepy/badger-politics/issues).
