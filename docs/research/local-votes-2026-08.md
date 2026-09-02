# Research: votes on local items, starting with Milwaukee and West Allis

2026-08-31. Research only; nothing here is built. Question: can Badger
Politics retrieve how local elected officials vote, item by item, with the
same "never guess" attribution the state and federal modules use, starting
with the City of Milwaukee and the City of West Allis? Everything marked
*verified* was probed live today with an identifying User-Agent.

## The headline finding

**Yes, for both cities, from one source.** Both councils run Granicus
Legistar, and both tenants of the public Legistar Web API answer without a
token and expose per-member votes on every item the clerk recorded a vote
on. Milwaukee County's Board of Supervisors, which represents every West
Allis and Milwaukee resident at the county level, is on the same API with
the same shape. That is three governments, one fetcher.

| Government | Legistar tenant | Per-member votes | Records begin | Votes reliably recorded from |
|---|---|---|---|---|
| City of Milwaukee Common Council | `milwaukee` | yes | 1996 (meetings) | at least 2008 (25 of 25 sampled acted items) |
| City of West Allis Common Council | `westalliswi` | yes | 2002 | about 2015 (22 of 25); 2010 is partial (15 of 25) |
| Milwaukee County Board of Supervisors | `milwaukeecounty` | yes | not probed | at least 2012 (24 of 25) |

## How the API works (verified)

Base: `https://webapi.legistar.com/v1/{tenant}/`. JSON, OData v3
(`$filter`, `$top`, `$skip`, `$orderby`), 1,000 rows per query, GET only,
public items only. Granicus says some tenants require a token; these three
do not. No rate limit or terms of use are published; NYC Council runs its
public API on the same product. The records themselves are Wisconsin
public records under the open meetings law. Treatment: identify ourselves,
throttle (0.4 s like the CFIS fetcher), cache immutable files forever, and
send each clerk a courtesy note before the first backfill.

The objects, in the order a fetcher walks them:

1. **`Events`**: meetings. `EventBodyName`, `EventDate`,
   `EventMinutesStatusName` (`Draft` or `Final`), `EventInSiteURL` (the
   public meeting page, our provenance link). Milwaukee County publishes
   duplicate event rows for one date where one row has zero items; the
   importer must skip empties rather than count them.
2. **`Events/{id}/EventItems`**: the agenda, one row per item.
   `EventItemMatterId` and `EventItemMatterFile` tie it to legislation;
   `EventItemActionName` is what the body did (`PASSED`, `ADOPTED`,
   `PLACED ON FILE`, `Approved`, `Referred for Legal Action to the City
   Attorney`, and so on); `EventItemPassedFlag`; `EventItemMover` and
   `EventItemSeconder` with person ids. Milwaukee 2025: 19 council
   meetings, 2,087 items, 1,398 with a recorded action. West Allis 2025:
   44 meetings, 1,288 items, 768 acted.
3. **`EventItems/{id}/Votes`**: one row per member: `VotePersonId`,
   `VotePersonName`, `VoteValueName`. This is the attribution key. It is
   the tenant's own person id on every row, so there is no name matching
   step to get wrong (the same property that made the federal module
   safe). Vote vocabularies, verified from each tenant's `VoteTypes`:
   - Milwaukee: Aye, No, Abstain, Present, Absent, Excused, VACANCY
   - West Allis: Aye, No, Abstain, Present, Excused, Absent, Non-Voting,
     Vacant, Pres (virt)
   - Milwaukee County: Aye, No, Present, Absent, Recuse, Abstain, Excused
4. **`EventItems/{id}/RollCalls`**: attendance. Milwaukee records it (15
   rows per item); West Allis does not.
