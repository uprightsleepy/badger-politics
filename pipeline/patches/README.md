# patches/

Runtime patches applied to the pinned openstates-scrapers submodule working
tree by `scraper/scrape.py` (via `git apply`, idempotent). The pinned commit
is never edited in-tree; each patch documents its upstream intent here.

| Patch | Upstream intent |
|---|---|
| `0001-wi-events-fixes.patch` | Two `WIEventScraper` fixes, to be submitted as one PR to openstates/openstates-scrapers: (1) committeeschedule.legis.wisconsin.gov now emits `title: "..."` with double quotes while every other field uses single quotes; `extract_field`'s regex only matched single quotes, so every event's title extracted as `None` and the scrape crashed at `re.match(chamber_regex, title)` (scrapers/wi/events.py:64) — the regex now accepts either quote style. (2) Defensive guard: skip (with a warning) any schedule row still missing title or start instead of crashing. |
| `0002-wi-bills-house-not-voting-marker.patch` | `WIBillScraper.add_house_votes` recognizes not-voting members by a cell containing `NV`, but docs.legis Assembly roll call pages mark them with a lowercase `x` (e.g. 2025 av0001: header says `NOT VOTING - 1`, the member's row marks column 3 with `x`). Every Assembly vote therefore silently dropped its individual not-voting records — the yes/no invariants passed while NV names were lost. The patch accepts `NV`/`x`/`X` and extends the scraper's own count invariant to not-voting names so this class of drift raises instead of dropping data. To be submitted upstream with 0001. |
