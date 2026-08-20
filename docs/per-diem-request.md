# Annual per-diem records request (manual, once a year)

Per-member per diem claims are public records held by each chamber's chief
clerk. Send the request below each January for the prior calendar year,
save the responses under `pipeline/_data/manual/per-diems/<year>/`, and
import with `source='manual'`.

Recipients:
- Assembly Chief Clerk: contact listed at https://legis.wisconsin.gov/assembly/acc
- Senate Chief Clerk: contact listed at https://legis.wisconsin.gov/senate/scc

Template:

> Subject: Public records request: {YEAR} legislator per diem claims
>
> Dear Chief Clerk,
>
> Under Wisconsin's public records law (Wis. Stat. §§ 19.31-19.39), I
> request records showing the per diem payments claimed by each member of
> the {Assembly/Senate} for calendar year {YEAR}, itemized by member, with
> the number of days claimed and total amounts paid.
>
> I would appreciate the records in a machine-readable format (spreadsheet
> or CSV) if available. If any fees would exceed $25, please contact me
> before proceeding.
>
> This request supports badgerpolitics.org, a free, independent,
> nonpartisan public information site.
>
> Thank you,
> Henry ({email})

Notes:
- Both clerks have released these routinely (they are the source for The
  Badger Project's annual roundups), so expect a spreadsheet or PDF table.
- When the data arrives, record the date and file names here for
  provenance.