5. **`Matters`**, **`Matters/{id}/Histories`**, **`Matters/{id}/Sponsors`**:
   the legislation, its path through committees (each history row names
   the acting body, action, date and event), and Milwaukee's sponsors by
   person id. West Allis matters carry no sponsors (items originate from
   staff and committees). Matter types are rich enough to filter noise:
   Milwaukee has 29 (Ordinance, Resolution, Charter Ordinance, Budget,
   Appointment, License, Communication...), West Allis 29 (Ordinance,
   Resolution, Claim, Rezoning, Conditional Use Permit, License
   Application(s)...).
6. **`OfficeRecords`** filtered to the council body: who sits, with start
   and end dates. Milwaukee's carry the seat (`OfficeRecordTitle` =
   "3rd District"), so member, seat and term come from one call. West
   Allis's say only "Ald." (see below).
7. **Provenance URLs** that resolve (verified 200):
   `https://{tenant}.legistar.com/LegislationDetail.aspx?ID={MatterId}&GUID={MatterGuid}`
   and `MeetingDetail.aspx?...` from `EventInSiteURL`. Every vote we show
   can link to the clerk's own page for the item and the meeting.

### Divided votes are real votes

Both cities record split decisions, not only unanimous consent:

- Milwaukee, 2026-07-31, file 260450, CONFIRMED: Aye 6, No 6, Abstain 3
  (Brower, Bauman, Westmoreland and Jackson among the Noes; Chambers Jr.
  and Coggs abstaining).
- West Allis, 2026-08-18, R-2026-5580, a TIF resolution, Adopted: Aye 9,
  No 1, Non-Voting 1 (the mayor presides and is recorded Non-Voting).
- Milwaukee County, 2026-06-25, file 26-2, SUSPENDED THE RULES: Aye 15,
  Excused 3.

## What each city needs beyond the API

### Milwaukee: complete from public sources

- Members and seats: `OfficeRecords` (15 current alders, districts 1 to
  15, terms 2024-04-16 to 2028-04-17; Brower's from 2025-04-04).
- District boundaries for address lookup: the city's own ArcGIS layer
  `https://milwaukeemaps.milwaukee.gov/arcgis/rest/services/election/alderman/MapServer/0`
  serves GeoJSON in WGS84 (`outSR=4326`, 223 KB, 15 polygons, fields
  `DISTRICT` and `ALDERPERSON`). The same data is on data.milwaukee.gov
  as the "Alder Districts" 2024 shapefile under a Creative Commons
  Attribution license. It slots straight into `lib/lookup.ts`, which
  already does point-in-polygon against bundled GeoJSON. (The older
  `maps2.milwaukee.gov` host timed out; use `milwaukeemaps`.)

### West Allis: two small gaps, both closed from the city's own publications

- **Seat per alder is not in Legistar.** `OfficeRecordTitle` is "Ald."
  for all ten members; the mayor is "Chair"/"Presiding Officer". The
  city's district pages (`westalliswi.gov/page/district-one` through
  `district-five`, an Apptegy CMS that embeds the page content as JSON in
  the HTML) name the two alderpersons per district. Extracted today:

  | District | Alderpersons (as the city prints them) |
  |---|---|
  | 1 | Ray C. Turner, Kimberlee Grob |
  | 2 | Chad Halvorsen, Marissa Nowling |
  | 3 | Suzzette Grisham, Danna Kuehn |
  | 4 | Patty Novak, Daniel J. Roadt |
  | 5 | Kevin Haass (Council President), Martin J. Weigel |

  Nine of ten match the Legistar `PersonFullName` exactly; Legistar has
  "Ray Turner" for "Ray C. Turner". Under the attribution mandate this
  is a ten-row curation table (`local_seats.json`: tenant, person id,
  district, basis URL, date verified), never a fuzzy match, and it is
  small enough to re-verify after each April election.
- **District boundaries.** The city's ArcGIS Server publishes them:
  `https://gis.westalliswi.gov/server/rest/services/Political_Layers_MIL1/MapServer/4`
  ("Aldermanic Districts", 5 polygons, `DISTRICT`, GeoJSON in WGS84
  verified) and `/5` ("Aldermanic Ward", 26 wards with `District` and
  `POLLING_PLACE`). No license text is attached to the service; it is a
  municipal public record, and the note should say where it came from.
  The ward layer's polling place field is a bonus: for West Allis
  addresses it could replace the hand-typed polling place on /my-reps/
  with the city's own assignment.

