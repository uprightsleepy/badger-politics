# Council data access in Green Bay, Kenosha and Racine

Use each city's existing public records interface where its applicable policies do not explicitly prohibit the proposed collection and reuse. Missing policies or silence about scraping do not require affirmative permission. Racine's API metadata and current identities are verified, but its meeting endpoint returns a configuration error. Green Bay now has a validated shared reader for its documented public CivicClerk API. Kenosha needs a separate records supply because its Granicus host explicitly excludes general crawlers.

An officially documented public API is an acceptable collection route without a separate permission request. Follow its documented scope, authentication requirements, usage limits and applicable explicit restrictions. Apply restrictions to the host, paths and use they actually govern. Distinguish an explicit prohibition from a technical denial, a failed policy check or an unverified record format. No city or vendor has been contacted. Green Bay is implemented for dev validation; Racine and Kenosha remain disabled. The remaining work is described per route below; there is no general requirement to obtain a city's written approval.

| City | Recommended first route | Fallback | Remaining decision |
| --- | --- | --- | --- |
| Green Bay | Shared reader for the documented public CivicClerk API | City-published export for earlier history or missing fields | Validate the new snapshot in dev; July and August samples preserve all 900 positions. [^36][^37][^38] |
| Kenosha | Clerk/Treasurer supplies existing electronic proceedings and any underlying vote export | A specifically authorized recurring file delivery | Determine the source system and whether individual positions exist beyond narrative summaries. Its Granicus robots file blocks our crawler. [^8][^9] |
| Racine | Use the shared Legistar collector after the meeting endpoint works and samples pass | A supported export or separately validated public InSite reader | `cityofracine` metadata and all 15 current district identities are verified; `Events` returns HTTP 400 for missing agenda-visibility configuration. [^32][^33][^34] |

Population remains the research order. Implementation can proceed as each source passes its applicable policy and data checks. A blocked source need not hold up another city, and outreach is a fallback when a restriction or missing data prevents the public route.

## Green Bay

### Verified public API and individual votes

Green Bay's official meeting page links to CivicClerk. The city's archive announcement describes older documents, while the current council page identifies twelve districts. These establish provenance and a historical lead, not complete structured history. [^4][^6][^31]

The public portal uses `greenbaywi.api.civicclerk.com/v1`. Its anonymously accessible `$metadata` document publishes the OData entities and functions, including meeting items, motion vote arrays and file retrieval. `EventCategories` identifies Common Council as category 26. The working meeting route is `/Meetings/{agendaId}`; the parenthesized OData key form returned 404. No token or staff account was used. This is the relevant Select/CivicClerk schema; the earlier Meetings Essential documentation was for a different product. [^24][^36]

Two meetings were validated: July 21, 2026 (event 9722, agenda 9275) and August 18, 2026 (event 9565, agenda 9276). Their nested items contain 42 and 33 motions respectively, with 504 and 396 individual positions. They include dissent and an abstention. Every sampled item's `hasVote` flag is false, so the reader follows the actual `minutesItemVotes` arrays instead. Each motion on an item remains separate. The published July 21 minutes independently confirm the API's 0/1 failed/passed codes, including the 5–7 failed motion. [^37][^38][^40]

The vote arrays contain full names rather than stable person IDs. All twelve voters match the official roster, with one verified alias: the city identifies district 3's Bill Morgan as William Morgan on his individual page. The shared curation assigns permanent internal person IDs; unknown or ambiguous names stop import. The current roster refreshes each run, with its date and source retained. It does not supply office term dates, so none are invented. Coverage begins July 1, 2026; earlier history needs a separate roster review. [^6][^39]

### Access scope and collection bounds

The API robots file returned 404. Portal robots returned 200 without disallow rules; the city's robots file permits the current council roster page. Runtime collection enables only API `Events`, `Meetings/{id}`, and the official roster page, with a five-second per-host request floor. Native records remain private, and production extraction is deterministic. [^41][^42]

