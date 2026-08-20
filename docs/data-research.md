# Research: free public data about Wisconsin legislators

Researched 2026-08-20. Each source is rated for cost, access mechanism,
reuse terms, and fit with the hard rules (free, keyless where possible,
static-servable, provenance-clean).

## Tier 1: free, machine-readable, automatable

### Lobbying activity — Eye on Lobbying (lobbying.wi.gov)
The Ethics Commission's disclosure site. Principals must report **every bill
they lobby on** within 15 days, plus semiannual dollars and hours spent.
Coverage back to the 2003-04 session.
- Direct Excel exports exist per session, e.g.
  `/What/WhatAreTheyLobbyingAbout/2025REG/ReportExport?outRpt=Excel` (by
  principal, total dollars, total hours), plus a per-bill legislative
  matter search.
- **Product fit: the single highest-value addition.** A "Who lobbied this
  bill" section on every bill page (organizations, for/against where
  reported, dollars) and a lobbying rollup per session. No other free WI
  site pairs roll calls with lobbying interest per bill.

### Campaign finance — CFIS "Sunshine" (cfis.wi.gov)
Transaction-level receipts and disbursements for every state candidate
committee, July 2008 to present. Transaction search exports to
spreadsheet, reports are public immediately on filing. Free.
- **Product fit:** the plan's backlog item 7 (`/money/` module): per-
  legislator fundraising totals, top donors, cash on hand. A large build
  (committee-to-legislator mapping, dedupe) but the data is free and
  comprehensive.

### Election results — WEC (elections.wi.gov)
Official results archive with ward-by-ward spreadsheets per election.
- **Product fit (quick win):** per-legislator electoral history on their
  page: last margin, "won by 3.2 points in 2024". Also pairs with the
  district GeoJSON for margin maps later.

### Salary — statutory (uniform)
$60,924/year for the 2025-26 session, set under s. 20.923 via the Joint
Committee on Employment Relations. Uniform for every member, so it is a
fact line, not per-member data. Historical salaries per biennium are in
the Blue Book.
- **Product fit (trivial):** a "Compensation" line on legislator pages:
  salary + the per-diem rates their chamber allows (Assembly $171
  overnight / $85.50 day; Senate $140, halved for Dane County members).

### District demographics — Census ACS
Free API (keyless at low volume; a free key removes limits) with state
legislative district geographies.
- **Product fit:** district profile boxes (population, median income,
  urban/rural) on legislator pages. Nightly-cacheable, tiny.

## Tier 2: free but manual (annual records, not posted as data)

### Per diems — chamber chief clerks
The differentiating compensation data: each member chooses how many days
to claim. 2025 totals: $1.17M claimed across the Assembly, $397K across
the Senate. The clerks' per-member records are public but are released
via records request (The Badger Project publishes annual roundups from
them; their articles are reporting, not a dataset we can take).
- **Product fit:** an annual records request to both chief clerks (free),
  imported as `source='manual'` with the response letter archived. Adds a
  per-member "per diem claimed" line next to salary. Yearly cadence,
  ~one hour of maintenance.

## Tier 3: not compatible with our rules

### Statements of Economic Interests — Ethics Commission
Public but request-gated: the requester files a form with name, address,
and phone, and **the official is notified who requested their statement**.
No bulk or anonymous access. The Wisconsin Democracy Campaign publishes
summaries, but that is their work product, not free data.
- **Decision: link out** to the Ethics Commission's SEI page from
  legislator pages; do not mirror.

## Zero-new-source wins (compute from our own database)

- **Votes with party %** per legislator per session (roll calls joined
  with party) — presented as a plain number, no grades, per the
  nonpartisan posture.
- Missed-vote counts already power the attendance heatmap; the same
  query can rank per session.

## Suggested order

1. Salary + per-diem-rate fact line (an afternoon).
2. Election margin history from WEC results files (a day).
3. Votes-with-party stat (hours).
4. "Who lobbied this bill" from Eye on Lobbying exports (the big one;
   needs export-format reverse engineering and a name-matching pass for
   principals).
5. Annual per-diem records request (recurring manual).
6. `/money/` from CFIS (a phase of its own; already on the backlog).