### Milwaukee County: feasible, one gap not yet probed

Votes and members (18 supervisors) work the same way. Supervisory
district boundaries were not located today; MCLIO's hub search returned
other cities' layers, and its Administrative service lists no district
layer. Candidates to check next: the LTSB ward layer (carries county
supervisory district for Milwaukee County wards) or a county election
commission publication.

## Sizing

Each acted item costs one `Votes` call; everything else is a handful of
calls per meeting.

| | Per year | Backfill span | Backfill calls | At 0.4 s |
|---|---|---|---|---|
| Milwaukee Common Council | ~1,400 | 2008 to 2026 | ~25,000 | ~2.8 h |
| West Allis Common Council | ~770 | 2015 to 2026 | ~8,500 | ~1 h |
| Milwaukee County Board | ~450 | 2012 to 2026 | ~6,500 | ~45 min |

One-time, cacheable forever once a meeting's minutes are `Final`; a
nightly incremental run refetches only `Draft` meetings and anything new,
which is a few hundred calls across all three. Committee meetings (the
bulk of Legistar events) are out of scope for a first pass; the council
floor is where the recorded votes that constituents ask about live, and
committee votes can be added by body name later without a schema change.

## Fit with the hard rules

- **$0, static**: public unauthenticated API plus two public GIS layers;
  one fetcher in the nightly, pages rendered from SQLite as ever.
- **Attribution never guesses**: votes are keyed by the tenant's person
  id; seats come from `OfficeRecords` (Milwaukee) or a curated table with
  a basis URL (West Allis). An id that is not in the body's office
  records on the vote date is a build failure, the same rule as "no vote
  outside a recorded term".
- **Coverage gaps over inference**: an item with no `Votes` rows is shown
  as "no recorded vote", never inferred from `PassedFlag`. West Allis
  before 2015 and both cities' committee stages are labeled as not
  covered. Values like Non-Voting (a presiding mayor), Vacant and Recuse
  are displayed as recorded, not folded into "did not vote".
- **Provenance**: every vote row links the clerk's item page and meeting
  page; the SourceStrip names the city, the system (Legistar) and both
  clocks.
- **Privacy**: address to aldermanic district happens in the browser with
  the bundled boundary file, exactly as the state lookup does.

## Proposed shape (when built)

1. `scraper/fetch_local_votes.py`, driven by a committed tenant registry
   (`tenant`, display name, council body name, first year to keep):
   Events for the body, EventItems, Votes for acted items, RollCalls
   where the tenant records them, Matters and Histories for items seen,
   OfficeRecords for the body. Raw JSON cached under `_data/local/`, one
   file per meeting, refetched while minutes are Draft.
2. Tables: `local_bodies`, `local_members(tenant, person_id, name, seat,
   start, end)`, `local_matters`, `local_events`, `local_actions
   (event_item_id, event_id, matter_id, action, passed)`, `local_votes
   (event_item_id, person_id, value)`, `local_attendance`. Boundaries as
   `site/public/data/local-districts-{city}.geojson`.
3. Checks: vote person in office on the date; one row per (item, person);
   vote values in the tenant's `VoteTypes`; every action carries a
   provenance URL; a tenant with zero Final meetings in 60 days is drift,
   not silence; empty duplicate events dropped and counted.
4. UI: on /my-reps/, after the state lookup, "Your city council" for
   addresses inside Milwaukee or West Allis (the district's alders, their
   last votes, and how they voted on divided questions), an alder page per
   member with the same record-first layout as legislators, a matter page
   per file linking the clerk's page, and the honest coverage notice for
   everyone else (two cities and one county today; other governments via
   the link-outs in the local-civics note).