CivicPlus's terms restrict interface use, excessive traffic, unauthorized republication and AI-related uses, while recognizing intended API/export functionality and public-records obligations. Collection uses the public documented interface for recorded voting facts and source links. No portal interface, video, staff console or restricted export is copied. The separate staff Analytics and optional Voting History documentation are background capabilities, not dependencies of this reader. [^2][^3][^7]

Each run refreshes the roster and paged event index and downloads at most two meetings. Unchanged records with published minutes are reused for seven days; drafts can refresh daily. Changed event metadata triggers an earlier refresh within the same cap. Prior native revisions are retained. Disappearing motions or recorded voters stop replacement for review rather than silently reducing the archive. Publication is labeled Published, not assumed to establish approval.

### Implementation and validation

The CivicClerk platform reader feeds the existing shared SQLite importer and council pages. City settings and verified identities are configuration. Every nested motion and recorded Yes/No/Abstain position is preserved; attendance and positions implied only by unanimity are not inferred. Site tallies recognize Yes alongside Aye while retaining displayed source vocabulary.

Live collection succeeded with the two-meeting cap. An isolated import preserved all 501,763 prior vote rows across five cities and all 806 source files, added exactly 75 Green Bay motions and 900 positions, and passed local integrity checks. The parity fixture includes a partial Madison research sample and is not a deployment archive. Automated tests cover nested items, multiple motions, identity ambiguity, roster changes, paging, bounded backfill, cached refreshes and transaction rollback.

**Assessment:** implemented for dev validation. Merge, refresh the separate policy job, collect a new validated snapshot, then run the dev release. No separate API permission request or paid service is required. The city's open-data program and clerk export remain options for earlier history or fields absent from the public API. [^1][^5][^25]

## Kenosha

### A clearer retrieval restriction

The earlier observation was a 403 response from `www.kenosha.org/robots.txt`. That failed policy check is not published prohibition language. RFC 9309 permits, but does not require, access after unavailable 4xx robots responses. The current runtime rejects an unexpected response until reviewed; its technical behavior is separate from the policy decision. The reason for Kenosha's 403 remains unknown. [^8][^10]

A separate policy-only check of the officially used `kenosha.granicus.com` host returned HTTP 200 with a wildcard group containing `Disallow: /`. There are narrower named crawler groups, but none authorizes this project's crawler. Do not impersonate one of them. This is an explicit reason to avoid automated retrieval from that host unless the operator supplies a reviewed authorization and compatible access configuration. No Granicus records were downloaded during that check. [^9]

The practical route is therefore a **clerk-supplied copy or an explicitly designated export**, not a different URL pattern on the blocked host. The project does not need to solve the website's bot protection to receive records through the city's ordinary records process.

### Available record forms and accuracy limits

Kenosha's published Clerk/Treasurer records-request form accepts requests for specified documents and offers email delivery. The document is marked revision November 2017; its fee table should not be treated as a current quotation. The county's official service directory, updated February 2026, independently identifies the City Clerk/Treasurer as the office supporting Common Council meetings and access to records. This is the city office, not the county board clerk or circuit court. [^11][^12]

An indexed official January 21, 2026 agenda links an earlier meeting's minutes and contains committee recommendations with vote totals. Those recommendations are not the council's later votes on the same subjects. An indexed January 17, 2024 proceedings example records a 12–1 roll call while naming the dissenting member. That example demonstrates a possible narrative format; it does not establish the completeness or format of 2025–2026 records. [^26][^27]

For this project, a tally plus a named dissenter is insufficient to attribute every other member's position. Attendance at the meeting does not establish presence for every subsequent vote. Likewise, “unanimous,” an agenda recommendation, a passed flag or a video timestamp must not be expanded into invented individual votes.

Granicus documents workflows transferring agendas, motions and votes between Legistar and LiveManager/MediaManager. This is evidence that structured records can exist behind such a portal, not proof that Kenosha uses Legistar or has a public Legistar tenant. Confirm the source system with the clerk rather than guessing a tenant or probing application endpoints. [^23]

### Recommended next action

