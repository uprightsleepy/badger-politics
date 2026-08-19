# Badger Politics

A free, independent one-stop shop for Wisconsin politics — [badgerpolitics.org](https://badgerpolitics.org).

v1 is the **legislature module**: every bill (current and historical sessions), full status
timelines, per-legislator roll call votes, committee hearings, and who's up for reelection —
including the "Hearing None" view of bills that died in committee without ever getting a hearing.

> **Badger Politics is an independent project, not affiliated with the State of Wisconsin.**

## How it works

A nightly job scrapes the Wisconsin Legislature's public site, imports everything into a single
SQLite file, runs hard integrity checks, and rebuilds a fully static site:

```
openstates-scrapers (wi) → SQLite → integrity checks → Astro static build → Firebase Hosting
```

No servers, no database service, no accounts, no tracking cookies. Data freshness is nightly,
and the site says so.

## Repo layout

| Path | Contents |
|---|---|
| `pipeline/` | scraper wrapper, importer (JSON → SQLite), integrity checks, nightly `run.sh` |
| `pipeline/importer/schema.sql` | the entire data model (SQLite is the only database) |
| `site/` | Astro + Tailwind + Pagefind static site (reads SQLite at build time) |
| `infra/` | OpenTofu for the GCP free-tier resources (Cloud Run Job, Scheduler, GCS) |
| `data/` | local SQLite builds (gitignored) |

## Local development

Requires [uv](https://docs.astral.sh/uv/), Node 20+, and the `sqlite3` CLI.

```sh
# create an empty database from the schema
sqlite3 data/wi.sqlite < pipeline/importer/schema.sql

# tests + lint
cd pipeline
uv run pytest
uv run ruff check .
```

Phases 0–5 run entirely locally against public, keyless sources — no GCP, no credentials.

## Data & licensing

Site and pipeline code are [Apache-2.0](LICENSE). Legislative data comes from the Wisconsin
Legislature via [openstates-scrapers](https://github.com/openstates/openstates-scrapers)
(invoked as a CLI, never linked — it's GPL-3.0). All bulk exports and the static JSON API are
provenance-filtered to public-domain-clean rows.
