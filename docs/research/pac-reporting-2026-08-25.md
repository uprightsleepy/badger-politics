# PAC reporting: feasibility research — 2026-08-25

Research only; nothing implemented. Question: can we surface PAC money
without breaking our rules (static site, ~$2/mo, bulletproof attribution,
no source we lack permission to store)?

**Verdict: highly feasible, and cheaper than expected — the data already
flows through our nightly fetcher and we discard it.**

## 1. What we already have

| | Count | Amount |
|---|---|---|
| PAC/committee → legislator receipts (`from_type='Registrant'`) | 9,916 | $21,292,767 |
| Distinct committee donors named | 1,610 | — |
| Conduit pass-throughs | 52,521 | $4,317,509 |

So we already answer *"which committees funded this legislator."* What we
cannot answer today:

- **Who funds the PAC** (its own receipts)
- **What the PAC spends** and on what
- **Independent expenditures** for or against named candidates
- **What a PAC is** — we store the donor's name but not its registration
  type, so a party committee, a conduit, and a corporate-sponsored PAC all
  look alike

## 2. The key finding: no new data source is needed

`scraper/fetch_cfis.py` calls `publicFrontendApi.getTransactions` for a
**date window, not a committee**. Every transaction filed statewide in that
window is already downloaded. We then drop rows two ways:

```python
if not person_id:            continue   # filer isn't a mapped legislator
if direction != "INCOMING":  continue   # discards every disbursement
```

PAC receipts, PAC disbursements, and independent expenditures are all in
the response we already fetch and parse. Capturing them costs **zero
additional HTTP requests** and no new endpoint — the marginal cost is
SQLite rows, not bandwidth or API surface. This matters directly for the
$2/mo ceiling and for the pending permission question (§5): we would not be
asking the Commission for anything beyond what we already retrieve.

## 3. Committee taxonomy is available and precise

`entity.searchEntities` returns, per committee entity:

```json
"committee": {"id": 48877, "assignedCommitteeId": "0501646",
              "committeeType": {"name": "PAC"}}
```

Sampled 400 committees; the full type landscape:

| Type | Sampled | Why it matters |
|---|---|---|
| State Candidate | 189 | what we track today |
| **PAC** | 66 | the core ask |
| Political Party | 39 | party → candidate transfers |
| Sponsoring Organization | 31 | the corporation/union behind a PAC |
| **Conduit** | 20 | earmarked pass-throughs; we hold 52k of these blind |
| **Independent Expenditure Committee** | 19 | unlimited outside spending |
| Federal Candidate | 16 | out of scope |
| Unregistered Express Advocacy | 10 | ad hoc spenders |
| Referendum | 5 | ballot-question committees |
| Legislative Campaign Committee | (seen) | caucus committees |

`assignedCommitteeId` is CFIS's own stable ID — an exact join key, matching
our existing entity-id-not-name attribution rule.

## 4. Independent expenditures are the standout

Transaction rows carry fields we currently ignore entirely:

- `supportStance` — **`FOR` / `AGAINST`**
- `relatedEntity` — the candidate targeted
- `relatedOffice`, `relatedDistrict`, `relatedBranch` — the race
- `finalRecipient` — the true recipient behind a conduit
- `communicationDate`, `transactionPurpose`, `comment`

In a single 1,000-row sample: 27 rows carried a stance (24 FOR, 3 AGAINST),
with filer types including Independent Expenditure Committee and
Unregistered Express Advocacy, targeting State Senate and State Assembly
races. Verified example: $5,387.50 **FOR** a named State Senate candidate.

This is the piece no one surfaces well for Wisconsin: *money spent for or
against a candidate by someone other than the candidate*. It is also the
money least visible to voters, because it never appears in the candidate's
own filings — which is exactly why our current pages can't show it.

## 5. Rules and permission

- **The data is public record.** CFIS exists to publish it; the Wisconsin
  Democracy Campaign has republished the same filings for decades.
- **Same endpoints, same posture** as our existing ingest: unauthenticated
  GETs the site itself makes, identifying User-Agent, throttled, archived
  locally so the importer reads archives rather than the live API.
- **Permission is already in flight.** The records request sent to
  ethics@wi.gov on 2026-08-24 explicitly asks whether nightly automated
  retrieval from campaignfinance.wi.gov is acceptable and whether they
  prefer another mechanism. PAC data needs no *additional* ask — it is the
  same retrieval already described.
- **No ToS blocker identified**, but the endpoints remain undocumented, so
  the honest posture is unchanged: fail-loud drift alarms, and the UI's own
  spreadsheet exports as the fallback path.

## 6. Accuracy limits to state on any page we build

- **Itemization thresholds** mean small contributions are aggregated, not
  named. A PAC's donor list is therefore its *itemized* donors, never all
  of them. Exact threshold not pinned down in this pass — **needs
  confirmation** against Wis. Stat. ch. 11 before any "all donors" wording.
- **Registration thresholds** mean spending below the trigger never
  appears at all (independent expenditure committees register after
  $2,500/yr of activity, per the Ethics Commission's IE overview).
- **72-hour reports** near elections arrive out of band; a nightly pull
  will lag them by up to a day, which our freshness wording already covers.
- **Conduits** pass money from individuals to candidates; attributing a
  conduit's total to the conduit itself would misstate who gave. The
  `finalRecipient` field exists precisely for this and must be used.

## 7. Recommended scope, in order

1. **Label what we already show.** Add `committeeType` to committee donors
   so "Wisconsin Realtors PAC" reads as a PAC and a party transfer reads as
   a party. Cheapest change; pure enrichment of existing rows.
2. **PAC profile pages.** Receipts in, disbursements out, top donors,
   recipients — one page per registered PAC above a materiality floor,
   mirroring the existing donor-committee pages.
3. **Independent expenditure tracking.** FOR/AGAINST by race and candidate,
   surfaced on legislator and election pages. Highest voter value; also the
   most care required, since "spent against" is a claim we must source
   precisely.
4. **Conduit transparency** using `finalRecipient`, so 52,521 pass-through
   rows stop being anonymous plumbing.

## 8. Open questions

1. Confirm the itemization threshold in Wis. Stat. ch. 11 before any page
   implies a complete donor list.
2. Storage: capturing all directions statewide grows `contributions`
   substantially (we currently keep only legislator-inbound). Worth sizing
   before committing — it affects the 263 MB SQLite we now ship.
3. Does the Commission's reply (pending) suggest a bulk export we should
   prefer over the API?
