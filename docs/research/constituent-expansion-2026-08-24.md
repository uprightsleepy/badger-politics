# Constituent-Facing Expansion Research — 2026-08-24

Research document only; nothing here is implemented. Architecture context for
every judgment below: nightly job → openstates-scrapers (+ our own fetchers) →
SQLite → Astro static build → Firebase Hosting. A source only fits if its data
can be pulled nightly, persisted in SQLite, and baked into static pages.

## 1. Inventory: what we ingest, store, and display today

From `pipeline/importer/schema.sql`, the site routes in `site/src/pages/`, and
`pipeline/dataproducts/` — verified against the actual database, not assumed
from the scrapers.

### Entities and fields in SQLite

| Table | Contents | Source |
|---|---|---|
| sessions | 23 sessions (9 regular bienniums 2009–2025, 13 historical special sessions, 2026s1), names, start/end dates, data-quality flag | openstates scraper |
| people | Name, party, current role, chamber, district, portrait URL | openstates/people YAML |
| person_terms | Service terms incl. mid-biennium ends, with curated end labels/URLs (recalls, resignations) | people YAML + curation |
| bills | ~18k bills/resolutions: title, classification, derived status (introduced → enacted/vetoed/failed_sjr1/adopted), LRB plain-language analysis, died-without-hearing flag + committee-at-death | openstates scraper + docs.legis |
| sponsorships | Primary authors, cosponsors, coauthors (derived from official history text where the scraper drops them), roster-resolved | scraper + history derivation |
| actions | Full official history per bill, verbatim | docs.legis via scraper |
| bill_documents | Official attachments verbatim: fiscal estimates, LC memos, hearing materials, amendment histories, **318 veto messages**, Ethics filings | docs.legis |
| bill_subjects | State subject-index terms, 2013→ | docs.legis subject index |
| vote_events / vote_records | Every roll call with per-member votes (full 2011→ incl. special sessions; tally-only for committee/journal motions) | docs.legis vote documents |
| committees / committee_members | Current rosters with chairs | openstates people repo |
| hearings / hearing_videos | Hearing schedule + agendas, WisconsinEye recording links (exact date+committee match) | scraper + wiseye.org |
| elections | 2026 cycle per-member: on-ballot, incumbency, opponents w/ ballot status | WEC ballot-access PDF |
| election_history | Certified legislative results 2022/2024, official Total Votes Cast | WEC ward-by-ward canvasses |
| statewide_races / statewide_history / statewide_county_results | 2026 constitutional-office candidates; certified 2022 statewide results incl. all 72 county aggregates | WEC |
| lobbying_interests | (bill, principal) registrations — interest only, not positions | Ethics "Eye on Lobbying" |
| cfis_committees / contributions | Verified committee↔legislator map; every receipt with donor entity id, type, occupation, category | Ethics CFIS API |

### Pages (site routes)

Bills (per session, per bill w/ history, sponsors, roll calls, LRB analysis,
documents, lobbying, subjects), New laws per biennium (act number, approval
date, passage roll calls), Veto tracker, Governor's desk (incl. governor card),
Hearing None (died-without-hearing per committee/session), legislators (profile:
authored + cosponsored bills, key votes, party breaks/agreement, attendance
heatmap, full vote history, campaign money with composition/top donors/
occupations/timeline, seat election history, compensation, 2026 ballot status),
committees, districts (address→district finder via Census geocoder + LTSB
boundaries; seat lineage; margins), My Reps dashboard, calendar (+iCal),
elections/2026 (legislative + statewide, cycle stats, county tables), money
(overview, per-committee donor pages), lobbying (org pages, most-lobbied),
subjects, votes (roll-call pages), testify guide, glossary, about/methodology,
following (localStorage), Atom feeds, static JSON API (`/api/v1/...`), bulk
exports, Pagefind search.

### Stored but not (or barely) surfaced

- **Veto messages**: 318 in `bill_documents`, linked only in each bill's
  documents list — not surfaced on /vetoes/ where a reader would look.
- **Contribution categories**: conduit (52,521 rows), in-kind, loans, returned
  contributions — summed into totals but never broken out.
- **Legislator contact info**: the people YAML we already fetch carries `email`
  and official-page links; both are dropped at import. No contact info on
  profiles — for a constituent site this is the single loudest absence.