Ask the **City Clerk/Treasurer** for existing electronic Common Council proceedings for one recent calendar month, the roster effective during that month, and any existing machine-readable motion, vote or attendance report. Ask whether the published minutes summarize fuller records kept in LiveManager, VoteCast, Legistar or another system.

If structured records are unavailable, request original electronic minutes and assess a small sample manually. A PDF reader should preserve the exact recorded tally and any explicitly named positions, while distinguishing incomplete attribution from a complete individual roll call. Do not activate the current member-vote product for Kenosha until the chosen representation can retain those distinctions.

For recurring delivery, propose one export after approved minutes are published, or an approved monthly bundle. If a public file endpoint is offered, obtain its applicable terms, robots policy and request limits before enabling it. If the city can supply only periodic responses, an offline import can still provide useful coverage with an explicit last-received date.

**Assessment:** high confidence that the current Granicus crawling route is unsuitable; medium confidence that digital proceedings can be obtained; low confidence that a complete per-member export is available until staff confirms it.

## Racine

### Closest fit with the existing collector

Racine's Clerk page links its legislative calendar. The city's hosted board directory also identifies the Common Council and links to `cityofracine.legistar.com`. The portal therefore has an official provenance chain. Granicus's public Legistar examples document read-only API access and explain that clients can require tokens. Its support documentation explicitly offers API setup assistance when supplied with the jurisdiction and InSite URL. [^13][^15][^16][^17]

The official portal's robots file returned 404 during the policy check. A missing robots file is not a scraping prohibition and does not require a permission request. A bounded API check using the official portal's `cityofracine` identifier returned the Common Council as body 138, 152 council office records, the vote vocabulary and 15 current person records. Names and office terms match the public InSite roster. [^14][^32][^35]

Both a one-row current meeting query and a one-row historical query returned HTTP 400: agenda draft/public-visibility settings are not configured. This is a server configuration failure, not a request for permission or a missing-record response. Do not enable a tenant that cannot list its meetings or turn this error into an empty successful import. The checks used the identifying client and a two-second request floor; captures remain private. [^34]

After tenant and data validation, Racine should use the same Legistar collector and importer as Milwaukee, Madison, Appleton, Waukesha and West Allis. This is the lowest additional implementation effort among these three cities. A different importer for Racine would duplicate existing work.

### Keep website and API rules separate

Racine's website terms begin with permission to download information for certain noncommercial purposes, while a later section restricts republishing website content in software and accessing the site to create or distribute tools for systematic collection. These statements must be read together. A general download permission does not erase the more specific restrictions. [^18]

The reviewed wording refers to the website. The page alone does not establish that its restrictions govern the separately documented Legistar API. Review rules actually attached to that API and its tenant; do not invent a permission requirement from silence. No explicit prohibition specific to the proposed public API route was identified in this review. That supports proceeding to route validation, not treating an unverified tenant as ready for production.

Granicus also publishes corporate-site terms and separate contractual/product documents. Do not assume a corporate website's private-use language governs every municipal record, or that a general service agreement is Racine's executed contract. Apply relevant published restrictions to the actual delivery channel. [^19][^20]

### District identities resolved

The hosted Common Council directory lists fifteen members, but two entries are labeled “Alder 10.” It also lists a general meeting time that differs from an indexed 2026 meeting page. These are directory inconsistencies, not proof that two people legally occupy the same district or that a particular meeting notice is wrong. They show why live event records and verified office records must take precedence over assumptions based on a directory. [^15][^28]

The city's alderman directory and district 12 page resolve the conflict: Sam Peete is district 10 (API person 859), and Rocco DeMark is district 12 (API person 1061). All 15 current API identities now have reviewed entries in the shared `local_seats.json`; a regression test protects that distinction and rejects a same-name unknown ID. Existing city mappings are unchanged. These prepared entries do not activate collection. [^32][^33]

### Recommended next action

The API identifier and current roster are ready. A technical support inquiry can now identify the failing documented endpoint, its HTTP 400 response, body 138 and the working metadata routes. Ask the city or Granicus to repair the public agenda-visibility configuration; no separate scraping permission is needed for the documented public API. No inquiry has been sent.

