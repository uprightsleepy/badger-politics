# Feature plans: alerts, fiscal estimates, video, committees, subjects

Researched 2026-08-21 with live probes of every source. Each plan keeps the
project's API access rules (free, keyless or free-key, honest User-Agent,
documented terms) and the attribution mandates (exact matching or no link,
gates over guesses, official source linked everywhere).

## 1. Fiscal estimates on bill pages

**Finding:** already in our archives. The openstates scrape captures every
bill's documents, including LFB fiscal estimates with official PDF URLs
(`docs.legis.wisconsin.gov/{year}/related/fe/{bill}/..._lfb.pdf`); a sample
of 400 bills held 401 fiscal-estimate documents. No new API, no new source.

**Phase 1 — links (no accuracy risk):**
- Importer: new `bill_documents` table (`bill_id`, `note`, `url`), loaded
  from the archived bill JSON `documents` arrays alongside actions.
- Bill page: a "Fiscal estimates" line under the LRB analysis listing each
  estimate (agency parsed from the note text verbatim) linking to the
  official PDF. We assert nothing about content, so nothing can be
  misattributed.
- Effort: small. One table, one importer loop, one page section.

**Phase 2 — amounts (deferred, gated):** parsing dollar figures out of the
PDFs is a wec_pdf-style project with real error surface (estimates are
ranges, "indeterminate", annualized vs biennial). Only attempt with a
strict parse-or-skip gate and per-figure provenance. Not in phase 1.

## 2. Subject browsing

**Finding:** docs.legis publishes a per-session subject index
(`/{year}/related/subject_index/index`) and the vendored scraper reads it,
but a bill-id key-format mismatch means **zero** bills in any session
archive carry subjects. Upstream bug; candidate for an upstream PR.

**Plan (own fetcher, no full rescrape):**
- `scraper/fetch_subjects.py`: walk the subject index per session (the
  "Down"-link pagination the scraper already handles), archive
  `_data/subjects/subjects-{session}.json` as subject → [identifiers].
  Identifiers are normalized the same way the site's `billSlug` works;
  an identifier that matches no bill in that session is counted and
  reported, never guessed across sessions.
- Importer: `bill_subjects` (`bill_id`, `subject`); rows only for exact
  session+identifier matches.
- Site: `/subjects/` index (subject list with counts) and
  `/subjects/{slug}/` pages listing bills across sessions, newest first;
  bill pages get a subject chip row. Subjects are the state's own index
  terms, displayed verbatim.
- Nightly: fetch is cheap (a few dozen pages per session); current session
  refreshes nightly, historical sessions fetch once.
- Effort: medium. New fetcher + table + two page templates.

## 3. WisconsinEye video links

**Finding:** wiseye.org is WordPress with an open REST API
(`/wp-json/wp/v2/posts`), keyless. Posts are one-per-recording with exact
titles ("Joint Committee on Finance"), dates, and canonical URLs. We link;
we never embed or republish their content.

**Accuracy rule (the whole design):** a hearing links to a video only when
exactly one WisEye post exists on that hearing's date whose normalized
title equals the normalized committee name (same normalization family as
committees.py). Zero matches or two-plus matches: no link. Floor sessions
match the "Assembly/Senate Floor Session" title pattern by date, same
exact-or-nothing rule.
- `scraper/fetch_wiseye.py`: nightly, query posts by date range (last ~14
  days plus any hearing dates missing links), archive
  `_data/wiseye/videos.json` (date, title, url). Full-history backfill is
  one paginated walk, run once.
- Importer: `hearing_videos` (`hearing_id`, `url`, `title`) written only on
  exact matches; a `videos.json` row that matches nothing is kept archived
  for the day the hearing data catches up.
- Site: "Watch on WisconsinEye" link on hearing rows and the calendar day
  panel. Framed as an external archive that may move (their December
  shutdown took the archive dark for seven weeks): links are a courtesy
  layer, never load-bearing.
- Fragility handling: the nightly fetch tolerates total failure (warn,
  keep old archive) so their outages never break our run.
- Effort: medium-small. One fetcher, one table, link rendering.

## 4. Committee hub pages

**Finding:** all data already fetched. `fetch_committees` pulls the
openstates people committee YAML (members with roles and person ids);
the importer currently stores only the chair.

**Plan:**
- Importer: `committee_members` (`committee_id`, `person_id`, `role`),
  loaded from the same YAML that already provides chairs. Person ids are
  openstates ids, so membership inherits the roster's exactness; a member
  id not in `people` is a hard import failure like any other orphan.
- Site: `/committees/` index and `/committees/{id}/` pages: members with
  party chips and profile links, chair marked, upcoming and recent
  hearings (already queryable), and the committee's Hearing None record:
  bills that died there, per session, with the kill rate stated as a
  count ("X of Y bills referred here never got a hearing"), computed only
  from `committee_at_death` rows that name this committee.
- Committee name → id linking across referral actions uses the existing
  `normalize_name` machinery; unmatched referral texts stay plain text.
- Mandate note: per rule 5, no money data on committee pages. A chair's
  profile is one click away; the juxtaposition stays the reader's choice.
- New checks: `committee_members -> people`, `committee_members ->
  committees` referential gates.
- Effort: medium. One table, two templates, two gates.

## 5. Alerts and follows

**Finding:** research says notification converts citizens from one-time
visitors into users, and it is the one competitive gap. It is also the
feature squeezed hardest by the mandates: no accounts, no server-side user
data, static serving path, ~$2/month.

**Phase 1 — inside current mandates (build now):**
- **Follow affordance:** a "Follow" button on bill and legislator pages
  storing ids in localStorage (`bp-follows`), same device-only model as
  districts and polling places.
- **"Since your last visit" page:** `/following/` renders the followed
  items client-side from the existing static JSON API
  (`/api/v1/bills/...json`), diffing latest-action dates against a
  last-visit timestamp in localStorage. Fully static, no new data
  products, no privacy surface: the server never learns what anyone
  follows.
- **Feed promotion:** per-bill and per-legislator Atom feeds already
  exist; the follow UI links them ("get updates in any feed reader")
  and the weekly digest feed gets a visible subscribe affordance.
- Effort: medium. One page, one script module, UI touches.

**Phase 2 — email (requires a mandate decision, not a technical one):**
Email digests mean storing subscriber addresses somewhere — server-side
user data, which mandate 8 currently prohibits, plus a sender
(free tiers exist: Buttondown/Listmonk-on-free-tier class) and its cost
curve against mandate 9. If ever pursued: a separate opt-in service,
clearly firewalled from the site (no shared analytics, address used for
delivery only, one-click delete), and the mandate text amended
deliberately. Not started without that explicit decision.

## Suggested order

1. **Fiscal estimates phase 1** — smallest, uses archived data, answers a
   documented constituent demand (bill costs).
2. **Committee hubs** — data in hand, completes the accountability loop.
3. **Subjects** — new fetcher but transforms browsability.
4. **Follows phase 1** — the competitive gap, fully within mandates.
5. **WisEye links** — valuable courtesy layer; last because it depends on
   their stability and adds the least structured data.