- **Sessions start/end dates**: stored for all 23, surfaced only implicitly.
- **Vote options granularity**: schema supports excused/paired/absent; data
  currently carries yes/no/not-voting.

## 2. Research method and the honest caveats

Three parallel research passes fed this document: a feature audit of comparable
sites (pages actually fetched and read; sites that block automation are marked
as search-derived), a demand-evidence pass (official FAQs, hotline pages,
recurring journalism, advocacy-org how-tos), and a source/terms pass (operative
ToS sentences quoted from the governing pages). I then re-verified the four
most load-bearing licensing claims myself against the live pages.

Caveats stated up front, not buried:

- **Reddit was unreachable** from this environment, so there is no first-person
  thread evidence. Demand ratings rest on institutional evidence: when the
  Legislature staffs a hotline, Legislative Council prints a citizen PDF, and
  three advocacy orgs each maintain their own how-to for the same question,
  that convergence is treated as demand.
- Sunlight Foundation / Code for America turned out to have little published
  *end-user* research on legislative data. Their one relevant quantitative
  finding: people request records about *their specific situation* far more
  than aggregate data ([Sunlight 2018](https://sunlightfoundation.com/2018/10/16/results-from-analyzing-public-record-requests/)).
  Translated: "this one bill / my legislator / my district," not dashboards.
- Several comparable sites (GovTrack, LegiScan, Ballotpedia, WisDC) block
  automated reading; their feature claims below come from search snippets
  citing their own URLs and are labeled as such in the underlying research.

**The competitive picture in one paragraph.** No free, plain-language Wisconsin
bill tracker exists: docs.legis is PDFs and indices with no address lookup and
nightly-email-only alerts ([docs.legis](https://docs.legis.wisconsin.gov/),
[notify.legis](https://notify.legis.wisconsin.gov/)); WisPolitics paywalls bill
tracking ([wispolitics.com](https://www.wispolitics.com/)); LegiScan is
data-dense and pro-oriented; the old Open States consumer site is largely
dismantled into the Plural app ([blog.openstates.org](https://blog.openstates.org/2023-june-changes/));
FastDemocracy's free tier is the closest competitor but generic multi-state
([fastdemocracy.com/states/wi](https://fastdemocracy.com/states/wi/)). Nobody
in Wisconsin joins money to legislative behavior (WisDC has raw lookup tools
only), and the benchmark for what a state site can be is CalMatters Digital
Democracy ([calmatters.digitaldemocracy.org](https://calmatters.digitaldemocracy.org/)).
A 2025–26 development that changes the landscape: **WisconsinEye went dark
mid-December 2025** over a funding shortfall ([PBS Wisconsin](https://pbswisconsin.org/news-item/wisconsineye-shutdown-leaves-state-lawmakers-meetings-outside-of-public-view/),
verified directly), resumed on stopgap legislative funding through 2026
([Urban Milwaukee](https://urbanmilwaukee.com/2026/07/29/legislature-gives-wiseye-250000-to-operate-for-rest-of-2026/));
its future beyond 2026 is uncertain, which both raises the value of our
text-based hearing/vote records and makes our existing WisEye links fragile.

## 3. Ranked candidate features

Ranked by constituent value first, feasibility second. Effort is judged
against the existing pipeline (nightly fetchers → SQLite → gates → static
build). **Reminder that colors every "freshness" feature: the site is not yet
deployed, so anything whose value depends on being current is gated on Phase 6
hosting.**

### #1 — Contact your legislators (profiles, My Reps, bill pages)

- **Constituent gain:** the single best-evidenced constituent need. The
  Legislature staffs a phone hotline whose stated purpose is telling people
  who represents them and how to reach them
  ([hotline](https://legis.wisconsin.gov/about/contact); FAQ items #1–2,
  [legis FAQ](https://legis.wisconsin.gov/about/faq)); at least five advocacy
  orgs maintain their own "contact your legislator" pages. We already answer
  *who*; we answer nothing about *how to reach them*.
- **Evidence of demand:** STRONG (hotline + official FAQ + UpNorthNews
  explainer + five independent org how-tos — URLs in §2 research).
- **Source:** already in our pipeline. The openstates/people YAML we fetch
  nightly carries `email` per member (verified in `_data/people/wi/`); office
  phone/address available on each member's docs.legis page (public record).
  openstates/people is CC0 ([repo](https://github.com/openstates/people)).
- **Licensing:** clean — CC0 + state public records. No review needed.
- **Effort:** small. Schema column(s) + importer + profile/My Reps cards.
- **Risks:** none material. Emails/phones are official public contacts.

### #2 — Plain-language outcome explainers: "why is this bill dead?"

- **Constituent gain:** docs.legis never says "this bill is dead." We already
  derive `died_without_hearing` and `failed_sjr1`; the missing piece is the
  plain-English sentence on every dead bill ("died when the session's floor
  deadline passed without a vote — most bills end this way") plus one
  evergreen partial-veto explainer page. End-of-session mass bill death is
  re-explained by journalists every cycle
  ([Wisconsin Watch 2026](https://wisconsinwatch.org/2026/02/wisconsin-assembly-legislature-what-lawmakers-did-and-what-is-unfinished/),
  [Cap Times](https://legis.wisconsin.gov/assembly/71/shankland/newsroom/news/2112021-the-cap-times-wisconsin-lawmakers-work-to-revive-bills-left-for-dead-during-last-legislative-session/));
  the partial veto is the most repeatedly re-explained topic in Wisconsin
  politics ([LRB](https://docs.legis.wisconsin.gov/misc/lrb/reading_the_constitution/reading_the_constitution_4_1.pdf),
  [PBS](https://pbswisconsin.org/news-item/the-story-of-wisconsins-singular-partial-veto/),
  [Leg. Council 2025 memo](https://docs.legis.wisconsin.gov/misc/lc/information_memos/2025/im_2025_04)).
- **Evidence of demand:** STRONG phenomenon; first-person evidence mediated
  through journalists (honest caveat). Partial-veto demand is episodic —
  one great page, not a feature.
- **Source:** existing DB + citations to LRB/Leg. Council documents (public
  records, stable docs.legis URLs).
- **Licensing:** clean.
- **Effort:** small (status-explainer strings + one content page citing LFB/
  LRB documents).
- **Risks:** wording must stay strictly factual; cite the SJR-1 mechanism.

### #3 — Hearing alerts / "this week at the Capitol" (gated on deployment)

- **Constituent gain:** short-notice hearings are the documented pain — the
  press's open-government column calls the state's email notification service
  "the de facto notification for just about all interested parties"
  ([Wisconsin Watch](https://wisconsinwatch.org/2020/03/your-right-to-know-hearings-should-have-ample-notice/)),
  and the Legislature's testify page + two Legislative Council citizen PDFs
  show the mechanics are arcane ([testify](https://legis.wisconsin.gov/about/testify),
  [citizen guide](https://legis.wisconsin.gov/lc/a-citizens-guide)). We
  already ingest hearings + agendas and ship a calendar + iCal; the gap is a
  prominent "being heard this week, in plain English, with how-to-testify
  links" view — the state's own committee-schedule site surfaces no
  dates/agendas in its index view (verified by direct read).
- **Evidence of demand:** STRONG.
- **Source:** existing scraper. For email alerts, link out to the state's
  free [notification service](https://notify.legis.wisconsin.gov/) rather
  than building alert infrastructure (static site, no server).
- **Licensing:** clean.
- **Effort:** small — but **worthless until nightly builds exist**. A static
  "this week" page built from stale data is worse than nothing. Gate on
  Phase 6.
- **Risks:** staleness (hard gate); hearing notices can post <48h ahead, so
  even nightly builds miss some — say so on the page.

### #4 — Veto messages and executive orders, surfaced

- **Constituent gain:** we hold **318 veto-message documents** already
  (`bill_documents`, note = "Veto Message") but a reader on /vetoes/ can't
  reach them; the governor's actual stated reasons are one join away.
  Executive orders 1965–present sit in a stable docs.legis archive
  ([docs.legis EO archive](https://docs.legis.wisconsin.gov/code/executive_orders)),
  a better source than the governor's JS-rendered SharePoint site.
- **Evidence of demand:** MODERATE (veto coverage is journalist-heavy;
  pairs naturally with the existing veto tracker and governor card).
- **Source:** veto messages already in SQLite; EOs = new small scrape of a
  stable public-records archive (example veto PDF:
  [2023 SB70](https://docs.legis.wisconsin.gov/document/vetomessages/2023/SB70.pdf)).
- **Licensing:** public records; the one-time LRB-copyright review in §5
  applies to *rehosting* PDFs — linking verbatim is unambiguous.
- **Effort:** trivial (link veto messages on /vetoes/) to moderate (EO pages).
- **Risks:** none for linking.

### #5 — Referendum / constitutional-amendment pipeline

- **Constituent gain:** ballot questions confuse voters every cycle
  ([UW law explainer](https://statedemocracy.law.wisc.edu/featured/2024/explainer-the-proposed-constitutional-amendment-on-noncitizen-voting-on-wisconsins-november-general-election-ballot/),
  [WISN](https://www.wisn.com/article/statewide-referendum-on-novembers-ballot-what-does-it-mean/62396753),
  [WPR](https://www.wpr.org/news/voter-id-law-wisconsin-explainer-april-1-referendum)),
  and the piece nobody explains is precisely what we have: the
  legislature-to-ballot pipeline (a constitutional amendment is a joint
  resolution passed in two consecutive sessions). We can show each proposed
  amendment's two-session progress, sponsors, votes — then its certified
  ballot result.
- **Evidence of demand:** MODERATE-STRONG, seasonal.
- **Source:** joint resolutions already in DB; results from WEC certified
  ward/county reports which include referenda
  ([WEC results](https://elections.wi.gov/elections/election-results),
  public records, xlsx) — same parser family we already gate-verify.
- **Licensing:** clean (state public records; WEC footer copyright noted,
  results are public records — same basis as our existing canvass use).
- **Effort:** moderate (identify amendment JRs across sessions, join text,
  parse referendum rows from canvasses we already download).
- **Risks:** matching a JR to its ballot question needs careful, documented
  rules (two-session identity); seasonal payoff.

### #6 — District demographics on district pages

- **Constituent gain:** "who lives in my district" context (population, age,
  income, education) on the district pages — the CalMatters profile pattern.
- **Evidence of demand:** MODERATE — competitors build it (CalMatters,
  Ballotpedia); direct constituent-ask evidence is thin. Ranked accordingly.
- **Source:** Census ACS 5-year API, which supports state-legislative-district
  geographies (verified: geography codes 610/620 in
  [the ACS geography list](https://api.census.gov/data/2023/acs/acs5/geography.json));
  TIGER/LTSB boundaries we already use.
- **Licensing:** clean — U.S. Government work, public domain;
  **mandatory disclaimer** verified on the
  [Census ToS](https://www.census.gov/data/developers/about/terms-of-service.html):
  "This product uses the Census Bureau Data API but is not endorsed or
  certified by the Census Bureau."
- **Effort:** moderate (annual fetch, small table, district-page section).
- **Risks:** **map-vintage trap** — ACS SLD geographies lag the 2024 (Act 94)
  remap; must verify which map each ACS vintage reflects before showing
  numbers next to a 2024-map district. Flagged as a pre-implementation check.

### #7 — Court challenges to enacted laws (federal first)

- **Constituent gain:** "this law is being challenged in court" on act pages
  (think Act 10, the partial-veto cases, redistricting).
- **Evidence of demand:** MODERATE, journalist-mediated.
- **Source:** CourtListener/Free Law Project for federal courts (W.D./E.D.
  Wis., 7th Cir.): bulk data verified public-domain-marked — "Our bulk data
  files are free of known copyright restrictions"
  ([bulk-data page](https://wiki.free.law/c/courtlistener/help/api/bulk-data/bulk-legal-data),
  verified directly); API free at 125 requests/day
  ([API docs](https://www.courtlistener.com/help/api/rest/)), fine for a
  handful of tracked dockets. **State courts are the catch**: WSCCA has no
  API/ToS (needs review) and circuit-court bulk access (WCCA) is a paid
  subscription designed to prevent scraping.
- **Licensing:** federal path clean; state path **needs human review**.
- **Effort:** moderate-high; curation-heavy (which cases challenge which act
  is an editorial judgment needing sources).
- **Risks:** partial coverage (federal-only at first) must be labeled
  honestly; matching cases→acts can't be automated safely.

### #8 — "Most-viewed bills" orientation signal

- **Constituent gain:** cheap orientation ("what are other people looking
  at") — the pattern FastDemocracy, LegiScan, and NM Bill Tracker all use.
- **Evidence of demand:** WEAK-MODERATE (competitor-common, not
  constituent-asked; ranked low accordingly).
- **Source:** our own GoatCounter analytics (already the site's only
  analytics; its API can be queried at build time). No third-party data.
- **Licensing:** our data; clean.
- **Effort:** small. **Gated on deployment** (needs real traffic).
- **Risks:** low-traffic noise early on; never present as importance.

## 4. Rejected ideas and why

| Idea | Verdict | Reason (with the governing link) |
|---|---|---|
| Vote Smart bios/ratings | **Rejected** | API terms: on revocation "you shall immediately remove all Project Vote Smart content" ([terms](https://api.votesmart.org/docs/terms.html)) — incompatible with baking into a redistributable static build; fees unpublished (sales-led). |
| OpenSecrets/FollowTheMoney state money | **Rejected** | API discontinued April 15 2025 ([opensecrets.org/api](https://www.opensecrets.org/api)); bulk data is "educational use only" ([open-data](https://www.opensecrets.org/open-data)) and site content is CC BY-NC-SA — public redistribution not clearly permitted; state data unmaintained past 2024. CFIS (primary source, already ingested) is strictly better. |
| WisconsinEye video storage/embedding/transcripts | **Rejected beyond plain links** | User agreement: "no portion of our Content may be recorded, reproduced… redistributed… without the express written permission" ([user agreement](https://wiseye.org/user-agreement/)); political-use clause is hazardous near elections. Current plain hyperlinks remain fine; monitor their post-2026 survival. |
| Google Civic API for address lookup | **Rejected** | Representatives API shut down April 30 2025 ([turndown notice](https://groups.google.com/g/google-civicinfo-api/c/9fwFn-dhktA)); what remains returns OCD-IDs only, and Google ToS caching limits conflict with static builds. Our Census-geocoder + LTSB-boundary lookup already does this better, license-clean ([LTSB open data](https://gis-ltsb.hub.arcgis.com/)). |
| LegiScan as a data source | **Rejected for now** | We scrape the primary source directly; LegiScan adds nothing we lack, and its governing ToS is behind a bot wall no automated read could reach — storage rights unverified. If ever wanted (e.g., as a cross-check feed), a human must read [legiscan.com/terms-of-service](https://legiscan.com/terms-of-service) first. |
| Administrative-rules tracker | **Deferred (weak demand)** | Every guide found is professional-facing (e.g., [lobbying-firm guide](https://www.hamilton-consulting.com/hcg-guide-to-the-wisconsin-administrative-rules-process/)); zero consumer explainers or FAQ presence. Data is feasible (Register is public-record HTML/PDF with RSS, [register](https://docs.legis.wisconsin.gov/code/register)) — so this is a demand rejection, not a licensing one. Revisit if a rule ever drives constituent traffic. |
| Election-night results | **Rejected** | No feed exists: "Wisconsin does not have a statewide system for reporting unofficial results on Election Night" ([WEC](https://elections.wi.gov/elections/election-results)). Certified-only is what we already do. |
| WCCA circuit-court data subscription (CCAP REST) | **Rejected — cost** | $12,500/yr non-refundable (§XIII of the subscription agreement, on file); 7-day update duty (§VIII.D) and destroy-on-direction (§VIII.E) also misfit a static archive. Court tracking proceeds federal-first (CourtListener) + curated WSCCA links. |
| Bill prognosis / ideology scores / report-card grades | **Rejected** | GovTrack/CalMatters pattern, but computed judgment scores conflict with our raw-facts-with-methodology ethos; our rule-selected Key Votes already covers the defensible part. |
| Ballotpedia-style pro/con argument curation | **Deferred** | Valuable but original editorial content with ongoing maintenance; doesn't fit the current one-maintainer, data-derived model. |

## 5. Open questions — DECIDED 2026-08-24

1. **Rehosting state PDFs: links only.** No rehosting of veto messages, LRB
   documents, or any state PDF; every ranked feature works with links to the
   stable docs.legis URLs. This removes the LRB-copyright question entirely.
2. **Deployment gating: confirmed.** #3 (this-week hearings) and #8
   (most-viewed bills) queue behind Phase 6 hosting; not built dark.
3. **State-court tracking: circuit-court data is rejected on cost.** The
   Wisconsin Court Data Subscription Agreement (CCAP REST, non-state
   subscriber form, rev. 08/2022 — on file) settles it: §XIII "Subscriber
   agrees to pay a non-refundable subscription fee of **$12,500** for 12
   months of electronic access to WCCA Information through the REST
   interface." That is ~520× the site's entire annual budget, so it fails
   hard constraint #1 regardless of terms. The terms would independently be a
   poor fit for a static archive: published records must be updated "within
   seven (7) days after receiving WCCA Information" (§VIII.D), the subscriber
   must "promptly comply with all CCAP instructions… including… any direction
   to destroy or modify the data" (§VIII.E), a mandatory disclosure statement
   must accompany every display (§VIII.C), criminal-case displays require a
   statutory employer advisory (§VIII.F), and all data must be destroyed on
   termination (§XII.F). Redistribution per se *is* permitted on websites
   listed in Exhibit A (§VII.D) — cost and the update/destroy duties are what
   kill it, not a display ban. **Resolution: candidate #7 proceeds
   federal-first via CourtListener (public-domain bulk, verified), with major
   state cases handled as curated links to WSCCA/wicourts case pages —
   linking to the public appellate site requires no agreement.**
4. **Reddit demand check: skipped** by decision; rankings stand on the
   institutional evidence.
5. **Contact-info scope for #1: email and phone, office contacts only** —
   official Capitol office email/phone/address as published by the
   Legislature; never personal numbers or addresses. Emails come from the
   CC0 people YAML already fetched; office phone/address will come from each
   member's docs.legis page (public record).

## Appendix: source-terms summary matrix

| Source | Store + redistribute in a static build? | Cost | Verified basis |
|---|---|---|---|
| openstates/people & Plural bulk | Yes — "public domain dedication" | Free | [open.pluralpolicy.com/data](https://open.pluralpolicy.com/data/) (verified directly) |
| docs.legis.wisconsin.gov | Yes — public records/edicts; no site ToS exists | Free | direct read; LRB caveat in §5 |
| WEC results (xlsx canvasses incl. referenda) | Yes — public records | Free | [elections.wi.gov](https://elections.wi.gov/elections/election-results) |
| LTSB GIS hub | Yes — "open and publicly available data" | Free | [DCAT feed](https://gis-ltsb.hub.arcgis.com/api/feed/dcat-us/1.1.json) |
| Census ACS/TIGER | Yes — public domain; mandatory disclaimer | Free | [ToS](https://www.census.gov/data/developers/about/terms-of-service.html) (verified directly) |
| CourtListener bulk | Yes — "free of known copyright restrictions" | Free (API 125/day) | [bulk data](https://wiki.free.law/c/courtlistener/help/api/bulk-data/bulk-legal-data) (verified directly) |
| LAB / LFB publications | Yes (link-first) — public records | Free | [LAB](https://legis.wisconsin.gov/lab/), [LFB](https://legis.wisconsin.gov/lfb/) |
| WI Admin Register | Yes — public records (weak demand though) | Free | [register](https://docs.legis.wisconsin.gov/code/register) |
| WisconsinEye | **No** — link only | Free to link | [user agreement](https://wiseye.org/user-agreement/) |
| Vote Smart | **No** — removal-on-revocation | Unpublished | [API terms](https://api.votesmart.org/docs/terms.html) |
| OpenSecrets/FTM bulk | **Unclear** — "educational use only" | Free w/ approval | [open-data](https://www.opensecrets.org/open-data) |
| LegiScan | Unverified — ToS behind bot wall | Free 30k/mo | [manual](https://api.legiscan.com/dl/LegiScan_API_User_Manual.pdf); human read needed |
| Google Civic | Representatives API dead 4/30/2025 | — | [turndown](https://groups.google.com/g/google-civicinfo-api/c/9fwFn-dhktA) |
