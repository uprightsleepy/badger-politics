# scraper/

Thin wrappers around external data sources. openstates-scrapers (GPL-3.0)
is pinned as a submodule and only ever invoked via its CLI (`os-update`);
its modules are never imported and its code never copied in-tree. Runtime
patches live in `pipeline/patches/` (see its README for upstream intent)
and are applied by `scrape.py` before every run.

## Source policy review (2026-09-07)

Use `http.session()` for every network request, including enrichment and one-off
data tools. The upstream Wisconsin CLI receives the same transport through
`0003-wi-source-access.patch`. No browser impersonation, disabled TLS checks,
unreviewed redirects, or unthrottled fast mode is permitted.

`source_policies.json` limits hosts, paths, methods, and request intervals. Before
fetching records, the transport checks live robots.txt against the reviewed
response. New directives, changed status/redirects, unavailable policies, and
unreviewed URLs stop collection. Successful reviews are cached in memory for at
most one hour, never across runs. HTTP 401/403/429, exhausted API limits, and
Retry-After stop the source for the rest of the process; wait until the published
reset before restarting. GET gateway failures have three paced retries. POSTs
are limited to the read-only Legistar pagination forms and are never retried.

This is a scoped access review, not a blanket reuse license. Check the linked
terms again before changing retrieval or reuse, and periodically during operation.
Do not automatically accept a changed fingerprint. Record the new date, policy
URLs, permitted paths and rates after review. Keep raw policy captures private.
No new paid service or dependency is required.