## Do the sources permit API calls and crawling? (verified 2026-08-31)

Checked robots.txt on every host the module would touch, plus published
terms. Summary: the primary sources permit what we need; one GIS host
does not, and it has a clean substitute.

| Host | robots.txt | Reading |
|---|---|---|
| `webapi.legistar.com` | none (404) | A documented public API with its own examples page and OData paging guidance ("limiting queries by paging and filtering will reduce the load"). Programmatic access is the intended use; no ToS is presented on the host. |
| `milwaukee.legistar.com`, `westalliswi.legistar.com`, `milwaukeecounty.legistar.com` | none (404) | No crawl restrictions declared. We only need these for provenance links readers click, not for fetching. |
| `gis.westalliswi.gov` | none (404) | ArcGIS REST endpoints published by the city for public consumption; no restrictions declared. |
| `www.westalliswi.gov` | `Allow: /`, `Disallow: /api/` | The district pages we read for the seat table are explicitly allowed. |
| `city.milwaukee.gov` / `county.milwaukee.gov` | allow all but print views | Fine; we barely touch them. |
| `data.milwaukee.gov` | allows datasets, `Disallow: /api/` | The shapefile resource download is an ordinary allowed dataset link under a Creative Commons Attribution license. The CKAN `/api/` path is disallowed, so the pipeline should use the resource download URL, not the catalog API (one research probe today did use it; the build must not). |
| `milwaukeemaps.milwaukee.gov` | **`User-agent: *` `Disallow: /`** (only Google allowed) | The city's ArcGIS host declines automated access by default. Do not fetch boundaries here; use the identical 2024 Alder Districts shapefile from data.milwaukee.gov (CC BY) instead. |

Terms of use: Granicus's own terms govern granicus.com and say nothing
about the API or customer InSite sites; the two cities publish
liability/privacy disclaimers, not access restrictions. The underlying
content is Wisconsin public record (open meetings and public records
law). Net treatment, consistent with the rest of the pipeline: use the
purpose-built API and licensed downloads, identify with the project
User-Agent, throttle at 0.4 s, cache immutable records forever, respect
the one Disallow by sourcing Milwaukee boundaries from the open data
portal, and send each clerk a courtesy note before the backfill.

## What the full Milwaukee backfill showed (2026-08-31, built)

366 council meetings from 2008-01-15, 26,666 items with votes, 394,386
vote rows: Aye 373,293, Excused 14,678, No 5,751, Abstain 375, Absent 260.
Three source quirks, each handled without guessing:

- 29 vote rows carry no value at all (the clerk listed the voter, no
  position). Not a vote; skipped and counted in the import output.
- 11,270 votes fall outside their member's recorded office dates. The
  body's office records are incomplete for earlier years (several
  long-serving members have no dates for whole terms), so "vote inside a
  recorded term" is reported by the importer, not gated: the vote is the
  tenant's own record and the term table is the weaker of the two.
- One voter (Legistar person 2699, "Russell Stamper", 1,603 votes) has
  no office record, while the sitting Ald. Stamper is person 2748. The
  same person under two ids in the source. Kept as two members, the
  older one a former member known only from vote records; a merge would
  need a curated entry with a basis, like `person_merges.json` for the
  Legislature.
- Historical office records carry the title "Ald." or nothing, so seats
  are known for sitting members only; former members' pages say so.
- 89 rows repeat a member's identical value on one item (kept once) and
  one item (2023-07-31) records Ald. Pratt as both Aye and Excused: the
  record disagreeing with itself, so no position is attributed and the
  clerk's page is the reference.

## What the full West Allis backfill showed (2026-08-31, built)

403 council meetings from 2015-01-06, 10,591 items with votes, 110,914
vote rows: Aye 96,102, Non-Voting 10,435 (the presiding mayor), No 525,
Present 42, Abstain 16. Attribution is clean: every voter is in the
body's office records and every vote falls inside a recorded term. The
quirks: 3,794 rows list a member with no value (skipped, counted) and
18 identical repeats (kept once). Attendance is not in the vote rows for
either city; it is in the roll-call items, added later (see the parity
section below).