After meeting retrieval works, validate two recent meetings including a contested roll call and a voice or consent action. The published vocabulary uses uppercase `YES`, `NO`, `PRESENT`, `ABSENT`, `EXCUSED`, `ABSTAIN`, `NON VOTING` and `RECUSED`. Shared display/counting logic must recognize these while retaining the original stored values; this remains unimplemented until real vote samples can be checked. Then add the registry entry with bounded backfill and the existing policy-review process. [^32]

A public InSite reader is another technical option, but would need its own meeting discovery, stable identity, paging and vote-completeness validation. An accessible calendar alone does not prove that this alternative preserves the API's records. Keep it separate from the existing API collector rather than silently switching formats after errors.

**Assessment:** roster preparation is complete; activation is blocked by a reproducible meeting API error and the resulting inability to validate vote samples. This is a technical dependency, not pending access clarification.

## Public-records route and cost

Wisconsin DOJ's public-records guidance distinguishes obtaining existing records from demanding a new service. It discusses access to electronic copies, limits on requiring new compilations, and the reasonableness of database extraction. It also states that prospective continuing requests are not required. A recurring API or automatic monthly delivery should therefore be proposed cooperatively, separately from a request for records already held. [^21][^22]

DOJ's March 2026 correspondence reiterates that a reasonable data run may be appropriate, but the authority generally need not create a new record or answer questions when no responsive record exists. Ask for existing reports and native exports, with flexibility about their current format. An inquiry about API support and a records request serve different purposes; label them separately. [^22]

The open-meetings recordkeeping duty also does not guarantee a downloadable per-person table. DOJ explains that motions and roll-call votes must be recorded and preserved, but written minutes are not the only permissible medium. Other rules may impose additional obligations on a particular body. An unavailable CSV is not evidence that a city has failed to keep records. [^29]

The principal cost risks are staff time, export preparation and manual verification, rather than SQLite storage. Wisconsin DOJ's fee guidance permits certain actual, necessary and direct costs, with restrictions on location charges and other fees. Fees vary by authority; DOJ's own copying schedule is not the cities' price list. Green Bay's notice identifies its local fee categories. Request an estimate and public-interest waiver, and authorize no charges in the initial inquiry. [^25][^30]

| Delivery route | Recurring demand on the source | Project work | Cost decision |
| --- | --- | --- | --- |
| City-published structured export | One small index and changed files after publication | Shared export reader and validation | Preferred if included in existing city tooling |
| Public Legistar API within applicable rules | Paged indexes plus requests for new or revised records | Existing collector with city configuration | Preferred for Racine after route and identity validation |
| Clerk-supplied electronic bundle | No automated load on the records website | Receipt tracking, offline parsing and review | Useful interim route; confirm any preparation charges |
| Approved minutes-only retrieval | Few documents, but potentially substantial parsing review | Shared document reader plus layout handling | Use only when it preserves adequate evidence |
| Recording/transcript extraction | Large transfers and costly verification | Audio/video processing and uncertain attribution | Poor initial fit for the project's accuracy and cost goals |

These comparisons are engineering judgments, not vendor quotations. No new paid service is needed to receive files, store an archive and import it into the existing SQLite pipeline. A paid connector, vendor module or managed scraper would need a separate cost decision and should not be assumed necessary.

Do not turn a nightly scheduler into a nightly rescan of an unchanged archive. Prefer publication-triggered updates or a small permitted index check, stable file hashes, conditional requests where supported and bounded backfill. A failed or denied fetch must leave the last valid archive intact. The existing request intervals are a starting constraint, not permission to send that volume to a new source; use any longer limit the operator supplies.

## Reusable implementation and validation

The design should remain **one shared municipal data model and importer, with readers for verified source formats**. Racine can reuse the Legistar reader. Green Bay now uses one CivicClerk reader; Kenosha may need a structured-export reader or a document reader after sample review. City-specific settings belong in the registry and verified identity tables. Avoid inventing a general connector framework before the actual inputs are available.

