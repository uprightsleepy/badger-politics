# patches/

Runtime patches applied to the pinned openstates-scrapers submodule working
tree by `scraper/scrape.py` (via `git apply`, idempotent). The pinned commit
is never edited in-tree; each patch documents its upstream intent here.

| Patch | Upstream intent |
|---|---|
| `0001-wi-events-fixes.patch` | Two `WIEventScraper` fixes, to be submitted as one PR to openstates/openstates-scrapers: (1) committeeschedule.legis.wisconsin.gov now emits `title: "..."` with double quotes while every other field uses single quotes; `extract_field`'s regex only matched single quotes, so every event's title extracted as `None` and the scrape crashed at `re.match(chamber_regex, title)` (scrapers/wi/events.py:64) — the regex now accepts either quote style. (2) Defensive guard: skip (with a warning) any schedule row still missing title or start instead of crashing. |
| `0002-wi-bills-vote-fixes.patch` | Two `WIBillScraper` vote fixes, to be submitted upstream with 0001: (1) `add_house_votes` recognizes not-voting members by a cell containing `NV`, but docs.legis Assembly roll call pages mark them with a lowercase `x` (e.g. 2025 av0001: header says `NOT VOTING - 1`, the member's row marks column 3 with `x`); every Assembly vote silently dropped its individual not-voting records — the patch accepts `NV`/`x`/`X` and extends the scraper's own count invariant to not-voting names. (2) `add_senate_votes` only parses the modern `table[@class="senate"]` layout; Senate roll-call pages before 2017 use a legacy layout (one table per vote type with `<strong>AYES - N</strong>` labels and nested name-column tables, e.g. 2015 sv0010) which crashed with `KeyError: 'yes'` — the patch adds a legacy-layout fallback keeping the same count-vs-names invariant. |