## Item links: InSite's ids are not the API's (2026-09-01, fixed)

`LegislationDetail.aspx?ID={MatterId}&GUID={MatterGuid}` built from the
API returns 200 with the body "Invalid parameters!", for every item in
both tenants: InSite keys a matter by its own id and GUID (file 201705 is
`ID=4913721` on InSite and `MatterId=56908` in the API), exactly as the
body pages turned out to be. A status check alone could not catch it. The
API's `EventInSiteURL` for a meeting does work, and that meeting page
lists every filed item with its InSite link under the file number, so the
fetcher now reads each meeting's page once (cached with the meeting; a
one-time pass over already-cached meetings) and the importer links an
item only to the page listed for its file number. A file number listed
with two different links, or not listed, links nowhere. No id is guessed
in either direction.

The meeting page's item grid pages at 200 rows, so Milwaukee's longest
agendas (five meetings, 2008 to 2024) needed the same form postback the
Departments listing uses; one helper now walks every InSite grid. After
that, Milwaukee links 26,863 of 26,885 filed items and West Allis all
10,294. The 22 left are one special meeting (2011-11-04) whose InSite
page lists a single item; those rows show the file number as text and
the meeting record link stands.

## Parity with the legislator profiles (2026-08-31, built)

Council member pages now carry what the legislator pages carry: a
portrait, office contacts, committee assignments, service dates, a follow
button, an Atom feed and a JSON record. Each piece has one source and one
rule, and a piece that fails its rule is left off rather than guessed.

- Portraits and contacts come from the cities' own district pages
  (`city.milwaukee.gov/CommonCouncil/...` and
  `westalliswi.gov/page/district-{one..five}`; both sites' robots.txt say
  `Allow: /`, and the West Allis `Disallow: /api/` path is not touched),
  fetched once a night by `scraper/fetch_local_profiles.py` under the
  project User-Agent. A Milwaukee photo attaches only when exactly one
  image on the district's page is captioned with that district; a West
  Allis photo only when the page's entry heading is the member's own
  name. An email attaches only when its local part carries the member's
  surname and the page holds exactly one; a phone only when exactly one
  remains after the number printed on every district page (the council's
  main line) is set aside. Milwaukee's page hrefs are obfuscated by its
  CDN, so an address is read from the link's `title` attribute, which only
  one district page exposes. Result: Milwaukee 14 of 15 portraits
  (District 9's page has none), 9 emails, 5 phones; West Allis 10 of 11
  portraits, 11 emails, 10 phones (the mayor's contacts come from the
  tenant's Persons record).
- Committees are every current OfficeRecord for a sitting member besides
  the council itself. InSite's page ids and GUIDs for a body differ from
  the API's BodyId and BodyGuid (0 of 100 matched, all 100 names did), so
  the link is by exact name against the tenant's own `Departments.aspx`
  listing. That grid shows 100 rows a page; later pages come through the
  plain form postback each page link carries for browsers without JS
  (one extra request per tenant a night). 89 of 92 Milwaukee seats and 68
  of 70 West Allis seats link; the rest name bodies the listing no longer
  carries and show as plain text.
- Service dates are the council's office records as held, so a Milwaukee
  member whose early terms lack dates shows only the dated ones.
- No party appears anywhere: council seats are nonpartisan, and the pages
  say so.
- Names: Milwaukee's office records abbreviate ("ALD. A. PRATT",
  "ALD. CHAMBERS JR."), while the same tenant's Persons record carries the
  first and last name ("Andrea" / "Pratt", "Mark" / "Chambers Jr."). A
  record name that already reads as a name (West Allis: "Martin J.
  Weigel") is shown as written; an all-caps abbreviation gives way to the
  person record's first and last name; with no person record (a member
  known only from vote rows) the abbreviation is shown in title case. The
  record's own string is kept as `record_name` and shown on the page when
  it differs. Slugs follow the shown name, so the Milwaukee URLs changed
  before any production release.
- Attendance: the API's `EventItems/{id}/RollCalls` lists every member
  with Present, Excused, Absent or Non-Voting for each roll-call item
  (`EventItemRollCallFlag`), in both tenants. Fetched once per meeting
  and cached with it; imported under the votes' rules (no value is no
  fact, two values is no fact) into `local_rollcalls`, gated on member
  ids and the tenant's vocabulary. Shown as meetings recorded present of
  meetings where the roll was called with the member listed, with every
  value as recorded.
