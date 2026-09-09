# Wisconsin city expansion

Reviewed September 8, 2026. Add cities in descending population order, after
verifying their official sources, permitted retrieval and recorded identities.
Population determines the review queue; it does not authorize collection.

## Order and scope

Use the Census Bureau's Vintage 2025 estimates for July 1, 2025, from its
[Wisconsin place file](https://www2.census.gov/programs-surveys/popest/datasets/2020-2025/cities/totals/sub-est2025_55.csv).
Select `SUMLEV=162` and names ending in ` city`, then sort `POPESTIMATE2025`
descending. This gives 190 whole incorporated cities; towns, villages and
county fragments are excluded. The source is a fixed planning input, not a new
nightly dependency. Re-rank when the next official vintage is released.

[Census download documentation](https://www.census.gov/data/tables/time-series/demo/popest/2020s-total-cities-and-towns.html),
[open-data policy](https://www.census.gov/topics/research/research-transparency-public-access/open-data.html).
The source file's SHA-256 is
`5db65614c832b99ba6dcb8ed78f588190202026d9f850d75c33155bb9dec8763`.
`www2.census.gov/robots.txt` returned 200 with no restriction for the project's
user agent on this bulk path. The single download used the identifying agent
and a minimum one-second interval. Raw captures remain outside Git.

| Rank | City | Population | Next action |
| --- | --- | ---: | --- |
| 1 | Milwaukee | 562,407 | Existing collector and history retained. |
| 2 | Madison | 286,233 | Enable the reviewed collector below; initial history from 2025. |
| 3 | Green Bay | 106,675 | Paused: clarify CivicPlus reuse terms and obtain an approved export/integration. |
| 4 | Kenosha | 99,239 | Paused: city robots returned 403; clarify access. |
| 5 | Racine | 77,908 | Paused: city terms prohibit systematic automated collection. |
| 6 | Appleton | 75,452 | Added for dev validation; shared Legistar collector, history from 2025. |
| 7 | Eau Claire | 72,465 | Review AgendaCenter records and district/at-large representation. |
| 8 | Waukesha | 70,872 | Added for dev validation; shared Legistar collector, history from 2025. |
| 9 | Oshkosh | 67,460 | Source and policy review pending. |
| 10 | Janesville | 66,929 | Source and policy review pending. |
| 11 | West Allis | 60,119 | Existing collector and history retained. |
| 12 | La Crosse | 50,784 | Source and policy review pending. |
| 13 | Sheboygan | 49,376 | Source and policy review pending. |
| 14 | Wauwatosa | 48,649 | Source and policy review pending. |
| 15 | Fond du Lac | 44,541 | Source and policy review pending. |
| 16 | Brookfield | 41,448 | Source and policy review pending. |
| 17 | Wausau | 40,188 | Source and policy review pending. |
| 18 | New Berlin | 39,953 | Source and policy review pending. |
| 19 | Sun Prairie | 39,227 | Source and policy review pending. |
| 20 | Oak Creek | 38,296 | Source and policy review pending. |

The remaining ranked cities appear below. Do not guess API tenant names or
enable a whole hosting platform to accelerate this queue. For each city:

1. Follow the city's official links to its records system. Review robots,
   terms, API documentation, dataset licenses and published rate limits.
2. Prefer a documented public API or official bulk export. If access is denied
   or reuse is unclear, pause that source and request an approved extract.
3. Verify council/body IDs, individual vote IDs, roll-call vocabulary, office
   dates, district/at-large seats, and source links against real records.
4. Test attribution, voice votes, paging, interruption recovery and unchanged
   existing-city imports. Make incomplete coverage visible before publication.
5. Add only reviewed host/path/method permissions and a bounded backfill.
   Refresh the separate policy job before the next collector run.

## Madison: approved scope

The city's [legislative information page](https://www.cityofmadison.com/CityHall/legislativeInformation/)
links to `madison.legistar.com`. The documented public API tenant is `madison`;
body ID `1`, `COMMON COUNCIL`, matches the
[official council](https://www.cityofmadison.com/council/council-members).
The council has 20 districts and a presiding mayor. No credentials were needed
for the reviewed public GET requests.

Policies reviewed:

- [City conditions of use](https://www.cityofmadison.com/policy/conditions):
  reuse of public information is permitted subject to protected content;
  logos and images require permission. This addition collects factual records
  and source links, with no city-page or portrait download.
- [City data policy](https://www.cityofmadison.com/policy/data): the city does
  not warrant completeness or accuracy; preserve attribution and uncertainty.
- [Legistar public API documentation](https://webapi.legistar.com/Home/Examples):
  use documented public endpoints, filters and paging; a tenant can require a
  token. Any later denial must stop collection, without an alternate bypass.
- [API robots](https://webapi.legistar.com/robots.txt) and
  [Madison InSite robots](https://madison.legistar.com/robots.txt) returned 404.
  These specific missing responses are recorded in the policy manifest.
- [City robots](https://www.cityofmadison.com/robots.txt) returned 200; public
  council paths were not disallowed. The runtime does not fetch this host.

Permitted API GET routes are `VoteTypes`, `OfficeRecords`, `Bodies`,
`Persons/{id}`, `Events`, `Events/{id}/EventItems`, and each item's `Votes` or
`RollCalls`. InSite retrieval is limited to `Departments.aspx` and
`MeetingDetail.aspx`, including their ordinary read-only form pagination.
No attachment, video, image, private endpoint or other tenant is enabled.

Requests are sequential, with at least one second between requests per host
and the existing identifying user agent. Longer published delays and retry
instructions take precedence. Existing access-denial, rate-limit and changed
robots protections still apply. A new policy report is required because the
manifest changes; no previous report can approve these new routes.

## Data validation and collection bounds

Bounded review found 105 council office records. Three sampled meetings
(January 14, 2025; July 21 and August 4, 2026) use `Approved` for settled
minutes, rather than Milwaukee and West Allis's `Final`. Three individually
recorded motions in the January meeting each contain 21 distinct person IDs.
Their 63 rows include Aye, No, Abstain, Absent, Excused and Non Voting.
Twelve sampled voice-vote actions contain no individual positions. A passed
motion or voice vote must never be expanded into votes for all council members.

Madison leaves the alder's office title empty. Its person records identify
districts through `PersonWWW` URLs matching exactly
`http(s)://www.cityofmadison.com/council/districtN/`. Use only the URL on that
same person ID, retain it as the attribution basis, and reject out-of-range
districts. Missing or unrelated URLs leave the district unknown. No names
are joined, and the mayor receives no invented district. Memberships and
votes remain keyed by `(tenant, person_id)`.

Initial coverage starts January 1, 2025. This is an explicit initial range,
not a claim that earlier records do not exist. It leaves Milwaukee's 2008 and
West Allis's 2015 start dates unchanged. Review older Madison records before
extending the range. No existing archived meeting is removed, including a
meeting omitted from a later source listing.

Each run collects at most five previously uncached Madison meetings. The first
batch begins with the reviewed January 14, 2025 meeting (API event `27791`),
which has verified individual dissent, then takes the newest remaining meetings.
This preserves the existing no-dissent integrity gate even when recent meetings
contain only voice votes. A missing bootstrap meeting fails collection for review.
Subsequent batches proceed newest first. Draft minutes continue refreshing without consuming that city's new
meeting allowance. Settled meetings remain cached. A failed response or
interrupted file replacement cannot replace a complete cached meeting with a
partial JSON file. Responses at the API page cap fail rather than silently
publishing a truncated roster or meeting.

After a successful collection, `coverage.json` records the start year, listed
past meetings, pending meetings and check time. The importer requires valid
coverage for bounded backfills and rolls back the transaction on invalid or
missing metadata. Site pages and council/member JSON expose this coverage;
the site labels pending history and explains unrecorded voice votes. Madison
district maps and address lookup remain unavailable until boundary sources
receive their own review.

[Mobile coverage notice preview](images/madison-coverage-mobile.png) shows the
actual component with fixture counts during and after backfill.

## Runtime and cost

Reuse the existing sequential community stage, private source archive, SQLite
import and static exports. No worker, paid API, new service or dependency is
added. The five-meeting cap bounds initial request growth; it is not a hard
wall-clock deadline. Sampled agendas had 67–126 acted items, each requiring a
vote request even when a voice vote returns no positions. Five similarly sized
meetings mean roughly 335–630 vote requests, plus agendas, attendance, links
and roster refreshes. Allow roughly 10–20 additional minutes per backfill run
at the current pacing, with source latency, drafts and longer agendas capable
of increasing that estimate. Measure the first completed community stage
before raising the limit.

Appleton and Waukesha each add at most two uncached meetings per run. Their
four sampled meetings needed 65 vote requests in total; office/person refreshes,
attendance and public page pagination add work. Budget roughly 5–10 additional
minutes for both cities at the existing pacing, or about 15–30 minutes including
Madison during initial backfill. This is an estimate, not a deadline; measure
actual stage duration and archive growth before increasing the batch size.

After backfill, settled history adds no repeated meeting requests. Roster
refreshes and new/draft meetings remain the recurring work. The existing public
repository runner and archive budget still apply; raw cache and generated page
growth should be measured after the first backfill before assigning a storage
cost estimate. Keep the combined project below $10/month, preferably $0–5.
Do not speed up requests to compensate for runtime or add concurrent scrapers.

## Sources queued for review

- Green Bay's [official meeting page](https://www.greenbaywi.gov/129/Meetings-Agendas-Minutes)
  links to [CivicClerk](https://greenbaywi.portal.civicclerk.com).
  [CivicPlus terms](https://www.civicplus.help/legal-center/docs/civicplus-terms-of-use),
  sections 7–8, restrict automated request rates and AI-related use, with a
  limited authorized API/export exception. Portal robots returned 200 with no
  disallow rules, but that does not resolve reuse permission. No record API was
  queried. Obtain clarification and an approved export/integration before collection.
- Kenosha's [official agenda viewer](https://kenosha.granicus.com/AgendaViewer.php?clip_id=6208&view_id=2)
  uses a different Granicus interface. [City robots](https://www.kenosha.org/robots.txt)
  returned 403 with the identifying user agent. Collection stopped before any
  records request; do not use a different host or browser to bypass the denial.
- Racine's [council site](https://cityofracinewi.gov/government/city-leadership/common-council/)
  links to [Legistar](https://cityofracine.legistar.com/), but its
  [terms](https://cityofracinewi.gov/termsofuse/) prohibit systematic automated
  collection and republishing content in software. No record API was queried.
  Clarify whether an approved public API/export permits this project’s reuse.
- Eau Claire's [official meeting page](https://www.eauclairewi.gov/723/Public-Notices-Meetings)
  and [AgendaCenter](https://www.eauclairewi.gov/AgendaCenter) require a separate
  record-format review and support for district and at-large members.

These links are research leads, not collection approvals. None of these
additional hosts or tenants is added to the runtime allowlist.

## Appleton and Waukesha: shared collection

Reviewed September 8, 2026. [Appleton's council page](https://appletonwi.gov/government/common_council.php)
links directly to its Legistar calendar. [Waukesha's city site](https://www.waukesha-wi.gov/)
links to its Legistar calendar, and the [official council roster](https://www.waukesha-wi.gov/about_the_common_council/index.php)
lists its 15 districts. The returned API meeting links match these official
portals. No separate website reuse restriction was found in the reviewed city
pages and their policy links. Retrieval uses the documented
[public API](https://webapi.legistar.com/Home/Examples) and ordinary public InSite pagination.

| City | API tenant / body | Settled minutes | First bounded batch |
| --- | --- | --- | --- |
| Appleton | `cityofappleton` / `138`, `Common Council` | `Final` | September 2, 2026 (`6462`), then newest uncached meeting |
| Waukesha | `waukesha` / `138`, `City Council` | `Final` | August 18, 2026 (`13087`), then newest uncached meeting |

[Appleton InSite robots](https://cityofappleton.legistar.com/robots.txt),
[Waukesha InSite robots](https://waukesha.legistar.com/robots.txt), and the
[shared API robots](https://webapi.legistar.com/robots.txt) returned 404.
Only the same reviewed API routes and InSite `Departments.aspx` / `MeetingDetail.aspx`
GET/POST pagination used by Madison are enabled. Keep the one-second per-host
floor, identifying agent, caching, and stop-on-denial protections. City websites,
portraits, attachments and video downloads are excluded from this addition.
Appleton's city robots redirected to its CMS and were not followed; Waukesha's
city robots returned 404. Neither city website is a runtime collection target.

Both cities leave district numbers out of their office titles and person URLs.
The existing `local_seats.json` holds all 30 verified district-to-person-ID
mappings, each with its official roster URL and review date. The shared importer
uses `(tenant, person_id)`; names never determine a vote or seat join. A new
unverified alderperson still fails the missing-seat integrity gate. Recheck
curation after elections or appointments. Appleton labels its mayor as `Member`;
only a proven active `Mayor` term exempts that person from needing a district.
Waukesha's council office records omit the mayor; no membership is invented.

The complete returned vote rows in four reviewed meetings were retained:

| City / meeting | Acted items | Individual vote rows | Recorded attendance rows |
| --- | ---: | ---: | ---: |
| Appleton September 2, 2026 | 28 | 430 | 16 |
| Appleton August 19, 2026 | 19 | 273 | 16 |
| Waukesha September 1, 2026 (draft) | 7 | 105 | 15 |
| Waukesha August 18, 2026 | 11 | 135 | 30 |

All four contain individual dissent. Three acted items have no individual vote
rows; those remain actions without inferred member votes. `Nay` counts as a
negative vote alongside `No` in shared site totals and dissent checks, while
SQLite, individual rows, feeds and JSON preserve the original wording. Unknown
positions must still match that tenant's published vocabulary.

Offline comparison preserved all 500,757 Milwaukee/West Allis vote rows and
the earlier Madison fixture across all ten local tables. All 943 new sampled
votes matched their source item IDs, person IDs and values exactly; both city
rosters resolved all 15 districts. The comparison changed no source files and
passed local integrity checks. Validation also passed 525 Python tests (one
existing skip), 44 site harness tests, Ruff, Astro checks, and mobile/desktop
coverage-notice checks with zero accessibility violations.

Initial coverage starts in 2025. The reviewed indexes list 47 past Appleton
meetings and 50 Waukesha meetings; only two per city were downloaded for this
review. Nightly backfill uses the same atomic cache, pending-history metadata,
draft refresh and import rollback behavior described above. Maps and address
lookup await a separate boundary review. There are no per-city runtime modules.

## Validate in dev

After merge, let the current nightly run finish. Run the nightly workflow with
`policy_only=true`, then start a fresh run with `policy_only=false` and an empty
`resume_run`. Once its validated snapshot is published, run the dev release
workflow from `main`; releases follow [the deployment runbook](../deploys.md).
The website build alone does not collect the new cities.

Check `/local/appleton/` and `/local/waukesha/`, their 15 district members, and
their council/member JSON links. Confirm that source links open the matching
meeting, Nay rows remain Nay, dissent totals agree,
and pending-history notices remain until backfill finishes. Compare individual
votes to the clerk's records, including a dissenting motion and a voice vote.

For an isolated local preview, start from the repository root in PowerShell.
Use a fresh destination and run collection only when no other scrape is active:

```powershell
if (Test-Path .private/city-dev) { throw "Use a fresh dev directory." }
New-Item -ItemType Directory .private/city-dev
Copy-Item -LiteralPath pipeline/_data/local -Destination .private/city-dev/local -Recurse
Copy-Item -LiteralPath data/wi.sqlite -Destination .private/city-dev/wi.sqlite
Set-Location pipeline
uv run python -m scraper.fetch_local_votes --tenant madison --tenant cityofappleton --tenant waukesha --data-dir ../.private/city-dev/local
if ($LASTEXITCODE -ne 0) { throw "Collection failed; stop here." }
uv run python -m importer.import_local ../.private/city-dev/local ../.private/city-dev/wi.sqlite
if ($LASTEXITCODE -ne 0) { throw "Import failed; stop here." }
uv run python -m importer.checks ../.private/city-dev/wi.sqlite
if ($LASTEXITCODE -ne 0) { throw "Integrity checks failed; stop here." }
Set-Location ../site
$env:WI_DATABASE_PATH = (Resolve-Path ../.private/city-dev/wi.sqlite).Path
npm run dev
```

Stop on any failed command. Keep the full existing municipal archive in that
copy: the importer replaces all local tables in one transaction. `--tenant`
selects collection only, and the per-city batch limits still apply. Do not use
private research samples as deployment archives; some contain partial meetings.
The normal database path remains `data/wi.sqlite` when `WI_DATABASE_PATH` is unset.

## Full population order

<details>
<summary>All 190 incorporated cities (July 1, 2025)</summary>

| Rank | City | Population | Place FIPS |
| --- | --- | ---: | --- |
| 1 | Milwaukee | 562,407 | 5553000 |
| 2 | Madison | 286,233 | 5548000 |
| 3 | Green Bay | 106,675 | 5531000 |
| 4 | Kenosha | 99,239 | 5539225 |
| 5 | Racine | 77,908 | 5566000 |
| 6 | Appleton | 75,452 | 5502375 |
| 7 | Eau Claire | 72,465 | 5522300 |
| 8 | Waukesha | 70,872 | 5584250 |
| 9 | Oshkosh | 67,460 | 5560500 |
| 10 | Janesville | 66,929 | 5537825 |
| 11 | West Allis | 60,119 | 5585300 |
| 12 | La Crosse | 50,784 | 5540775 |
| 13 | Sheboygan | 49,376 | 5572975 |
| 14 | Wauwatosa | 48,649 | 5584675 |
| 15 | Fond du Lac | 44,541 | 5526275 |
| 16 | Brookfield | 41,448 | 5510025 |
| 17 | Wausau | 40,188 | 5584475 |
| 18 | New Berlin | 39,953 | 5556375 |
| 19 | Sun Prairie | 39,227 | 5578600 |
| 20 | Oak Creek | 38,296 | 5558800 |
| 21 | Greenfield | 37,159 | 5531175 |
| 22 | Franklin | 36,687 | 5527300 |
| 23 | Beloit | 36,649 | 5506500 |
| 24 | Manitowoc | 34,671 | 5548500 |
| 25 | Fitchburg | 34,615 | 5525950 |
| 26 | West Bend | 32,268 | 5585350 |
| 27 | Neenah | 27,638 | 5555750 |
| 28 | Superior | 26,397 | 5578650 |
| 29 | Stevens Point | 26,377 | 5577200 |
| 30 | Muskego | 25,602 | 5555275 |
| 31 | De Pere | 25,590 | 5519775 |
| 32 | Mequon | 25,120 | 5551150 |
| 33 | Middleton | 23,115 | 5551575 |
| 34 | Watertown | 22,704 | 5583975 |
| 35 | Onalaska | 20,297 | 5559925 |
| 36 | South Milwaukee | 20,191 | 5575125 |
| 37 | Oconomowoc | 20,119 | 5559250 |
| 38 | Marshfield | 18,980 | 5549675 |
| 39 | Wisconsin Rapids | 18,654 | 5588200 |
| 40 | Kaukauna | 18,517 | 5538800 |
| 41 | Menasha | 18,385 | 5550825 |
| 42 | River Falls | 17,916 | 5568275 |
| 43 | Cudahy | 17,655 | 5517975 |
| 44 | Verona | 16,821 | 5582600 |
| 45 | Menomonie | 16,664 | 5551025 |
| 46 | Beaver Dam | 16,542 | 5505900 |
| 47 | Pewaukee | 16,375 | 5562240 |
| 48 | Whitewater | 16,038 | 5586925 |
| 49 | Hartford | 16,005 | 5533000 |
| 50 | Chippewa Falls | 15,293 | 5514575 |
| 51 | Hudson | 15,019 | 5536250 |
| 52 | Glendale | 14,795 | 5529400 |
| 53 | Stoughton | 13,256 | 5577675 |
| 54 | Baraboo | 13,224 | 5504625 |
| 55 | Cedarburg | 12,916 | 5513375 |
| 56 | Port Washington | 12,658 | 5564450 |
| 57 | Fort Atkinson | 12,388 | 5526675 |
| 58 | Platteville | 11,815 | 5563250 |
| 59 | Two Rivers | 11,222 | 5581325 |
| 60 | Marinette | 11,168 | 5549300 |
| 61 | Waupun | 11,150 | 5584425 |
| 62 | New Richmond | 10,988 | 5557100 |
| 63 | Burlington | 10,951 | 5511200 |
| 64 | Reedsburg | 10,641 | 5566800 |
| 65 | Monroe | 10,581 | 5553750 |
| 66 | Elkhorn | 10,045 | 5523300 |
| 67 | Sparta | 9,974 | 5575325 |
| 68 | Portage | 9,956 | 5564100 |
| 69 | Sturgeon Bay | 9,917 | 5577875 |
| 70 | Shawano | 9,693 | 5572925 |
| 71 | Tomah | 9,600 | 5580075 |
| 72 | Merrill | 9,389 | 5551250 |
| 73 | Altoona | 9,376 | 5501550 |
| 74 | Delavan | 9,228 | 5519450 |
| 75 | St. Francis | 8,955 | 5570650 |
| 76 | Rice Lake | 8,882 | 5567350 |
| 77 | Plymouth | 8,821 | 5563700 |
| 78 | Lake Geneva | 8,818 | 5541450 |
| 79 | Sheboygan Falls | 8,687 | 5573025 |
| 80 | Monona | 8,664 | 5553675 |
| 81 | Rhinelander | 8,242 | 5567200 |
| 82 | Antigo | 8,060 | 5502250 |
| 83 | Ashland | 7,927 | 5503225 |
| 84 | Jefferson | 7,814 | 5537900 |
| 85 | Ripon | 7,738 | 5568175 |
| 86 | New London | 7,726 | 5556925 |
| 87 | Delafield | 7,314 | 5519400 |
| 88 | Lake Mills | 6,655 | 5541675 |
| 89 | Waupaca | 6,352 | 5584375 |
| 90 | Edgerton | 6,121 | 5522575 |
| 91 | Milton | 6,024 | 5552200 |
| 92 | Evansville | 5,837 | 5524550 |
| 93 | Berlin | 5,588 | 5506925 |
| 94 | Prairie du Chien | 5,408 | 5565050 |
| 95 | Columbus | 5,400 | 5516450 |
| 96 | Mayville | 5,184 | 5550200 |
| 97 | Dodgeville | 5,076 | 5520350 |
| 98 | Richland Center | 5,020 | 5567625 |
| 99 | Oconto | 4,640 | 5559350 |
| 100 | Medford | 4,589 | 5550425 |
| 101 | Prescott | 4,581 | 5565375 |
| 102 | Mosinee | 4,529 | 5554500 |
| 103 | Clintonville | 4,499 | 5515725 |
| 104 | Viroqua | 4,435 | 5582925 |
| 105 | Chilton | 4,183 | 5514475 |
| 106 | Mauston | 4,133 | 5550025 |
| 107 | Lancaster | 4,031 | 5542250 |
| 108 | Kiel | 3,973 | 5539525 |
| 109 | Horicon | 3,917 | 5535750 |
| 110 | Stanley | 3,876 | 5576625 |
| 111 | Arcadia | 3,840 | 5502500 |
| 112 | Omro | 3,639 | 5559875 |
| 113 | Barron | 3,634 | 5504875 |
| 114 | Bloomer | 3,634 | 5508225 |
| 115 | Seymour | 3,628 | 5572725 |
| 116 | Waterloo | 3,600 | 5583925 |
| 117 | Black River Falls | 3,555 | 5507900 |
| 118 | Peshtigo | 3,423 | 5562175 |
| 119 | Tomahawk | 3,387 | 5580125 |
| 120 | Brillion | 3,327 | 5509725 |
| 121 | Boscobel | 3,250 | 5508850 |
| 122 | Algoma | 3,225 | 5501000 |
| 123 | Brodhead | 3,214 | 5509925 |
| 124 | Lodi | 3,190 | 5545350 |
| 125 | Ladysmith | 3,172 | 5540850 |
| 126 | Wisconsin Dells | 3,149 | 5588150 |
| 127 | New Holstein | 3,040 | 5556800 |
| 128 | Oconto Falls | 3,012 | 5559400 |
| 129 | Amery | 2,927 | 5501725 |
| 130 | Mondovi | 2,853 | 5553600 |
| 131 | Kewaunee | 2,793 | 5539350 |
| 132 | Fennimore | 2,775 | 5525600 |
| 133 | Juneau | 2,706 | 5538675 |
| 134 | Hayward | 2,614 | 5533450 |
| 135 | New Lisbon | 2,577 | 5556900 |
| 136 | Mineral Point | 2,555 | 5553100 |
| 137 | Spooner | 2,531 | 5575625 |
| 138 | Darlington | 2,490 | 5518875 |
| 139 | Westby | 2,435 | 5585475 |
| 140 | Abbotsford | 2,413 | 5500100 |
| 141 | Wautoma | 2,411 | 5584625 |
| 142 | Nekoosa | 2,402 | 5555875 |
| 143 | St. Croix Falls | 2,370 | 5570550 |
| 144 | Neillsville | 2,367 | 5555800 |
| 145 | Park Falls | 2,359 | 5561200 |
| 146 | Schofield | 2,311 | 5572150 |
| 147 | Cumberland | 2,282 | 5518025 |
| 148 | Chetek | 2,152 | 5514325 |
| 149 | Cuba City | 2,103 | 5517950 |
| 150 | Washburn | 2,045 | 5583525 |
| 151 | Colby | 1,957 | 5516150 |
| 152 | Durand | 1,854 | 5521225 |
| 153 | Osseo | 1,842 | 5560575 |
| 154 | Adams | 1,803 | 5500275 |
| 155 | Weyauwega | 1,788 | 5586400 |
| 156 | Thorp | 1,781 | 5579625 |
| 157 | Crandon | 1,726 | 5517425 |
| 158 | Eagle River | 1,715 | 5521625 |
| 159 | Galesville | 1,704 | 5528200 |
| 160 | Fox Lake | 1,686 | 5527000 |
| 161 | Whitehall | 1,621 | 5586725 |
| 162 | Hurley | 1,617 | 5536525 |
| 163 | Niagara | 1,577 | 5557325 |
| 164 | Phillips | 1,492 | 5562450 |
| 165 | Independence | 1,487 | 5536800 |
| 166 | Augusta | 1,483 | 5503825 |
| 167 | Montello | 1,447 | 5553875 |
| 168 | Cornell | 1,443 | 5517100 |
| 169 | Shell Lake | 1,414 | 5573200 |
| 170 | Manawa | 1,411 | 5548350 |
| 171 | Hillsboro | 1,401 | 5534825 |
| 172 | Markesan | 1,380 | 5549450 |
| 173 | Blair | 1,292 | 5508075 |
| 174 | Gillett | 1,276 | 5529050 |
| 175 | Marion | 1,273 | 5549400 |
| 176 | Elroy | 1,255 | 5523800 |
| 177 | Glenwood City | 1,254 | 5529625 |
| 178 | Princeton | 1,249 | 5565600 |
| 179 | Shullsburg | 1,240 | 5573825 |
| 180 | Loyal | 1,190 | 5546075 |
| 181 | Greenwood | 1,079 | 5531575 |
| 182 | Green Lake | 1,040 | 5531300 |
| 183 | Buffalo City | 1,009 | 5511062 |
| 184 | Owen | 904 | 5560825 |
| 185 | Pittsville | 820 | 5563100 |
| 186 | Fountain City | 769 | 5526850 |
| 187 | Montreal | 769 | 5554075 |
| 188 | Alma | 718 | 5501225 |
| 189 | Mellen | 683 | 5550700 |
| 190 | Bayfield | 589 | 5505350 |

</details>