| Source / collector | Robots result and current decision | Terms / permitted scope |
| --- | --- | --- |
| Wisconsin Legislature (`scrape`, contacts, subjects, session rosters, enrichers) | [docs robots](https://docs.legis.wisconsin.gov/robots.txt) restrict internal mechanisms and search-result routes; only reviewed year/document routes and `/search` are enabled. [Schedule robots](https://committeeschedule.legis.wisconsin.gov/robots.txt) returns 404. Minimum 1 second/request. | Reviewed [Legislature](https://legis.wisconsin.gov/) and [records site](https://docs.legis.wisconsin.gov/); no separate public-site terms link or conflicting collection restriction found. Official legislative records and office contacts only; retain attribution. |
| CFIS (`fetch_cfis`, `fetch_cf_committees`) | [Robots](https://campaignfinance.wi.gov/robots.txt) leaves the three used JSON procedures open to general crawlers; named AI agents are blocked. Both general groups were reviewed. Conservative 10-second interval because a crawl-delay directive has ambiguous placement. | [Official public search](https://ethics.wi.gov/Pages/CampaignFinance/ViewReports.aspx), [Commission reuse notice, pp. 8–9](https://ethics.wi.gov/Resources/20251021%20Open%20Session%20Materials%20Revised.pdf): noncommercial civic reporting only; no sale, commercial use, solicitations, or AI training. Preserve `alwaysRespectPiiRedaction`. This is the public frontend's JSON interface, not a documented API service guarantee. Do not use an AI browsing agent to collect its records or change identities to avoid restrictions. |
| WEC ballot and canvass files | [Robots](https://elections.wi.gov/robots.txt) permits the report paths, but the homepage returned 403 during the terms recheck. New downloads are paused; existing local reports remain usable. | Terms review could not be completed. Clarify current access/reuse rules before restoring downloads; never work around a denial. |
| OpenStates people/committees; congressional roster | Robots returned 404 on [api.github.com](https://api.github.com/robots.txt), [raw.githubusercontent.com](https://raw.githubusercontent.com/robots.txt), and [unitedstates.github.io](https://unitedstates.github.io/robots.txt). Only the specific roster repositories/paths are enabled, minimum 1 second/request. | [GitHub API terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#h-api-terms), [rate handling](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#handle-rate-limit-errors-appropriately), [people license](https://github.com/openstates/people/blob/main/LICENSE), [congress roster dedication](https://github.com/unitedstates/congress-legislators#public-domain). CC0/public-domain roster data; no unrelated GitHub user data. |
| Federal roll calls | [House robots](https://clerk.house.gov/robots.txt) returns 404. [Senate robots](https://www.senate.gov/robots.txt) redirects to its specific `file_not_found.htm` page; this known missing response is recorded explicitly, not interpreted as an allow-all file. XML paths only, minimum 1 second/request. | [House rights/reproductions](https://clerk.house.gov/PrivacyPolicy), [Senate XML publication](https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_119_2.htm), [Senate privacy policy](https://www.senate.gov/general/privacy.htm). Attribute factual voting records; no photos, broadcast footage, endorsements, or campaign advertising. |
| Milwaukee / West Allis council records | Robots returns 404 on [Web API](https://webapi.legistar.com/robots.txt), [Milwaukee InSite](https://milwaukee.legistar.com/robots.txt), [West Allis InSite](https://westalliswi.legistar.com/robots.txt). Reviewed public tenant API and meeting/department pagination only, minimum 1 second/request. | [Published API](https://webapi.legistar.com/Help), [Milwaukee policies](https://city.milwaukee.gov/Information-and-Services/webpolicies). Public meeting/vote facts and source links; no login, unpublished tenants, video or attachments collection. |
| Council profile pages | [Milwaukee robots](https://city.milwaukee.gov/robots.txt) allows district pages but disallows print queries; [West Allis robots](https://www.westalliswi.gov/robots.txt) disallows `/api/`. District HTML only, minimum 1 second/request. | [Milwaukee disclaimer](https://city.milwaukee.gov/Information-and-Services/webpolicies/DisclaimerofLiabilit), [privacy](https://city.milwaukee.gov/Information-and-Services/webpolicies/Privacy), [West Allis site](https://www.westalliswi.gov/). No separate West Allis terms link found. Capture official office-contact facts and portrait URLs; this collector does not download image files. |
| Eye on Lobbying | [Robots](https://lobbying.wi.gov/robots.txt) disallows all crawling. Automated retrieval **removed**; CLI fails without network requests. | May be restored later with **site approval** and a fresh policy review. [Official records access](https://ethics.wi.gov/Pages/AboutUs/PublicRecordsNotice.aspx) offers a route to request an approved extract. |
| WisconsinEye | [Robots](https://wiseye.org/robots.txt) permits crawling with a 10-second delay, but retrieval is **paused**. | [User agreement](https://wiseye.org/user-agreement/), especially sections 1 and 14, leaves metadata republication uncertain. Obtain approval/clarification before restoring retrieval. Existing local metadata can still match archived hearing links. |
| FollowTheMoney | [API robots](https://api.followthemoney.org/robots.txt) disallows all crawling. Network requests are **paused**; cached research remains available. | Previously documented API-key/license access does not resolve the current robots conflict. Obtain explicit approval covering automated API use before restoring either research helper. |
| Boundary utilities | [LTSB ArcGIS host](https://services1.arcgis.com/robots.txt) returned 403; [Milwaukee maps](https://milwaukeemaps.milwaukee.gov/robots.txt) disallows general crawlers. New requests are **paused**; committed boundaries/local caches remain. | [Milwaukee open data](https://data.milwaukee.gov/) resource files may be an alternative, but `/api/` is robots-disallowed. No active downloader exists for that host or West Allis GIS; review individual dataset terms before adding one. |
| Organization logos | `fetch-logos.mjs` now performs **no network requests**. Existing assets/monogram fallback remain. | The former homepage checks lacked individual robots/terms reviews. The logo.dev terms recheck could not be completed (429). Review provider API/caching/attribution terms and each identity-verification source before restoring. |

## Preserving lobbying data offline

`run.sh` no longer fetches lobbying pages. It still imports the complete existing
`_data/lobbying/interests-*.json` archive after rebuilding the database, so this
change does not discard collected registrations. The site labels them archived.
`fetch_lobbying.parse_principals()` remains a network-free parser for locally
saved HTML; it is not a complete manual-upload workflow.

Do not replace the full archive with a one-page download: `import_lobbying`
rebuilds the entire table. Keep original HTML, session, official source URL and
download date outside public Git. Validate and merge partial approved updates
into the existing archive before running an import. Archive importers fail on
missing input rather than silently substituting empty data.
