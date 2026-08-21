# Deep dive: campaign finance + org logos on legislator and bill pages

Researched 2026-08-20. Verdict up front: **highly feasible, no keys, no
paid services**, with one hard editorial constraint about how "who is
paying" must be framed (see Framing, below — read it first).

## 1. The data source: CFIS "Sunshine" has an open JSON API (verified live)

The new campaignfinance.wi.gov is a Next.js app over a tRPC API, and the
API answers plain HTTP GETs with an identifying User-Agent: no browser, no
key, no Cloudflare block (verified 200s from a bare script).

Verified endpoints (`/api/trpc/<procedure>?input={"json":{...}}`):

| Procedure | Verified behavior |
|---|---|
| `publicFrontendApi.getTransactions` | paginated (`take`/`skip`), sorted; each row has amount, date, comment, and full committee objects for filer and counterparty |
| `publicFrontendApi.getTransactionsTotalCount` | 13,140,331 transactions total, 1950 to today |
| date filtering | `dateFrom`/`dateTo` works (Jan 2026 alone = 57,295 rows), so nightly incremental sync is trivial |
| `entity.searchEntities` | name search scoped to committees; "Friends & Neighbors of Robin Vos" resolves to entity id 15594, type "State Candidate" |
| `transactionMeta.getTransactionCategories/Types/Purposes` | vocabulary for filtering receipts vs disbursements |

Sync design: initial backfill windowed by month for the current biennium
(and later, prior cycles), keeping only rows whose filer committee is one
of the ~132 sitting legislators' candidate committees. Nightly delta =
`dateFrom: yesterday`. Volume after filtering is tens of thousands of rows
per cycle: nothing for SQLite.

Committee-to-legislator mapping: `entity.searchEntities` per legislator
name plus a small curation table for odd committee names, same pattern as
the person-curation files. One-time cost, verified per entry.

Risk: this is an unofficial API for a public-records site. Mitigations:
drift alarms exactly like the WEC parser (fail loud on shape changes), and
the UI's spreadsheet exports as a fallback path. The data itself is public
record; we already follow the same posture for docs.legis.

## 2. Framing: what "paying for them" legally means in Wisconsin

**Corporations cannot contribute to Wisconsin candidate committees.**
Money reaching a legislator's committee comes from:

- individuals (name, and above thresholds employer/occupation, on record),
- PACs and other committees (often corporate- or union-sponsored),
- party and legislative campaign committees,
- conduits (pass-throughs of itemized individual money).

So a logo wall labeled "companies paying this legislator" would be
factually wrong and reputationally fatal for a trust-first site. The
correct, industry-standard presentation (what OpenSecrets does):

- **"Top contributing committees"**: PACs/committees by total, with the
  sponsoring organization's logo where the sponsor is unambiguous
  (WMC, unions, realtors, credit unions...).
- **"Top employers of individual donors"**: aggregated employer totals,
  clearly labeled with the standard methodology note: *totals reflect
  contributions from the organization's PAC, employees, and their
  families — not the organization itself.*
- Every number links back to the underlying transactions.

This framing must ship in the same commit as the feature, plus a
methodology section on /about.

## 3. Logos: free, keyless, build-time (verified)

- Name → domain: Clearbit's public autocomplete
  (`autocomplete.clearbit.com/v1/companies/suggest?query=...`) — free, no
  key, verified ("American Family Insurance" → amfam.com).
- Domain → icon: DuckDuckGo favicons
  (`icons.duckduckgo.com/ip3/<domain>.ico`) — verified 200; Google s2 as
  fallback.
- Fetched **at build time** and stored in site assets, so visitors never
  make third-party requests (keeps the privacy posture intact).
- PAC → sponsor-org mapping is a curation table (e.g. "WMC Issues
  Mobilization Council" → wmc.org), verified by hand like person merges.
- No match → clean monogram tile fallback; never guess a logo.
- Trademark note: favicon-scale marks used to identify the organization in
  factual reporting is classic nominative use; the monogram fallback also
  means we are never forced to use one.

## 4. Extending to bills: lobbying is the bill-scoped link (verified)

Campaign money attaches to legislators; **lobbying** attaches to bills.
Eye on Lobbying (lobbying.wi.gov, Ethics Commission):

- per-session Excel exports of principals with dollars and hours
  (`/What/WhatAreTheyLobbyingAbout/2025REG/ReportExport?outRpt=Excel`),
- per-matter pages listing every principal registered on a bill/topic
  (`/What/TopicInformation/2025REG/Information/<id>`), coverage back to
  2003, verified.

Bill pages can then show two honest org lists:
- **"Organizations lobbying this bill"** (direct, per-registration data,
  with for/against where the effort disclosure includes it), and
- optionally the sponsors' top funders (linked from the money data, with
  the same framing rules).

Per-matter scraping is ~one request per bill with a lobbying registration
(a fraction of bills); weekly cadence is plenty (15-day reporting window).

## 5. Suggested build plan

1. **Money ingest** (1 session): fetch_cfis.py (tRPC client with drift
   alarms), candidate-committee mapping table, contributions table,
   nightly delta in run.sh.
2. **Aggregation + legislator UI** (1 session): top committees / top
   donor employers cards with methodology labels, linked transaction
   drill-down via the static API.
3. **Logo pipeline** (1 session): org_domains curation + build-time
   favicon fetcher into site assets, monogram fallback component.
4. **Lobbying-per-bill** (1-2 sessions): session export ingest + per-
   matter scrape, lobbying tables, "Organizations lobbying this bill"
   on bill pages with the same logo component.
5. **Methodology page** (with step 2, non-negotiable).

Total: roughly four to five working sessions for the full vision, each
independently shippable, all free and keyless.

## Cross-checking the data

Sources evaluated against the project's API requirements (free,
keyless or free-key, machine-readable, clear reuse terms):

- **CFIS itself (in use).** Every fetched month reconciles exactly
  against the server's own transaction counts. A nightly rotating audit
  re-fetches three archived months and refreshes any that upstream
  amendments changed, so history never goes silently stale. Filed-report
  cover sheets would be a stronger check but are not in the public API.
- **FollowTheMoney API (qualifies, needs free key).** State legislative
  per-candidate totals from an independent pipeline over the same WEC
  filings. Same free-key model we accepted for the Census API. Once a
  key exists (FTM_API_KEY), a comparison harness can flag per-member
  divergence beyond a tolerance. Expect close-not-exact: cycle windows,
  refunds, transfers and unitemized lumps differ by methodology.
- **Wisconsin Democracy Campaign (excluded).** Their summaries are their
  work product, not free data (same call as the lobbying section above).
- **TransparencyUSA, Ballotpedia (manual only).** No API or no free API,
  no stated reuse terms. Fine for eyeballing a single legislator.
- **OpenSecrets API (not applicable).** Federal races only.