- Outcomes and motions, from data already held: "on the losing side" is
  an Aye or No opposite the clerk's passed flag (items without the flag
  left out of both counts); "sole No votes" are items where the member
  cast the only No; "motions they moved" are items whose record names
  the member as mover (`EventItemMoverId`, present on 99% of acted
  items, kept with the seconder).
- A presiding officer's page (the West Allis mayor) leads with
  tie-breaking votes: Aye/No cast while the other voters split evenly,
  recounted from the vote rows (6 on record, all Aye on 5-5 splits). His
  other 49 Ayes joined an already unanimous council and the rest is
  Non-Voting, which the page now says outright.
- Term end from the office record; every sitting member's term ends in
  April 2028, and the seat is filled at that April's spring election.
- Upcoming meetings: the fetcher already receives the not-yet-held
  meetings and now keeps them (`upcoming.json` -> `local_upcoming`), and
  the civic calendar merges a city's meetings client-side only for
  readers whose saved address lookup landed in that city. Council
  meetings are open to the public under the Open Meetings Law (Wis.
  Stat. 19.81 to 19.98); the day panel says to confirm against the
  posted agenda.
- A paged full vote record at 200 a page, noindex like a legislator's,
  and one page per council district drawing the district within its city
  from the committed boundaries (`importer/local_district_shapes.py`).

## Open questions for the owner

1. Scope of the first build: both city councils plus the county board, or
   the two councils only? The county adds supervisory districts as an
   unresolved geography.
2. Committee votes: council floor only at first (recommended), or
   include committee stages where Legistar records them?
3. How far back: everything the clerk recorded (2008 Milwaukee, 2015 West
   Allis), or the current terms (2024 on) with history added later?
4. Should West Allis's ward-to-polling-place field replace the hand-typed
   polling place on /my-reps/ for West Allis addresses?
5. Courtesy notice to the three clerks before the backfill? (Recommended;
   it costs one email each and the traffic is a few thousand cached
   requests once.)

## Sources probed

- Legistar Web API: `https://webapi.legistar.com/v1/{milwaukee,westalliswi,milwaukeecounty}/` and its examples page (`/Home/Examples`)
- Milwaukee InSite: `https://milwaukee.legistar.com/`; West Allis InSite: `https://westalliswi.legistar.com/`
- Milwaukee aldermanic districts: `https://milwaukeemaps.milwaukee.gov/arcgis/rest/services/election/alderman/MapServer/0`; `https://data.milwaukee.gov/dataset/aldermanic-districts` (CC BY)
- West Allis aldermanic districts and wards: `https://gis.westalliswi.gov/server/rest/services/Political_Layers_MIL1/MapServer/{4,5}`
- West Allis council roster: `https://www.westalliswi.gov/page/district-one` through `district-five`, `https://www.westalliswi.gov/page/contact-your-alderperson`
- Milwaukee council district pages (portraits, contacts): `https://city.milwaukee.gov/CommonCouncil/Council-Members/District{1..15}`
- InSite body listings (committee links): `https://milwaukee.legistar.com/Departments.aspx`, `https://westalliswi.legistar.com/Departments.aspx`
- West Allis meeting records index: `https://www.westalliswi.gov/page/common-council-agendas-minutes`
