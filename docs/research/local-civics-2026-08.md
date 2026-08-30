# Research: county and local civic data under each representative

2026-08-29. Question: what district/county-level civic information —
local meetings above all — can Badger Politics feasibly pull in and
show under individual representatives? Everything marked *verified* was
probed live today.

## The headline finding

There is **no central Wisconsin repository of local meeting notices**.
The open-meetings law requires posting, but posting happens at each
body's own door and website. What *does* exist, and works, is the
agenda-management platforms the larger governments buy — and the
biggest one has a free, public, unauthenticated JSON API.

## Verified sources

### 1. Legistar Web API (Granicus) — verified live, the anchor source

`webapi.legistar.com/v1/{client}/Events` returns upcoming and past
meetings as JSON: body name, date, time, location, agenda status and
file, minutes, and a public InSite URL per meeting. No key, no auth.
Wisconsin tenants verified today (HTTP 200 with real data):

| Client | Body | Sample verified |
|---|---|---|
| `milwaukee` | City of Milwaukee | Public Debt Commission, Sept 15 |
| `milwaukeecounty` | Milwaukee County | ADRC Governing Board, Sept 15 |
| `madison` | City of Madison | Ethics Board (live calendar) |
| `dane` | Dane County | Personnel & Finance, **Aug 31** — agenda modified yesterday |
| `waukesha` | Waukesha | 200 |
| `racine` | Racine | 200 |

That set alone covers the state's two biggest counties and three of its
largest cities — a large share of Wisconsinites. More tenants likely
exist; enumeration is by trying names (Granicus publishes no directory).

### 2. District → county/municipality mapping — verified available

- LTSB's live BAS ward layer (`mapservices.legis.wisconsin.gov`,
  `BAS_Live_Collection_Wards`) carries county and municipality
  (CNTY_NAME, MCD_NAME, CTV) per ward. Verified today.
- The LTSB GIS hub currently publishes **WI Municipal Wards (July
  2026)**; LTSB ward products have historically carried assembly/senate
  assignments — verify the field list at build time. Fallback if the
  columns are absent: assign wards to districts geometrically from the
  two official LTSB layers we already use, and say so in the method
  note (computation on official geometry, not inference).
- This yields the module both pages need: "Assembly District 14 lies in
  Milwaukee and Waukesha counties; municipalities: West Allis, …" — and
  it is the join key that puts *county* meetings on a *representative's*
  page honestly.

### 3. Census ACS at legislative-district level — works, now needs a key

The ACS 5-year API has `state legislative district (lower/upper
chamber)` geographies for Wisconsin. As of today the endpoint redirects
keyless requests to a "Missing Key" page: a **free** API key is
required (env var in the nightly; no cost, no rules conflict). Enables
a sourced, vintage-labeled district profile (population, median income,
age structure) on district pages.

### 4. Already in our SQLite

`statewide_county_results` holds certified county-level results for
statewide races — county context ("how the counties overlapping this
district voted for governor") can ship with zero new ingestion, labeled
carefully: counties are not districts.

## Verified dead ends and link-outs

- **wisconsinpublicnotice.org** (newspaper association archive of all
  legally published notices, including hearings and ordinances):
  verified live, searchable by region — **no API, no RSS**. Use as a
  per-region link-out ("all legal notices for your area"), never as an
  ingest.
- **CivicClerk** (second-largest platform among WI counties): has an
  API pattern, but tenant subdomains are not guessable — five county
  guesses all 404ed today. Second wave: discover tenants from county
  websites' agenda links, then the same nightly fetch shape.
- **BoardDocs (school boards)**: no public API. Link-out only.
- **Small towns/villages**: PDFs on TownWeb-class sites. Not feasible
  at scale; the coverage notice must own this gap.

## Fit with the hard rules

- **$0**: public unauthenticated APIs plus one free Census key.
- **Static**: one nightly fetch; pages render from SQLite as ever.
- **Provenance**: every meeting links to its Legistar page; the
  SourceStrip names the county/city system and both clocks. A meeting
  can change after our nightly pull — the strip's "pulled" date plus
  the live link is the honest treatment.
- **Coverage gaps over inference**: this dataset is *structurally*
  partial (six tenants today, 72 counties). The money pages' coverage
  notice is the required pattern: "Meetings shown for N governments;
  most smaller bodies post only to their own sites" with link-outs —
  never an implied statewide calendar.

## Proposed shape (when built)

1. `scraper/fetch_local_meetings.py`: nightly, hits a committed tenant
   registry (client id, display name, county scope), pulls Events for
   the next ~45 days, caches raw JSON.
2. Tables: `local_bodies(tenant, body, county_fips)` and
   `local_meetings(tenant, body, date, time, location, agenda_url,
   insite_url)`; `district_places(seat, county, municipalities)` from
   the LTSB ward file.
3. UI: an "In your district" module on legislator and district pages —
   counties and municipalities, the next few county-board/committee
   meetings for overlapping counties, the clerk/notices link-outs, and
   the coverage notice. District pages also gain the ACS profile once
   the key exists.
4. Checks: every meeting row must carry a source URL and a future-or-
   recent date; a tenant returning zero upcoming meetings for 30+ days
   is flagged (platform drift), not silently empty.

## Open questions for the owner

1. Get a Census API key (free, instant) for the district profiles?
2. Tenant expansion appetite: ship with the six verified now and grow,
   or spend a session harvesting CivicClerk/Legistar tenants from all
   72 county websites first?
3. Does "local meetings" belong on legislator pages, district pages, or
   both? (Recommendation: district pages as home, a compact echo on the
   legislator page.)
