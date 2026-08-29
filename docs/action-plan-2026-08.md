# Action plan: deep-research report, August 2026

Derived from `docs/deep-research-report.md` (the product/UX/SEO audit received
2026-08-29). This plan records what of it we will build, in what order, and
what we will not build and why. The report was researched against the site as
it stood before the late-August homepage work, so its first job here is
reconciliation: a good deal of its P0 list already shipped.

## Already shipped (do not redo)

| Report recommendation | Status on the live site |
|---|---|
| Search + "who represents me" as the homepage front door | Shipped. Address-first hero completes the lookup in place; saved-district state replaces the prompt on return visits. |
| Search filters / entity types | Shipped. Type chips (Bills, Legislators, Committees, Topics, Districts, Money) plus session and outcome facets, baked into the Pagefind index. |
| Floating search results, no layout shift | Shipped. |
| "What matters now" record-driven surface | Shipped in first form: latest-activity cards and the session bill flow on the homepage. |
| Technical SEO baseline | Largely shipped: robots.txt, sitemap index, per-entity titles/descriptions (duplicates 20,500 → 46), JSON-LD on 20,577 pages, BreadcrumbList where breadcrumbs render. Remaining: Search Console submission (owner action) and breadcrumb coverage on the templates that still lack it. |
| Follow + feeds | Bills and legislators have follow; bills, committees and legislators have Atom feeds. |
| Address-first election page | Shipped: /elections/2026/ renders "your ballot" from the saved district. |
| District map fixed, not decorative | Shipped (Mercator projection fix). |
| Provenance philosophy | Exists in About and in per-dataset methodology; not yet a per-module UI component (Phase 1). |

## Constraint filter

Hard rules exclude some of the report outright. Recording the substitutions so
they are decisions, not omissions:

- **No email/push alerts** (no servers, no functions). Substitute: Atom feeds
  per entity, plus a client-side "changes since your last visit" computed by
  diffing static JSON against a localStorage timestamp. This is Phase 3.
- **No accounts, no sync.** "My Wisconsin" is localStorage-only, as the report
  itself recommends for the first stage.
- **No news operation, no ideology scores, no user ratings.** The report
  agrees; noted here so it stays settled.
- **No county/municipality knowledge graph yet.** The DB has county-level
  statewide results but no municipality-to-district mapping; that is new
  pipeline work, parked as Phase 5 pending a data source decision.
- **Voter transactions stay with MyVote.** We explain and hand off; we do not
  rebuild registration/polling tools.

## Phase 0 — prerequisite: the nightly job

The report's trust framework leans on freshness ("Badger last checked /
official record through"). That strip is only honest if the data moves.
Data is frozen at the 2026-08-24 import. **Blocked on enabling the Cloud Run
and Cloud Scheduler APIs in the prod project (owner action).** Once enabled:
nightly Cloud Run Job runs the existing pipeline, uploads the snapshot,
triggers the deploy workflow. Nothing else in this plan depends on it, but
every freshness claim gets stronger the day it lands.

## Phase 1 — trust as interface, directory search, search polish

Small, high-leverage, all static.

1. **Provenance strip component** (`SourceStrip.astro`): source name, "pulled"
   date, "record through" date, and a coverage state, rendered from `meta`
   plus per-template props. Placed on bill, legislator, committee, district,
   money and election templates. The money pages' existing coverage language
   becomes the shared coverage-notice variant ("X of Y linked", never a false
   zero). No new methodology — the About page already defines it all.
2. **Committee directory upgrade**: the grouped list becomes a filterable
   directory (client-side, same pattern as FilterBar): name search, chamber
   filter, and columns for chair, member count, next scheduled hearing, and
   bills-died-here. All fields already exist in the DB.
3. **Search result metadata**: results carry their facet metadata (type badge;
   party/district for people; session/status for bills), and exact
   identifiers (SB 268, AB 1, "assembly 14") rank first via a pre-check on
   the query shape. Recent searches (localStorage, capped, clearable) shown
   on focus before typing. No-result state gains recovery actions: clear
   filters, try bills-only, find-my-legislators, link to docs.legis search.
   Mobbin check before building: grouped-autocomplete metadata density
   (report handoff questions 3, 4, 25).
4. **Breadcrumbs on remaining templates** (districts, subjects, money detail,
   hearings) with BreadcrumbList; visible trail matches markup.

## Phase 2 — election → race → candidate layer

The biggest unshipped SEO and utility item. Data already in SQLite:
`elections` (132 seats, WEC ballot status, opponents), `election_history`
(426 result rows with official totals), `statewide_races` (53),
`statewide_county_results`, `statewide_history`.

1. **Race pages, one per seat on the 2026 ballot** (~116 legislative races +
   statewide): `/elections/2026/assembly-14/` — office, district (map thumb),
   incumbent with record links, WEC-approved candidates, open-seat flag,
   past results for the seat from election_history, provenance strip.
   Candidate cards symmetric; party as label + badge, never color alone.
2. **Election hub upgrade**: /elections/2026/ gains a race directory
   (filter: chamber, open seats, on-your-ballot) above the existing
   personal-ballot module.
3. **Results-state readiness**: templates render a "results" section from
   election_history rows when they exist for the cycle, so election night is
   a data import, not a redesign. (Same pattern as fiscal estimates on bills:
   conditional module.)
4. **Comparison, modest form**: on a race page, incumbent's sourced record
   (attendance, bills led, money coverage state) beside challenger cards that
   carry only what WEC provides. No questionnaires, no positions without a
   source. Mobbin check: matchup layout symmetry (handoff question 10).

## Phase 3 — My Wisconsin: unified saved state

1. **Follow everywhere**: extend the existing FollowButton to districts,
   committees and races (bills and legislators already have it). One
   localStorage schema, typed entries.
2. **/following/ becomes the unified Saved page**: mixed list grouped by
   type, each row reusing the entity result row from Phase 1.
3. **"Since your last visit"**: on the Saved page, diff followed entities'
   latest-action dates (from the static JSON the site already ships) against
   a stored last-visit timestamp; render a plain changes list. No servers,
   no notifications — the page answers "what changed?" when the user returns.
4. Mobbin checks: unified multi-type watchlist IA (question 14), change
   representation (question 17).

## Phase 4 — dense-data and mobile normalization

1. Audit the wide tables (roll calls, money rankings, election history) at
   390 px: sticky identity column on desktop, fewer columns + disclosure rows
   on mobile, `overflow-x-auto` everywhere, sortable headers with announced
   state.
2. Related-entities module on templates that still dead-end (hearings,
   subjects, votes): "connected to" links with typed labels, honoring the
   rule that every edge has provenance.
3. Metric cards adopt the source-aware pattern (value, definition, period,
   source) — mostly relabeling of what exists.

## Phase 5 — parked pending decisions

- County/municipality pages (needs a municipality-district source; LTSB has
  candidates).
- Embeddable widgets (CSP work + upkeep; unclear demand).
- API expansion beyond current /api/v1 (wait for actual requests).

## Owner actions (cannot be done from this repo)

1. Enable Cloud Run + Cloud Scheduler APIs (unblocks Phase 0).
2. Submit sitemap in Google Search Console; grant read access for query data.
3. Decide whether Phase 2 should ship before or after the nightly job — the
   race pages are static and can ship first, but their WEC data also goes
   stale without Phase 0.

## Sequencing rationale

Phase 1 before Phase 2 because the provenance strip and entity result row are
reused by every race page. Phase 3 after 2 because a watchlist is worth more
once races are followable. The report's own dependency chart agrees: trust →
search → connected entities → elections → saved state → activity.
