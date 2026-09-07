# Records request: Wisconsin Ethics Commission

## Access status

A request was sent on 2026-08-24. No response or authorization is recorded
in this repository. Keep sent correspondence, sender details, and replies
in private project records. Review current source policies before
collection; a sent request does not establish permission.

## Request template

Recipient: ethics@wi.gov

Subject: Public records request: candidate committee registrant data

Dear Wisconsin Ethics Commission staff,

I'm building Badger Politics (badgerpolitics.org), a free, independent,
noncommercial website that helps Wisconsin residents follow the
Legislature. It will present campaign finance data from CFIS with links
back to campaignfinance.wi.gov on every figure. This is a public records
request under Wis. Stat. § 19.35, though I suspect much of it is data
you can export routinely.

1. **Registrant extract.** For all registered candidate committees
   (current and historical, electronic era): committee/filer ID as used
   in CFIS, committee name, candidate name, office sought, district, and
   registration status. A CSV or any machine-readable export is ideal.
   Purpose: verifying committee-to-candidate attribution so my site
   never links a contribution to the wrong person. The CFIS website's
   search shows committee names but not the candidate/office fields,
   which is why I'm asking.

2. **Filed report summaries (if exportable).** Per committee, per filing
   period: report ID, period covered, and the cover-sheet totals (total
   receipts, total disbursements, cash on hand). Purpose: reconciling my
   itemized sums against committees' own filed totals as an accuracy
   check.

3. **CFIS automated retrieval.** Separately from the records request: to
   keep the site current, I would like to run a nightly job that
   retrieves contribution records for sitting legislators' committees
   from campaignfinance.wi.gov, using the same JSON endpoints the
   website itself loads data from (/api/trpc/...), at low volume —
   roughly one paged, throttled pull per day, with an identifying
   User-Agent linking to the project contact page. Since those endpoints aren't
   formally published, I want to ask before making that routine: would
   something like that be acceptable to the Commission, and is there a
   preferred method — a bulk export, the site's spreadsheet downloads,
   or a different schedule — that would be easier on your
   infrastructure? I'm happy to use whatever you prefer.

4. **Eye on Lobbying retrieval.** Same question for lobbying.wi.gov: the
   site will display which principals registered on each bill, and I
   would like to retrieve that nightly at low volume with the same
   identifying User-Agent. Would that retrieval be acceptable, and is
   there a preferred method or schedule? I'm happy to adjust frequency,
   timing, or mechanism to whatever suits your infrastructure.

I'm glad to accept whatever format is least work for your staff, and to
pay reasonable location/copying costs as provided by statute. Thank you
for maintaining these systems; the transparency they provide is the
foundation my site is built on.

Best regards,
{requester name}
badgerpolitics.org
