# Historical Backfill — Coverage and Floor

Walked backward from the 2023-24 biennium (plan §5) on 2026-08-20. Result:

| Session | data_quality | Bills | Notes |
|---|---|---|---|
| 2025-26 (+May 2026 special) | full | 2,751 | current biennium, nightly |
| 2023-24 | full | 2,655 | |
| 2021-22 | full | 2,617 | |
| 2019-20 | full | 2,263 | |
| 2017-18 | full | 2,236 | |
| 2015-16 | full | 2,246 | pre-2017 legacy vote-page layouts (patches/0002) |
| 2013-14 | full | 2,255 | docs.legis membership listings begin here |
| 2011-12 | full | 1,584 | recall-wave biennium; roster from openstates legacy CSV |
| 2009-10 | **partial** | 1,985 | vote events carry official counts but docs.legis pages list no individual names (journal era) — no per-legislator records |

**The floor is the 2009-10 session.** Sessions before 2009 are not defined in
openstates-scrapers' WI jurisdiction (`ignored_scraped_sessions`), docs.legis
per-session legislator listings don't exist before 2013, and the openstates
legacy CSV era starts at 2009. Going earlier would require adding session
definitions upstream plus a new membership source (Blue Book), or the
LegiScan fallback (display-only rows). Not pursued.

## Membership sources by era

- **2013+**: docs.legis per-session listings (authoritative; includes
  mid-session replacements) unioned with openstates people-file term windows.
- **2009-2012**: openstates legacy CSV term rows (data.openstates.org),
  joined to modern identities via `legacy_openstates` identifiers;
  members absent from the modern people files are synthesized with
  `legacy/WIL...` ids.

## Manual curation tables (pipeline/importer/)

Every entry is human-verified with its basis recorded — never heuristic:

- `person_merges.json` — 7 duplicate openstates person records folded into
  canonical identities (an upstream 2015-era record split: Farrow,
  Fitzgerald, Lasee, Lassa, Olsen, Risser, plus Roys's Assembly/Senate arc).
- `person_aliases.json` — printed name forms the data files lack (maiden
  names on old roll calls: Harris/Harris Dodd, Pope-Roberts/Pope).
- `person_terms.json` — service terms all sources miss: Petrowski's and
  Shilling's Assembly stints before their mid-biennium Senate special/recall
  election wins (the legacy CSV records only their end-of-biennium chamber).

`TITLE_VOTERS` (import_openstates.py) maps presiding-officer titles printed
on roll calls to members, per biennium, verified against docs.legis officer
listings (2013+) or the Blue Book (2011). Unknown titles hard-fail.

## Known upstream-data defects accepted

- 2013 sv0012 (and any page like it): docs.legis prints `NOT VOTING - 1`
  with an empty name list. The scraper warns; checks accept all-or-none for
  the not-voting column only (yes/no reconciliation stays absolute). See
  checks.py and patches/README.md.
