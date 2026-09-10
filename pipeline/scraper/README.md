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

`source_policies.json` limits hosts, paths, methods, and request intervals. The
nightly parser uses the daily policy job's matching checks for up to 24 hours.
Local commands without `SOURCE_POLICY_REPORT` check live robots.txt and cache
successful checks in memory for one hour. New directives, changed responses,
unavailable policies, and unreviewed URLs stop collection.
HTTP 401/403/429, exhausted API limits, and nonzero or unrecognized Retry-After
values stop the source for the rest of the process; wait until the published
reset before restarting. A successful 2xx response with a valid zero-second
Retry-After keeps normal source pacing. GET gateway failures have three paced
retries. POSTs are limited to read-only Legistar pagination and are never retried.

This is a scoped access review, not a blanket reuse license. Check the linked
terms again before changing retrieval or reuse, and periodically during operation.
Do not automatically accept a changed fingerprint. Record the new date, policy
URLs, permitted paths and rates after review. Keep raw policy captures private.
No new paid service or dependency is required.

## Shared daily checks (2026-09-08)

Madison council collection was reviewed on September 8, 2026: documented public
Legistar API GETs and public InSite meeting/department pagination, minimum one
second per request, with robots returning 404 on both hosts. City terms allow
public-information reuse subject to protected content; portraits and logos are
excluded. Its bounded history starts in 2025. See the complete
[policy evidence, ranked city queue and rollout](../../docs/research/wisconsin-city-expansion-2026-09.md).