A non-Legistar reader should preserve its native source keys and provenance rather than manufacture a response that appears to have come from the Legistar API. Where documents have no member IDs, create a reviewed mapping to term-specific roster identities and retain the original names and page references. Unknown or ambiguous identity remains unresolved.

The receiving contract should account for the following distinctions:

| Record | Evidence to retain | Acceptance condition |
| --- | --- | --- |
| Meeting | Source ID or document identity, date, council body, approval state, source URL and file hash | No silent replacement of an approved record by an incomplete fetch |
| Motion/action | Item identity, exact wording, outcome, sequence and any consent-group relationship | Committee recommendations remain distinct from council decisions |
| Individual vote | Motion, source person identity, original position and evidence location | A named recorded vote or an explicit, verified complete roll call |
| Aggregate result | Recorded totals and any statement of unanimity | Retained separately from per-member positions; never filled from attendance |
| Membership | Person identity, district or role, effective dates and authoritative basis | Ambiguities and conflicting districts stop attribution |
| Coverage | Requested and received period, complete/partial status, last successful receipt | A partial sample cannot replace full history or be presented as complete |

Aggregate results may require a small extension to the shared model before a minutes-only city can be represented faithfully. That would preserve information the current per-person view cannot express; it should not be implemented by inventing individual votes or weakening the existing integrity checks.

For each sample, compare the imported data with the official record, including a contested action, voice/consent action, absence or recusal where present, and an amended or corrected record if available. Include an office turnover when testing historical identities. Verify counts, source IDs, original vote labels, body identity and all unresolved positions.

Then run the existing-city parity comparison on an isolated database: every pre-existing local record must be unchanged. Only after that succeeds should the city enter a bounded community-stage backfill. Retain original inputs privately, expose collection gaps in the site and API, and keep source retrieval separate from database import and static builds.

## Optional inquiry when the public route is unsuitable

The following is an unsent fallback template, not a prerequisite for collecting from an unrestricted public route. Use it for blocked access, missing records or a specific unresolved policy conflict. Use current contact details from the official department page and request an initial sample rather than an entire archive.

> Subject: Existing Common Council vote records and approved electronic access
>
> Badger Politics is an independent, noncommercial civic information project that publishes attributed Wisconsin government voting records. We would like to include your Common Council while respecting your access rules and keeping requests infrequent.
>
> As an initial records request, please provide existing electronic minutes, recorded motions, individual roll-call vote records and attendance records for Common Council meetings held in January 2026, together with the council roster and office terms covering those meetings. Please include existing source identifiers and public document links where available.
>
> An existing CSV, JSON, XML or other native export is preferred if readily available; original electronic minutes are also useful. We are not asking you to create a new application or report. If the records are already available through a permitted public export or documented API, please identify that route.
>
> Separately, can you confirm the approved method and limits for receiving future published records, and any applicable conditions on caching and republishing the factual records with attribution, including static data exports? Production processing would use deterministic code, with no model training or runtime AI features. Development uses AI-assisted coding; please identify any restrictions relevant to source content used in development or testing.
>
> Please advise before incurring any charge; no fees are authorized by this request. We request electronic delivery and consideration of a public-interest fee waiver. If another office holds these records, please identify the appropriate custodian.

| Recipient | Additional question |
| --- | --- |
| Green Bay Clerk; IT/data governance as needed | Can an existing Select Analytics view export individual votes, and can that dataset be published under the city's open-data program? Is Public Portal Voting History enabled? |
| Kenosha Clerk/Treasurer | Does the source system retain individual positions beyond the published narrative minutes, and can those existing records be exported or supplied directly? |
| Racine Clerk; IT/Granicus as needed | Can the public agenda-visibility configuration for `cityofracine` be repaired? `Bodies` and `OfficeRecords` work, but `Events` returns HTTP 400 for missing draft/public agenda settings. |

Record any supplied route, conditions, technical limits and cost before changing source configuration. An unanswered request for an exception does not override an existing explicit restriction. When no applicable prohibition exists, an unanswered inquiry is not itself a reason to block public collection. No correspondence is sent automatically.

