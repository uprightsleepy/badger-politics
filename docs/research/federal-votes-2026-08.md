# Research: Wisconsin's federal delegation votes

2026-08-29. Question: how would Badger Politics show how Wisconsin's
U.S. senators (and, by extension, its House delegation) vote at the
federal level? Every source below was verified live today, not from
prior knowledge.

## The delegation (roster verified)

| Seat | Member | Party | bioguide | LIS |
|---|---|---|---|---|
| Senate | Tammy Baldwin | D | B001230 | S354 |
| Senate | Ron Johnson | R | J000293 | S345 |
| House 1–8 | Steil, Pocan, Van Orden, Moore, Fitzgerald, Grothman, Tiffany, Wied | 6R/2D | verified | n/a |

Roster source: `unitedstates/congress-legislators` (public domain,
community-maintained, used by GovTrack/ProPublica lineage projects) —
carries bioguide, LIS, state, district, and term history. Verified
serving today.

## Sources, as verified 2026-08-29

### 1. Senate roll calls — senate.gov LIS XML (canonical, use this)

- Menu per session: `senate.gov/legislative/LIS/roll_call_lists/vote_menu_119_2.xml`
  — verified live, currently 231 votes for the 2026 session, newest
  Aug 8 (cloture on S. 5271, 52-46).
- Per-vote XML: `.../roll_call_votes/vote1192/vote_119_2_00231.xml` —
  **member-level positions with LIS ids**: verified Baldwin `Nay`,
  Johnson `Yea` on that vote.
- No key, no rate-limit documentation (be a polite nightly client),
  U.S. government work: no license restriction.
- Attribution is exact by LIS member id — meets the exact-match rule
  with no surname disambiguation at all.

### 2. House roll calls — clerk.house.gov EVS XML (canonical for House)

- Per-vote: `clerk.house.gov/evs/2026/roll200.xml` — verified 200 with
  an identifying User-Agent (`BadgerPolitics/1.0 (badgerpolitics.org;
  contact email)`); the bare landing page 403s anonymous proxies, so
  the fetcher must always send our UA. DTD `rollcall-vote v1.0`,
  member-level with state/party, WI extractable.
- Vote numbering is per calendar year, discoverable by iterating roll
  numbers until 404 (the unitedstates scrapers do exactly this).

### 3. Congress.gov API (Library of Congress) — House only, beta

- `house-vote` endpoints (list / item / member-votes) exist, **beta**,
  cover the 118th–119th Congresses, member-level, free API key.
- **No Senate vote endpoint exists.** The API cannot replace source 1.
- Useful later as a cross-check for House data, not as the primary.

### 4. unitedstates/congress scrapers

Public-domain Python scrapers wrapping sources 1–2. Unlike
openstates-scrapers there is **no GPL boundary problem** (public
domain), so we could import them directly — but the two XML formats
are simple enough that a ~200-line fetcher of our own, in the style of
enrich_companions (cached, throttled, identified UA), is less
dependency surface than adopting their framework.

### Not viable

- **ProPublica Congress API**: discontinued; do not build on it.
- **GovTrack**: no public API since 2018; their site is a consumer,
  not a source.

## Fit with the hard rules

- **Cost**: $0. Two XML feeds and one JSON roster, all free, fetched
  nightly by the job we already run. No new GCP resources.
- **Static**: pages build from SQLite like everything else.
- **Provenance**: every vote links to its senate.gov / clerk.house.gov
  XML; bills link out to congress.gov (constructible:
  `congress.gov/bill/119th-congress/senate-bill/5271`). SourceStrip
  sources become "U.S. Senate" / "U.S. House Clerk".
- **Attribution**: LIS/bioguide ids, exact or absent. No guessing.
- **Scope honesty**: this is a new module, not an extension of the
  legislature data. Federal pages must say what they are and are not
  (roll calls only; no federal bill tracking, no federal money — FEC
  is a separate research question).

## Proposed architecture (when built)

1. **Pipeline**: `scraper/fetch_federal_votes.py` — nightly, cached
   per vote file. Senate: read the session menu, fetch new per-vote
   XMLs. House: iterate roll numbers past the last known. Store the
   full chamber result but our UI shows the WI ten.
   Tables: `federal_members` (from the roster, WI only),
   `federal_votes` (congress, session, chamber, number, date, question,
   result, tallies, source_url, bill ref), `federal_vote_records`
   (vote_id, bioguide, position) — schema mirrors vote_events /
   vote_records so the site code rhymes.
2. **Checks**: tallies must reconcile with counted positions (same
   invariant we hold for state roll calls); WI delegation must be
   exactly 10 or the roster changed and the run fails loudly.
3. **Site**: `/federal/` hub (both senators' latest votes, the
   delegation grid); `/federal/tammy-baldwin/` per-member vote lists
   with the same attendance honesty as state pages; per-vote pages
   optional at first (the official XML link may suffice).
4. **Search/follow**: members get the `Legislator` facet with a
   `chamber: U.S. Senate` value; follow works like state legislators
   once per-member JSON ships.

## Effort and sequencing

- Senate-only first (the question asked about senators): fetcher +
  tables + checks + two member pages + hub. Roughly a Phase-1-sized
  day of work.
- House second: same shape, one more fetcher.
- Backfill: senate.gov menus go back decades; start with the 119th
  Congress (2025–26) and extend backward as wanted.

## Open questions for the owner

1. Is federal coverage in scope for badgerpolitics.org's identity
   ("v1: legislature module"), or does it dilute the Wisconsin-first
   positioning? The counterargument: "how did MY senators vote" is a
   top search intent the site currently cannot answer.
2. Senate-only or full delegation from day one?
3. Does the 2026 Senate race page (SD is state; the U.S. Senate seat
   is not up in WI in 2026 — Baldwin re-elected 2024, Johnson to 2028)
   change priorities? Federal votes are evergreen either way.