Appleton and Waukesha received the same scoped review on September 8. Their
official city sites link to the verified public Legistar tenants; API and
InSite robots return 404. Only documented API GETs and ordinary meeting/department
pagination are enabled, with the existing one-second per-host floor and denial
protections. Each city adds at most two uncached meetings per run from 2025.
District identities use the shared curated roster; no city-page or portrait
collector is added. The linked review records policy URLs, samples and dev steps.
Green Bay uses the shared CivicClerk adapter from July 1, 2026. Its public OData
schema documents the event and meeting records used by the portal. Collection
is limited to two meeting downloads per run, with a five-second request floor.
Native revisions remain in the private archive; missing names or removed votes
stop replacement. Published records are checked again after seven days or when
event metadata changes. The current roster refreshes each run without inventing
term dates. See the [API schema](https://greenbaywi.api.civicclerk.com/v1/$metadata),
[official roster](https://www.greenbaywi.gov/617/Common-Council), and
[CivicPlus terms](https://www.civicplus.help/legal-center/docs/civicplus-terms-of-use).
The API robots file returns 404; the roster path is permitted by the city's
reviewed robots file. Only `/v1/Events`, `/v1/Meetings/{id}` and the roster page
are enabled. No authentication, staff endpoints, attachments or video collection.

Green Bay portrait support was reviewed September 9, 2026 against the same
[robots file](https://www.greenbaywi.gov/robots.txt), roster, CivicPlus terms,
[city copyright notice](https://www.greenbaywi.gov/site/copyright), and
[privacy page](https://www.greenbaywi.gov/privacy). The existing roster request
also captures same-origin portrait URLs whose alt text uniquely matches the
member's full name. The importer checks the name, district and source again.
No image files are downloaded or copied, and request scopes and the five-second
floor are unchanged. Native roster revisions retain the attribution evidence.
Older snapshots remain usable without portraits; the next roster refresh adds them.

Appleton and Waukesha portrait rosters were also reviewed September 9, 2026:
[Appleton council](https://appletonwi.gov/government/common_council.php) and
[Waukesha council](https://www.waukesha-wi.gov/about_the_common_council/index.php).
Each named district card supplies its own image; imports require both the full
name and district to match the current member. Two roster requests per run add
about ten seconds at the five-second floor. No image files are downloaded.
Neither roster/footer published a separate scraping or image-use restriction.
[Waukesha robots](https://www.waukesha-wi.gov/robots.txt) returns 404.
[Appleton robots](https://appletonwi.gov/robots.txt) redirects to the exact
[Revize policy URL](https://cms2.revize.com/revize/appletonwi/robots.txt), which
returns 404. Only that reviewed cross-origin policy redirect is allowed;
changed URLs/statuses and access denials still stop collection. No CMS record
routes are enabled. These new hosts require a fresh daily policy report.

Madison's [robots](https://www.cityofmadison.com/robots.txt) permits `/council`,
but its [Conditions & Use](https://www.cityofmadison.com/policy/conditions)
explicitly requires permission to reuse images. Its
[data policy](https://www.cityofmadison.com/policy/data) grants no image rights.
Madison portraits remain uncollected, with official roster and policy links on
the site. Its separately reviewed legislative records continue normally.

Racine's API metadata and 15 current
district identities are verified, with mappings prepared in `local_seats.json`;
its `Events` endpoint returns HTTP 400 for missing agenda-visibility settings.
Working meeting retrieval and vote validation are required before activation.
Affirmative permission is not a prerequisite where no applicable explicit
restriction prohibits collection.
Kenosha's Granicus host explicitly disallows our crawler. See the
[city access review](../../docs/research/municipal-access-routes-2026-09.md).
Racine and Kenosha remain disabled.

Review restrictions against the actual host, paths and intended use. Missing
policies or silence about scraping do not require an operator's approval. Record
explicit prohibitions separately from technical denials, failed policy checks,
and unverified formats. A website restriction does not automatically cover a
separate public API. Officially documented public APIs need no separate permission
request; follow their documented scope, authentication requirements and limits.
Runtime source scopes, denial protections and pacing still apply.

The policy-only job checks each active host once using the existing transport;
paused sources stay paused. It compares the complete normalized robots response
with the reviewed fingerprint, including comments. Terms and reuse still need
human review against the source links below; this job does not approve new rules.
The 24-hour limit follows [RFC 9309 caching guidance](https://www.rfc-editor.org/rfc/rfc9309.html#section-2.4).
The cache changes no permitted paths, methods, identifying User-Agent, or rates.

Reports include the policy configuration hash, check times, and per-host results.
They stay in the private checkpoint prefix. Every attempt writes a pending report
before source requests and a final report afterward. Readers choose the newest
attempt, including failures, so an interrupted or denied check cannot expose an
older approval. Configuration changes, missing/malformed reports, and checks
older than 24 hours stop the parser before collection.

Parser jobs restore the report to `.private/policies/report.json` and pass its
absolute path through `SOURCE_POLICY_REPORT`, including to the upstream CLI.
Configured reports are mandatory; there is no automatic live-check fallback.
Expiry is checked before every record request, including after pacing waits.
The first request in each collector still observes the source interval, and
live access denials, retry delays, and exhausted rate limits still stop the source.
See [scheduling and activation](../../docs/nightly-parser-hosting.md#daily-policy-job).

| Source / collector | Robots result and current decision | Terms / permitted scope |
| --- | --- | --- |
| Wisconsin Legislature (`scrape`, contacts, subjects, session rosters, enrichers) | [docs robots](https://docs.legis.wisconsin.gov/robots.txt) restrict internal mechanisms and search-result routes; only reviewed year/document routes and `/search` are enabled. [Schedule robots](https://committeeschedule.legis.wisconsin.gov/robots.txt) returns 404. Minimum 1 second/request. | Reviewed [Legislature](https://legis.wisconsin.gov/) and [records site](https://docs.legis.wisconsin.gov/); no separate public-site terms link or conflicting collection restriction found. Official legislative records and office contacts only; retain attribution. |
| CFIS (`fetch_cfis`, `fetch_cf_committees`) | [Robots](https://campaignfinance.wi.gov/robots.txt) leaves the three used JSON procedures open to general crawlers; named AI agents are blocked. Both general groups were reviewed. Conservative 10-second interval because a crawl-delay directive has ambiguous placement. | [Official public search](https://ethics.wi.gov/Pages/CampaignFinance/ViewReports.aspx), [Commission reuse notice, pp. 8–9](https://ethics.wi.gov/Resources/20251021%20Open%20Session%20Materials%20Revised.pdf): noncommercial civic reporting only; no sale, commercial use, solicitations, or AI training. Preserve `alwaysRespectPiiRedaction`. This is the public frontend's JSON interface, not a documented API service guarantee. Do not use an AI browsing agent to collect its records or change identities to avoid restrictions. |
| WEC ballot and canvass files | [Robots](https://elections.wi.gov/robots.txt) permits the report paths, but the homepage returned 403 during the terms recheck. New downloads are paused; existing local reports remain usable. | Terms review could not be completed. Clarify current access/reuse rules before restoring downloads; never work around a denial. |
| OpenStates people/committees; congressional roster | Robots returned 404 on [api.github.com](https://api.github.com/robots.txt), [raw.githubusercontent.com](https://raw.githubusercontent.com/robots.txt), and [unitedstates.github.io](https://unitedstates.github.io/robots.txt). Only the specific roster repositories/paths are enabled, minimum 1 second/request. | [GitHub API terms](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service#h-api-terms), [rate handling](https://docs.github.com/en/rest/using-the-rest-api/best-practices-for-using-the-rest-api#handle-rate-limit-errors-appropriately), [people license](https://github.com/openstates/people/blob/main/LICENSE), [congress roster dedication](https://github.com/unitedstates/congress-legislators#public-domain). CC0/public-domain roster data; no unrelated GitHub user data. |
| Federal roll calls | [House robots](https://clerk.house.gov/robots.txt) returns 404. [Senate robots](https://www.senate.gov/robots.txt) redirects to its specific `file_not_found.htm` page; this known missing response is recorded explicitly, not interpreted as an allow-all file. XML paths only, minimum 1 second/request. | [House rights/reproductions](https://clerk.house.gov/PrivacyPolicy), [Senate XML publication](https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_119_2.htm), [Senate privacy policy](https://www.senate.gov/general/privacy.htm). Attribute factual voting records; no photos, broadcast footage, endorsements, or campaign advertising. |
| Milwaukee / West Allis council records | Robots returns 404 on [Web API](https://webapi.legistar.com/robots.txt), [Milwaukee InSite](https://milwaukee.legistar.com/robots.txt), [West Allis InSite](https://westalliswi.legistar.com/robots.txt). Reviewed public tenant API and meeting/department pagination only, minimum 1 second/request. | [Published API](https://webapi.legistar.com/Help), [Milwaukee policies](https://city.milwaukee.gov/Information-and-Services/webpolicies). Public meeting/vote facts and source links; no login, unpublished tenants, video or attachments collection. |
| Council profile pages | [Milwaukee robots](https://city.milwaukee.gov/robots.txt) returned HTTP 403 from the nightly runner on September 8; retrieval is **paused**, retaining the complete existing profile archive. [West Allis robots](https://www.westalliswi.gov/robots.txt) disallows `/api/`; reviewed district HTML remains enabled, minimum 1 second/request. | [Milwaukee disclaimer](https://city.milwaukee.gov/Information-and-Services/webpolicies/DisclaimerofLiabilit), [privacy](https://city.milwaukee.gov/Information-and-Services/webpolicies/Privacy), [West Allis site](https://www.westalliswi.gov/). No separate West Allis terms link found. Capture official office-contact facts and portrait URLs; this collector does not download image files. |
| Eye on Lobbying | [Robots](https://lobbying.wi.gov/robots.txt) disallows all crawling. Automated retrieval **removed**; CLI fails without network requests. | May be restored later with **site approval** and a fresh policy review. [Official records access](https://ethics.wi.gov/Pages/AboutUs/PublicRecordsNotice.aspx) offers a route to request an approved extract. |
| WisconsinEye | [Robots](https://wiseye.org/robots.txt) permits crawling with a 10-second delay, but retrieval is **paused**. | [User agreement](https://wiseye.org/user-agreement/), especially sections 1 and 14, leaves metadata republication uncertain. Obtain approval/clarification before restoring retrieval. Existing local metadata can still match archived hearing links. |
| FollowTheMoney | [API robots](https://api.followthemoney.org/robots.txt) disallows all crawling. Network requests are **paused**; cached research remains available. | Previously documented API-key/license access does not resolve the current robots conflict. Obtain explicit approval covering automated API use before restoring either research helper. |
| Boundary utilities | [LTSB ArcGIS host](https://services1.arcgis.com/robots.txt) returned 403; [Milwaukee maps](https://milwaukeemaps.milwaukee.gov/robots.txt) disallows general crawlers. New requests are **paused**; committed boundaries/local caches remain. | [Milwaukee open data](https://data.milwaukee.gov/) resource files may be an alternative, but `/api/` is robots-disallowed. No active downloader exists for that host or West Allis GIS; review individual dataset terms before adding one. |
| Organization logos | `fetch-logos.mjs` now performs **no network requests**. Existing assets/monogram fallback remain. | The former homepage checks lacked individual robots/terms reviews. The logo.dev terms recheck could not be completed (429). Review provider API/caching/attribution terms and each identity-verification source before restoring. |

## Robots transport recovery (2026-09-08)

The nightly community stage stopped on a Legislature robots connection timeout,
then on an unexpected Milwaukee robots response. A fresh check of
[Milwaukee robots](https://city.milwaukee.gov/robots.txt), using the pipeline's
identifying User-Agent, returned HTTP 200 and the existing reviewed fingerprint.
The [disclaimer](https://city.milwaukee.gov/Information-and-Services/webpolicies/DisclaimerofLiabilit)
and [privacy policy](https://city.milwaukee.gov/Information-and-Services/webpolicies/Privacy)
were rechecked; the existing district-page scope and exclusions remain unchanged.
The failed runner did not record its response status, so the cause of that
unexpected response remains unconfirmed. Raw diagnostics stay private.

Robots checks retry only connection/timeouts and HTTP 502/503/504, up to three
times with 30/60/120-second waits (or the source's interval if longer). No record
request is sent until the live response passes the existing policy checks.
TLS failures, 401/403/429, nonzero or unrecognized Retry-After, exhausted limits,
changed fingerprints, and unexpected redirects still stop collection. Same-origin robots redirects
respect the source interval. Failure messages include the status received and
expected, or the transport error type and number of attempts.

## Milwaukee profile pause (2026-09-08)

A later nightly retry reached Milwaukee robots.txt and recorded HTTP 403 before
requesting any district page. Collection from `city.milwaukee.gov` is now paused
in `source_policies.json`; clarify access and review the policies linked above
before restoring it. A successful check from another machine does not override
the runner's denial. West Allis profile retrieval and both councils' separately
reviewed Legistar records remain enabled at their existing rates.

The profile collector requires all 15 archived Milwaukee districts and preserves
their records unchanged. Before the first retained import, it binds them to the
member IDs in the archived roster; subsequent runs keep those bindings. Run
profiles before `fetch_local_votes`, as `run.sh` and the nightly stage do. A new
member in the same seat cannot inherit the former member's cached portrait or
contact details. Missing, malformed, or ambiguously attributed archives fail.

Refresh metadata records the pause without advancing the last successful
collection date. Legacy archives have no reliable date, so it remains unknown.
The importer exposes this status through SQLite metadata and the static API;
council, district, and current-member pages display a missed-refresh notice.
Votes and other records still refresh and pass the existing integrity gates.
Profile output is replaced atomically only after West Allis succeeds. No source
denial is retried or suppressed, and no paid resource is added.

## Zero-second retry headers (2026-09-08)

The initial daily policy job stopped on West Allis with HTTP 200. A subsequent
single robots review returned the existing fingerprint and `Retry-After: 0`.
[RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3) defines this
value as a delay in seconds, so zero adds no wait. Successful 2xx responses now
accept that value while retaining the configured request interval. Access denials,
exhausted limits, error/redirect responses with Retry-After, and nonzero or malformed
values still stop collection. Policy fingerprints and source permissions are unchanged.
The nightly runner must produce a fresh successful report before collection resumes.

## Nightly finance windowing (2026-09-07)

The CFIS [robots file](https://campaignfinance.wi.gov/robots.txt) was rechecked
for the monthly job split; its reviewed fingerprint is unchanged. Keep the
conservative ten-second interval because the published `Crawl-delay: 10`
has ambiguous group placement. The collector's shorter page sleep counts
toward that interval; the transport waits only the remaining time. The split
does not change source pacing, permitted paths, request shapes, redaction,
or reuse scope in the review above.

Nightly committee collection uses the existing `--since YYYY-MM --until YYYY-MM`
interface once per month, with one worker at a time. Every month from January
2025 through the run's frozen start month is still refreshed. Receipt refresh
and historical audit accept `--as-of YYYY-MM-DD` to keep their month selection
and audit rotation stable across job boundaries and retries; this is not an
upstream point-in-time snapshot. All completed month outputs are merged with
the prior archive before the full import. Missing, conflicting, or incomplete
outputs stop publication. See [hosting and recovery](../../docs/nightly-parser-hosting.md).

## CFIS completeness recovery (2026-09-08)

The [CFIS robots file](https://campaignfinance.wi.gov/robots.txt) passed the existing
fingerprint check during diagnosis. The [public search guidance](https://ethics.wi.gov/Pages/CampaignFinance/ViewReports.aspx)
and [reuse notice](https://ethics.wi.gov/Resources/20251021%20Open%20Session%20Materials%20Revised.pdf)
were rechecked. Keep the reviewed paths, identifying User-Agent, redaction,
noncommercial civic scope, and ten-second request floor described above.

The transaction endpoint can return incomplete results depending on page size.
Receipt refresh, historical audit, and committee collection now require scanned
rows and unique transaction IDs to equal the reported count before writing a
month. An incomplete month gets at most two retakes, with a five-second wait
that counts toward the transport's ten-second floor. For counts of at most
1,000, retakes use 100-row pages; larger months keep 1,000-row pages. Recovery
also rechecks the count after fetching. Failed attempts are discarded in full;
missing rows are never excused because they appear irrelevant to receipt filters.
Access-policy failures still stop collection through the existing transport.

Normal collection keeps 1,000-row pages. Committee collection adds one count
request per month (about 3.5 minutes across 21 months at the current interval).
No service or dependency is added. Raw diagnostic responses stay private.

## Preserving lobbying data offline

`run.sh` no longer fetches lobbying pages. It still imports the complete existing
`_data/lobbying/interests-*.json` archive after rebuilding the database, so this
change does not discard collected registrations. Registrations are private: the
site has no lobbying pages or bill panels, and bulk exports delete these rows
before vacuuming the copied database. Publication requires an approved source.
`fetch_lobbying.parse_principals()` remains a network-free parser for locally
saved HTML; it is not a complete manual-upload workflow.

Do not replace the full archive with a one-page download: `import_lobbying`
rebuilds the entire table. Keep original HTML, session, official source URL and
download date outside public Git. Validate and merge partial approved updates
into the existing archive before running an import. Archive importers fail on
missing input rather than silently substituting empty data.
## Federal campaign finance (2026-09-09)

The [FEC bulk downloads](https://www.fec.gov/data/browse-data/?tab=bulk-data) publish
the [all-candidate summary format](https://www.fec.gov/campaign-finance-data/all-candidates-file-description/).
Collection uses only `www.fec.gov/files/bulk-downloads/YYYY/weballYY.zip`:
one current-cycle file per nightly federal stage (193 KB at review), no API key
or paid service. The [robots file](https://www.fec.gov/robots.txt) permits this
route and specifies a ten-second interval, enforced by the shared transport.
The official link redirects to the FEC's exact GovCloud S3 host
`cg-519a459a-0ea3-42c2-b7bc-fa1143481f74.s3-us-gov-west-1.amazonaws.com`;
its `robots.txt` returns 404. Only `/bulk-downloads/YYYY/weballYY.zip` on that
host is approved, also at ten seconds. Other buckets and paths remain blocked.
The [privacy/security policy](https://www.fec.gov/about/privacy-and-security-policy/)
and [data-use guidance](https://www.fec.gov/updates/using-information-obtained-from-fec-reports/)
were reviewed. This civic display uses candidate aggregates, no donor contact lists.
Keep the raw ZIP and validated summary in the private federal archive; no browser
requests or new hosting resources are required. The added storage is under 1 MB
per snapshot at the reviewed file size, within the existing cost target.

FEC IDs come from the existing congressional roster, filtered by current chamber;
never match candidate names. Store dollars as integer cents, preserve blanks,
reporting dates, refunds, and authorized-committee transfers. The display reports
the FEC's gross totals with its transfer caveat; it does not combine federal money,
state campaigns, or outside spending. Federal donor-level detail links to the FEC.

`importer/federal_campaigns.json` links federal members to explicitly verified
state campaign committees. Tiffany's gubernatorial committee is CFIS entity 16621,
registration 0104212, verified against his campaign disclosure, CFIS registry, and
the January 2026 state filing. Identically named unregistered entities are excluded.
The existing reviewed CFIS monthly scans retain that committee's transactions
without adding requests, changing pacing, or weakening completeness checks.
Monthly coverage travels with the registry; the importer stores campaign records
separately and preserves the existing PAC and legislator tables. State totals stay
hidden until every cycle month through the snapshot's month has been collected.
The first full nightly run backfills 2025 onward; all committee activity in that
period is included, including activity before a campaign announcement.

After merging, run the policy-only workflow to approve the updated manifest before
manually starting collection, or allow the scheduled policy check to run first.
An old policy report is intentionally invalid for the expanded source manifest.
Portrait loading note: Appleton's council image URLs redirect to
`cms2.revize.com/revize/appletonwi/`; that host's root `robots.txt` disallows
general crawlers from images. Collect only the image URL metadata on the permitted
city roster, and leave image loading to visitors' browsers. Do not download images
or run automated image-load checks against that host. Waukesha redirects portraits
to its `webfile.waukesha-wi.gov/waukeshawi25/` image host (robots 404 at review).