## Evidence limits and status

Evidence was reviewed on September 8, 2026, America/Chicago. Policy and live API checks continued into September 9 UTC. A fresh Kenosha city-host policy request still returned 403; its cause remains unknown. Raw responses and audit output remain private.

No authenticated staff console, unpublished record endpoint or restricted archive was inspected. Indexed record examples identify format risks but are not a completeness audit and were not imported. Green Bay's public API fields and sampled votes are verified; staff exports and optional Voting History activation were not needed. Kenosha's underlying system and structured vote availability remain unverified. Racine's public metadata and roster were checked directly; meeting and vote completeness could not be tested because its event endpoint fails.

The recommendations apply the project's collection standard: review applicable explicit restrictions without requiring affirmative permission merely because policies are silent. They do not decide the enforceability of website terms. No correspondence has been sent, no records request filed and no new collector enabled as a result of this memo.

## Sources

[1]: https://www.greenbaywi.gov/OpenData
[2]: https://www.civicplus.help/meetings-select/docs/analytics-overview
[3]: https://www.civicplus.help/meetings-select/docs/view-motions-and-votes-on-the-public-portal
[4]: https://www.greenbaywi.gov/129/Meetings-Agendas-Minutes
[5]: https://www.greenbaywi.gov/clerk
[6]: https://www.greenbaywi.gov/617/Common-Council
[7]: https://www.civicplus.help/legal-center/docs/civicplus-terms-of-use
[8]: https://www.kenosha.org/robots.txt
[9]: https://kenosha.granicus.com/robots.txt
[10]: https://www.rfc-editor.org/rfc/rfc9309.html#section-2.3.1.3
[11]: https://www.kenosha.org/Document%20Center/Departments/City%20Clerk%20Treasure/Public%20Records/public_record_request.pdf
[12]: https://apps.kenoshacounty.org/KARL/Programs/Kenosha_City_ClerkTreasurer/
[13]: https://cityofracinewi.gov/Clerk/
[14]: https://cityofracine.legistar.com/robots.txt
[15]: https://cityofracine.granicus.com/boards/w/cf1d7b8b8a0361db/boards/28044
[16]: https://webapi.legistar.com/Home/Examples
[17]: https://support.granicus.com/articles/en_US/Knowledge/Troubleshooting-Common-Legistar-Issues
[18]: https://cityofracinewi.gov/termsofuse/
[19]: https://granicus.com/trust-center/terms-of-use/
[20]: https://granicus.com/legal-licensing/
[21]: https://www.wisdoj.gov/Open%20Government/PRL_guide.pdf
[22]: https://www.wisdoj.gov/Open%20Government/2026%20Q1%20CORR%20Summary_Final.pdf
[23]: https://support.granicus.com/articles/Knowledge/Working-with-Legistar-and-LiveManager
[24]: https://www.civicplus.help/meetings-essential/docs/public-application-programming-interface-api
[25]: https://www.greenbaywi.gov/DocumentCenter/View/154/Public-Records-Policy-PDF?bidId=
[26]: https://kenosha.granicus.com/DocumentViewer.php?file=kenosha_295005436171b37e8fa36b4fafa661b1.pdf&view=1
[27]: https://kenosha.granicus.com/DocumentViewer.php?file=kenosha_ddf6b78188039e95e668eb9cb9089dc2.pdf&view=1
[28]: https://cityofracine.legistar.com/MeetingDetail.aspx?GUID=7BC27687-BCF7-4075-A45E-3221523B2A18&ID=1362885&Options=info%7C&Search=
[29]: https://www.wisdoj.gov/Open%20Government/2024%20Q4%20CORR%20Summary_Final.pdf
[30]: https://www.wisdoj.gov/Pages/AboutUs/public-records.aspx
[31]: https://www.greenbaywi.gov/CivicAlerts.aspx?AID=31&ARC=177
[32]: https://webapi.legistar.com/v1/cityofracine/OfficeRecords?$filter=OfficeRecordBodyId%20eq%20138
[33]: https://cityofracinewi.gov/government/city-leadership/common-council/cityalderman/district-12/
[34]: https://webapi.legistar.com/v1/cityofracine/Events?$top=1&$filter=EventBodyId%20eq%20138%20and%20EventDate%20lt%20datetime%272026-09-01%27&$orderby=EventDate%20desc
[35]: https://cityofracine.legistar.com/DepartmentDetail.aspx?ID=27510&GUID=8134A3C9-877C-4F05-9E7C-9D3AA5F02106&Mode=MainBody

[^1]: City of Green Bay. [Open Data][1]. Undated policy and service-standard page; reviewed September 8, 2026. Program goals, formats, data stewardship and vendor-held records.
[^2]: CivicPlus. [Analytics Overview][2]. Updated January 13, 2026. Meetings Select CSV/XLSX export capability; no verified Green Bay vote-field inventory.
[^3]: CivicPlus. [View Motions and Votes on the Public Portal][3]. Updated November 14, 2025. Voting History feature and Support enablement requirement.
[^4]: City of Green Bay. [Meetings, Agendas & Minutes][4]. Current official portal referral.
[^5]: City of Green Bay. [Clerk][5]. Current office responsibilities and contact route.
[^6]: City of Green Bay. [Common Council][6]. Current district roster and minutes-approval statement.
[^7]: CivicPlus. [Terms of Use][7], sections 2–3, 5 and 7–8. Page updated August 28, 2026; text states last revised March 20, 2026. Both dates are reported without inferring which reflects a substantive amendment.
[^8]: City of Kenosha. [robots.txt][8]. Prior direct response on September 8, 2026: HTTP 403. This is an observation, not published permission language.
[^9]: Kenosha Granicus records host. [robots.txt][9]. Direct policy-only observation September 8, 2026: HTTP 200, wildcard disallow-all. Normalized SHA-256: `ac520e96489c10c6864a2b2fcc4a21120f954baa06b6e544a7ecdcc9eb8fff05`.
[^10]: IETF / RFC Editor. [RFC 9309, Robots Exclusion Protocol][10]. September 2022, section 2.3.1.3. Protocol handling of unavailable robots files.
[^11]: City of Kenosha Clerk/Treasurer. [Public Records Request, CLKPRR][11]. Form revision November 2017; search-indexed official copy. Email delivery and document-request route; fees not verified as current.
[^12]: Kenosha County ADRC. [Kenosha City Clerk/Treasurer][12]. Updated February 19, 2026. Official service-directory confirmation of the city office and its records/meeting role.
[^13]: City of Racine. [Customer Service, City Clerk & Treasurer][13]. Current department page, public-records role and legislative-calendar link.
[^14]: Racine Legistar host. [robots.txt][14]. Direct policy-only observation September 8, 2026: HTTP 404. Subsequent API checks are documented in notes 32–35.
[^15]: City of Racine / Granicus. [Common Council board directory][15]. Current displayed fifteen-member roster; two district-10 labels and general meeting information.
[^16]: Granicus. [Legistar Web API Examples][16]. Current public documentation, version displayed 26.4.2.0. Read-only examples and client token policy.
[^17]: Granicus Support. [Troubleshooting Common Legistar Issues][17], “I want to use the API.” Undated support article reviewed September 8, 2026. Jurisdiction/InSite-based API setup route.
[^18]: City of Racine. [Terms of Use][18]. Undated; reviewed September 8, 2026. Download permission and specific website collection/republishing restrictions.
[^19]: Granicus. [Terms of Use][19]. Undated corporate-site terms; applicability to a municipal tenant not presumed.
[^20]: Granicus. [Legal contracts][20]. Current agreement and product-term directory; not evidence of either city's signed contract.
[^21]: Wisconsin Department of Justice. [Wisconsin Public Records Law Compliance Guide][21]. June 2025; printed pages 14–16 and 65–66. Request form, prospective requests, electronic copies and format limits.
[^22]: Wisconsin Department of Justice. [2026 First Quarter Correspondence][22]. March 2026 letters; PDF pages 9–11 and 18–19. Existing records, reasonable data runs, requested formats and requests versus questions.
[^23]: Granicus Support. [Working with Legistar and LiveManager][23]. Undated technical guide reviewed September 8, 2026. Product workflow only; not proof of Kenosha's configuration.
[^24]: CivicPlus. [Meetings Essential Public Application Programming Interface][24]. Updated November 14, 2025. Different product and token-based access; not a Select API authorization.
[^25]: City of Green Bay. [Public Records Notice][25]. Undated current linked PDF. Custodian routing, methods and fee categories.
[^26]: City of Kenosha. [Common Council agenda, January 21, 2026][26]. Search-indexed official record. Minutes attachment and committee-recommendation format; no full archive review.
[^27]: City of Kenosha. [Common Council proceedings, January 17, 2024][27]. Search-indexed official record. Narrative roll-call example; historical, not a current-schema guarantee.
[^28]: City of Racine. [Common Council meeting, April 20, 2026][28]. Indexed official meeting page, 6:00 p.m.; contrasts with generic directory schedule.
[^29]: Wisconsin Department of Justice. [2024 Fourth Quarter Correspondence][29]. PDF discussion of Wis. Stat. § 19.88(3). Recordkeeping may use media other than written minutes.
[^30]: Wisconsin Department of Justice. [Public Records][30], fee guidance. Current overview reviewed September 8, 2026; authority-specific costs rather than a city price quotation.
[^31]: City of Green Bay, Mayor's Office. [City Launches New Website and Agenda Management System][31]. April 19, 2018. Historical archive announcement; not evidence of current structured completeness.
[^32]: City of Racine / Granicus. [Common Council office records][32], `Bodies`, `VoteTypes` and current `Persons/{id}` routes. Direct identifying-client review September 8, 2026: body 138, 152 office records and 15 current identities. Districts checked against the [official alderman directory](https://cityofracinewi.gov/government/city-leadership/common-council/cityalderman/). Raw responses retained privately.
[^33]: City of Racine. [District 12, Alderman Rocco DeMark][33]. Current official page reviewed September 8, 2026. Resolves the hosted board directory's duplicate district-10 label.
[^34]: City of Racine / Granicus. [Date-bounded Common Council event query][34]. Direct identifying-client observation September 8, 2026: HTTP 400, missing agenda-visibility configuration. A separate current-event query returned the same error; no meeting records received.
[^35]: City of Racine / Granicus. [Common Council InSite roster][35]. Current official public roster reviewed September 8, 2026. Confirms API names and office terms; InSite IDs differ from API IDs.

[^36]: [Green Bay's published CivicClerk OData schema](https://greenbaywi.api.civicclerk.com/v1/$metadata), reviewed with the public EventCategories response identifying Common Council as category 26.
[^37]: [July 21, 2026 public meeting API record](https://greenbaywi.api.civicclerk.com/v1/Meetings/9275), 42 motions and 504 named positions in nested items.
[^38]: [August 18, 2026 public meeting API record](https://greenbaywi.api.civicclerk.com/v1/Meetings/9276), 33 motions and 396 named positions in nested items.
[^39]: [Green Bay: William Morgan, district 3](https://www.greenbaywi.gov/627/William-Morgan), confirms the Bill/William Morgan identity used in the official roster and votes.
[^40]: [July 21 meeting files](https://greenbaywi.portal.civicclerk.com/event/9722/files), published minutes file 31062. The documented API file function supplied the download URL; the file was checked locally without publishing the temporary URL.
[^41]: [Green Bay API robots](https://greenbaywi.api.civicclerk.com/robots.txt), 404; [portal robots](https://greenbaywi.portal.civicclerk.com/robots.txt), 200 with no disallow rules. Reviewed September 8, 2026 local time.
[^42]: [Green Bay city robots](https://www.greenbaywi.gov/robots.txt), 200; `/617/Common-Council` is permitted for the identifying project client. Reviewed September 8, 2026 local time.
