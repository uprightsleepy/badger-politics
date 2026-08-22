"""Rebuild SQLite from archived scrape dirs (current biennium + backfill).

Usage: python -m importer.import_openstates <scrape_dir>... <sqlite_path>

Vote attribution goes through per-session rosters; ambiguous or unmatched
names abort the import. See docs/backfill.md for historical-era details.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from importer.committees import CommitteeIndex, load_committees
from importer.roster import (
    OPEN_END,
    Person,
    Roster,
    load_legacy_terms,
    load_people,
    merge_listing,
    roster_for,
)
from importer.status import SJR1_RE, derive_status

CENTRAL = ZoneInfo("America/Chicago")
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
VOTE_FIXES_PATH = Path(__file__).resolve().parent / "vote_corrections.json"

# per-vote name re-attributions for defective source pages (see the JSON)
VOTE_NAME_FIXES: dict[str, dict[str, str]] = {
    src: entry["names"]
    for src, entry in json.loads(VOTE_FIXES_PATH.read_text(encoding="utf-8")).items()
    if not src.startswith("_")
}

# Presiding officers print as titles on roll calls. Each mapping is a
# verified per-biennium fact; unmapped titles hard-fail (add, never infer).
TITLE_VOTERS: dict[tuple[str, str], dict[str, str]] = {
    # verified against docs.legis/<year>/legislators/assembly officer listings
    ("2025", "lower"): {"SPEAKER": "Vos", "SPEAKER PRO TEMPORE": "Petersen"},
    ("2023", "lower"): {"SPEAKER": "Vos", "SPEAKER PRO TEMPORE": "Petersen"},
    ("2021", "lower"): {"SPEAKER": "Vos", "SPEAKER PRO TEMPORE": "August"},
    ("2019", "lower"): {"SPEAKER": "Vos", "SPEAKER PRO TEMPORE": "August"},
    ("2017", "lower"): {"SPEAKER": "Vos", "SPEAKER PRO TEMPORE": "August"},
    ("2015", "lower"): {"SPEAKER": "Vos", "SPEAKER PRO TEMPORE": "August"},
    # 2013: pro tem changed mid-session (Kramer removed 2014-03, August
    # elected) — SPEAKER only; a pro-tem title in 2013 votes must hard-fail
    # so it gets mapped by date, never guessed.
    ("2013", "lower"): {"SPEAKER": "Vos"},
    # 2011-12: Speaker Jeff Fitzgerald (R-Horicon); docs.legis officer pages
    # don't exist that far back — basis: 2011-12 Wisconsin Blue Book.
    ("2011", "lower"): {"SPEAKER": "Fitzgerald"},
}


def biennium(session_key_str: str) -> str:
    """Session key -> odd-year biennium key ('2026s1' -> '2025')."""
    year = int(session_key_str[:4])
    return str(year if year % 2 else year - 1)


def session_key(identifier: str) -> str:
    """Normalize scraper session identifiers to short URL-safe keys:
    '2023' -> '2023'; '2009 Regular Session' -> '2009';
    'January 2021 Special Session' -> '2021s-jan'; '2026S1' -> '2026s1'."""
    if re.fullmatch(r"\d{4}(S\d+)?", identifier):
        return identifier.lower()
    m = re.fullmatch(r"(\d{4}) Regular Session", identifier)
    if m:
        return m.group(1)
    m = re.fullmatch(r"([A-Za-z]+) (\d{4}) Special Session", identifier)
    if m:
        return f"{m.group(2)}s-{m.group(1)[:3].lower()}"
    raise ValueError(f"unrecognized session identifier: {identifier!r}")


HEARING_RE = re.compile(r"\b(public hearing held|executive session held)\b", re.I)
# the committee-schedule feed double-escapes some titles ('Veterans’')
LITERAL_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def unescape_literal(text: str) -> str:
    return LITERAL_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)
REFERRAL_RE = re.compile(r"referred to (?:the )?(.+?)\s*$", re.I)
IDENTIFIER_RE = re.compile(r"^([A-Za-z]+)\s*(\d+)$")


def normalize_identifier(raw: str) -> str:
    """'AB656' / 'ab 656' -> 'AB 656'."""
    m = IDENTIFIER_RE.match(raw.strip())
    if not m:
        raise ValueError(f"unrecognized bill identifier: {raw!r}")
    return f"{m.group(1).upper()} {m.group(2)}"


def _pk(key: str, identifier: str) -> str:
    return f"{key}-{identifier.replace(' ', '').lower()}"


def bill_key(session: str, identifier: str) -> str:
    """Deterministic, URL-friendly PK: ('2025', 'AB 656') -> '2025-ab656'."""
    return _pk(session_key(session), identifier)


def pseudo_chamber(pseudo_id: str | None) -> str | None:
    """'~{"classification": "lower"}' -> 'lower'."""
    if not pseudo_id or not pseudo_id.startswith("~"):
        return None
    return json.loads(pseudo_id[1:]).get("classification")


def committee_from_referral(description: str) -> str | None:
    """'Read first time and referred to Committee on Children and Families'
    -> 'Children and Families' (leading 'Committee on' stripped; joint
    committees keep their full name)."""
    m = REFERRAL_RE.search(description)
    if not m:
        return None
    name = m.group(1).rstrip(".")
    if name.lower() == "calendar" or name.lower().startswith("calendar of"):
        # 'referred to calendar ...' is floor scheduling, not a committee
        return None
    if name.lower().startswith("committee on "):
        name = name[len("committee on "):]
    return name


def derive_graveyard(actions: list[dict]) -> tuple[int, str | None, str | None]:
    """(died_without_hearing, committee_at_death, committee_chamber):
    a referral, no hearing, then the SJR1 death. Chamber comes from the
    referral so a same-named committee elsewhere is never blamed."""
    death_idx = None
    for i, action in enumerate(actions):
        if SJR1_RE.search(action["description"]):
            death_idx = i
            break
    if death_idx is None:
        return 0, None, None
    referred = False
    committee = chamber = None
    for action in actions[:death_idx]:
        if "referral-committee" in (action.get("classification") or []):
            referred = True
            name = committee_from_referral(action["description"])
            if name:
                committee, chamber = name, action.get("chamber")
        if HEARING_RE.search(action["description"]):
            return 0, committee, chamber
    return (1 if referred else 0), committee, chamber


def to_local(start: str) -> tuple[str | None, str | None]:
    """Scraper timestamps are UTC ISO strings; hearings display in Central
    ('2025-01-07T15:00:00+00:00' -> ('2025-01-07', '09:00'))."""
    if not start:
        return None, None
    try:
        parsed = datetime.fromisoformat(start)
    except ValueError:
        return start[:10] or None, start[11:16] or None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(CENTRAL)
    return parsed.date().isoformat(), parsed.strftime("%H:%M")


def load_json_files(scrape_dirs: list[Path], prefix: str) -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for scrape_dir in scrape_dirs
        for p in sorted(scrape_dir.glob(f"{prefix}_*.json"))
    ]


def load_session_defs(scrape_dirs: list[Path]) -> dict[str, dict]:
    """identifier -> session metadata, merged across archive dirs."""
    defs: dict[str, dict] = {}
    for scrape_dir in scrape_dirs:
        for path in scrape_dir.glob("jurisdiction_*.json"):
            jur = json.loads(path.read_text(encoding="utf-8"))
            for s in jur.get("legislative_sessions", []):
                defs[s["identifier"]] = s
    return defs


def option_bucket(option: str) -> str:
    return option if option in ("yes", "no") else "other"


class Importer:
    def __init__(
        self,
        conn: sqlite3.Connection,
        rosters: dict[str, Roster],
        committees: CommitteeIndex,
        current_sessions: set[str],
    ):
        self.conn = conn
        self.rosters = rosters  # session_key -> Roster
        self.committees = committees
        self.current_sessions = current_sessions  # keys of the active biennium
        self.used_vote_fixes: set[tuple[str, str]] = set()
        self.bill_ids: dict[str, str] = {}  # scraper _id uuid -> our bill PK
        self.bill_pks: set[str] = set()  # every PK inserted into bills
        self.warnings: list[str] = []

    def import_sessions(self, session_defs: dict[str, dict], seen: set[str]) -> None:
        for identifier in sorted(seen):
            meta = session_defs.get(identifier, {})
            self.conn.execute(
                "INSERT INTO sessions (id, identifier, name, start_date, end_date)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    session_key(identifier),
                    identifier,
                    meta.get("name"),
                    meta.get("start_date"),
                    meta.get("end_date"),
                ),
            )

    def import_terms(
        self, people: list[Person], session_windows: dict[str, tuple[str, str]],
    ) -> None:
        events_path = Path(__file__).resolve().parent / "term_events.json"
        # entries match a term by "matches" (the source's end date) when the
        # source end is a verified artifact; "end" is what gets persisted.
        # "chamber" narrows the match when both chambers share an end date
        events = {
            (pid, e.get("matches", e["end"])): e
            for pid, entries in json.loads(events_path.read_text(encoding="utf-8")).items()
            if not pid.startswith("_")
            for e in entries
        }
        known = {row[0] for row in self.conn.execute("SELECT id FROM people")}
        used = set()
        coverage: list[tuple[str, str, str, str]] = []  # id, chamber, start, end
        for person in people:
            if person.id not in known:
                continue
            for term in person.terms:
                # synthetic terms (guessed dates) build rosters but are never
                # persisted; exact session windows replace them below
                if term.synthetic:
                    continue
                event = events.get((person.id, term.end)) if term.end else None
                if event and event.get("chamber") not in (None, term.chamber):
                    event = None
                end = term.end
                if event:
                    used.add((person.id, term.end))
                    end = event["end"]
                self.conn.execute(
                    "INSERT INTO person_terms"
                    " (person_id, chamber, district, start, end, end_label, end_url)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (person.id, term.chamber, term.district, term.start, end,
                     event["label"] if event else None,
                     event.get("url") if event else None),
                )
                coverage.append((person.id, term.chamber, term.start, end or OPEN_END))
        # session rosters are the authority that attributes votes; a rostered
        # member without a real dated term gets a biennium-bounded one, so
        # service coverage and vote attribution share one authority. The
        # biennium (Jan 1 odd year to Jan 1 odd+2, exactly adjacent like WI
        # terms ending on inauguration day) is used, not the session metadata
        # window: floor votes run past sine-die dates
        terms_by_person = {p.id: p.terms for p in people}
        # curation marked "exclusive" is the complete verified service for
        # that person+chamber; supplements stay out of its way (a curation
        # gap then orphans votes and fails the coverage gate loudly)
        curated_path = Path(__file__).resolve().parent / "person_terms.json"
        exclusive = {
            (pid, t["chamber"])
            for pid, entries in json.loads(curated_path.read_text(encoding="utf-8")).items()
            if not pid.startswith("_")
            for t in entries
            if t.get("exclusive")
        }
        for key in sorted(session_windows, key=lambda k: session_windows[k][0]):
            by = int(biennium(key))
            start, end = f"{by}-01-01", f"{by + 2}-01-01"
            for m in self.rosters[key].members:
                if m.id not in known:
                    continue
                if (m.id, m.chamber) in exclusive:
                    continue
                # session metadata windows run to the NEXT inauguration, so
                # a Jan-5 legacy start guess lands incoming freshmen on the
                # outgoing session's roster (the 2013 class on 2011's); a
                # supplement also needs the member's own recorded service
                # (guessed dates included) to touch this biennium — unless
                # the session's docs.legis listing itself seated them
                touches = m.from_listing or any(
                    t.chamber == m.chamber and t.start < end
                    and start < (t.end or OPEN_END)
                    for t in terms_by_person.get(m.id, [])
                )
                if not touches:
                    continue
                covered = any(
                    pid == m.id and ch == m.chamber and ts < end and start < te
                    for pid, ch, ts, te in coverage
                )
                if not covered:
                    # curated departure events label supplement ends too, and
                    # a "matches" entry corrects them (a mid-biennium exit by
                    # a legacy-era member has no real dated term to carry it)
                    event = events.get((m.id, end))
                    if event and event.get("chamber") not in (None, m.chamber):
                        event = None
                    term_end = end
                    if event:
                        used.add((m.id, end))
                        term_end = event["end"]
                    self.conn.execute(
                        "INSERT INTO person_terms"
                        " (person_id, chamber, district, start, end, end_label, end_url)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (m.id, m.chamber, m.district, start, term_end,
                         event["label"] if event else None,
                         event.get("url") if event else None),
                    )
                    coverage.append((m.id, m.chamber, start, term_end))
        dangling = set(events) - used
        if dangling:
            raise RuntimeError(f"term_events entries match no imported term: {dangling}")

    def import_committees(self) -> None:
        for c in self.committees.committees:
            self.conn.execute(
                "INSERT INTO committees (id, chamber, name, chair_person_id)"
                " VALUES (?, ?, ?, ?)",
                (c.id, c.chamber, c.name, c.chair_person_id),
            )
            for m in c.members:
                self.conn.execute(
                    "INSERT INTO committee_members (committee_id, person_id, role)"
                    " VALUES (?, ?, ?)",
                    (c.id, m["person_id"], m["role"]),
                )

    def import_people(self) -> None:
        """Union of every session roster; sitting members keep live titles."""
        seen: dict[str, dict] = {}
        ordered = sorted(self.rosters.items())  # oldest -> newest, newest wins
        for key, roster in ordered:
            is_current = key in self.current_sessions
            for m in roster.members:
                title = "Representative" if m.chamber == "lower" else "Senator"
                if not is_current:
                    title = f"Former {title}"
                previous = seen.get(m.id)
                # unreachable under chronological key order (current sessions
                # sort last); kept as a guard should ordering ever change
                if previous and previous["is_current"] and not is_current:
                    continue
                seen[m.id] = {
                    "row": (m.id, m.name, m.party, title, m.chamber, m.district,
                            m.image_url),
                    "is_current": is_current,
                }
        for entry in seen.values():
            self.conn.execute(
                "INSERT INTO people (id, name, party, current_role, chamber, district,"
                " image_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                entry["row"],
            )

    def import_bill(self, bill: dict) -> None:
        session = bill["legislative_session"]
        key = session_key(session)
        roster = self.rosters[key]
        identifier = normalize_identifier(bill["identifier"])
        pk = _pk(key, identifier)
        self.bill_ids[bill["_id"]] = pk
        self.bill_pks.add(pk)

        actions = [
            {**a, "chamber": pseudo_chamber(a.get("organization_id"))}
            for a in sorted(bill.get("actions", []), key=lambda a: a["date"])
        ]
        died, committee, committee_chamber = derive_graveyard(actions)
        status = derive_status(actions)
        chair_name = None
        if died and committee and key in self.current_sessions:
            # chairs known for the current biennium only; history stays NULL
            match = self.committees.find(committee, committee_chamber)
            if match:
                chair_name = match.chair_name
            else:
                self.warnings.append(
                    f"graveyard committee not in roster: {committee!r}"
                    f" ({committee_chamber}) on {pk}"
                )
        latest = actions[-1] if actions else None
        chamber = pseudo_chamber(bill.get("from_organization"))
        html_links = [
            link["url"]
            for version in bill.get("versions", [])
            for link in version.get("links", [])
            if link.get("media_type") == "text/html"
        ]
        # Prefer the original proposal text: enrolled/act versions of passed
        # bills omit the LRB analysis section.
        text_url = next(
            (url for url in html_links if "proposaltext" in url),
            html_links[0] if html_links else None,
        )
        self.conn.execute(
            "INSERT INTO bills (id, session_id, identifier, title, chamber,"
            " classification, status, latest_action_date, latest_action_desc,"
            " text_url, died_without_hearing, committee_at_death,"
            " committee_chamber_at_death,"
            " committee_chair_at_death, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'openstates')",
            (
                pk,
                key,
                identifier,
                bill.get("title"),
                chamber,
                ",".join(bill.get("classification", [])),
                status,
                latest["date"][:10] if latest else None,
                latest["description"] if latest else None,
                text_url,
                died,
                committee if died else None,
                committee_chamber if died else None,
                chair_name if died else None,
            ),
        )
        for i, action in enumerate(actions):
            self.conn.execute(
                "INSERT INTO actions (id, bill_id, date, chamber, description,"
                " classification) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    f"{pk}-a{i}",
                    pk,
                    action["date"][:10],
                    action["chamber"],
                    action["description"],
                    ",".join(action.get("classification") or []),
                ),
            )
        for doc in bill.get("documents", []):
            url = doc["links"][0]["url"] if doc.get("links") else None
            if url and doc.get("note"):
                self.conn.execute(
                    "INSERT INTO bill_documents (bill_id, note, url) VALUES (?, ?, ?)",
                    (pk, doc["note"], url),
                )
        for sp in bill.get("sponsorships", []):
            person_id = None
            if sp.get("entity_type") == "person":
                sp_chamber = None
                if sp.get("person_id"):
                    sp_chamber = json.loads(sp["person_id"][1:]).get("chamber")
                member = roster.resolve_or_none(sp["name"], sp_chamber or chamber)
                if member is None:
                    self.warnings.append(
                        f"sponsor unresolved (kept by name only): {sp['name']!r} on {pk}"
                    )
                else:
                    person_id = member.id
            self.conn.execute(
                "INSERT INTO sponsorships (bill_id, person_id, name, classification,"
                " is_primary) VALUES (?, ?, ?, ?, ?)",
                (
                    pk,
                    person_id,
                    sp["name"],
                    sp.get("classification"),
                    int(sp.get("primary", False)),
                ),
            )

    def import_vote_event(self, vote: dict) -> None:
        session = vote["legislative_session"]
        key = session_key(session)
        roster = self.rosters[key]
        bill_pk = self.bill_ids.get(vote.get("bill") or "")
        if bill_pk is None and vote.get("bill_identifier"):
            bill_pk = _pk(key, normalize_identifier(vote["bill_identifier"]))
        # bills are all imported before any votes, so the in-memory PK set
        # is exactly the bills table
        if bill_pk not in self.bill_pks:
            raise RuntimeError(f"vote event references unknown bill: {vote.get('_id')}")

        vote_id = f"{key}-{vote.get('dedupe_key') or vote['_id']}".lower()
        chamber = pseudo_chamber(vote.get("organization"))
        src_url = (vote.get("sources") or [{}])[0].get("url")
        counts = {option_bucket(c["option"]): 0 for c in vote.get("counts", [])}
        for c in vote.get("counts", []):
            counts[option_bucket(c["option"])] += c["value"]

        self.conn.execute(
            "INSERT INTO vote_events (id, bill_id, date, chamber, motion, result,"
            " yes_count, no_count, nv_count, source_url, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'openstates')",
            (
                vote_id,
                bill_pk,
                (vote.get("start_date") or "")[:10],
                chamber,
                vote.get("motion_text"),
                vote.get("result"),
                counts.get("yes"),
                counts.get("no"),
                counts.get("other"),
                src_url,
            ),
        )
        titles = TITLE_VOTERS.get((biennium(key), chamber), {})
        fixes = VOTE_NAME_FIXES.get(src_url or "", {})
        for record in vote.get("votes", []):
            voter_name = record["voter_name"].strip()
            voter_name = titles.get(voter_name.upper(), voter_name)
            if voter_name.upper() in fixes:
                self.used_vote_fixes.add((src_url, voter_name.upper()))
                voter_name = fixes[voter_name.upper()]
            # resolve raises on ambiguity/no-match: never attribute by guess
            member = roster.resolve(voter_name, chamber)
            self.conn.execute(
                "INSERT INTO vote_records (vote_event_id, person_id, option)"
                " VALUES (?, ?, ?)",
                (vote_id, member.id, record["option"]),
            )

    def import_event(self, event: dict) -> None:
        """Committee hearing (from the events scrape) -> hearings + committees."""
        name = unescape_literal(event.get("name") or "")
        hosts = [
            unescape_literal(p["name"])
            for p in event.get("participants", [])
            if p.get("entity_type") == "organization"
        ]
        committee_id = None
        if hosts:
            # the schedule feed doubles 'Joint' for committees whose proper
            # name already starts with it ('Joint Joint Legislative Audit')
            committee_name = re.sub(r"^(Joint )+", "Joint ", hosts[0])
            # 'Senate X' / 'Assembly X' -> chamber + bare name; joint stays whole
            chamber = None
            if committee_name.startswith("Senate "):
                chamber, committee_name = "upper", committee_name[len("Senate "):]
            elif committee_name.startswith("Assembly "):
                chamber, committee_name = "lower", committee_name[len("Assembly "):]
            match = self.committees.find(committee_name, chamber)
            if match:
                committee_id = match.id
            else:
                committee_id = re.sub(
                    r"[^a-z0-9]+", "-", f"{chamber or 'joint'}-{committee_name}".lower()
                ).strip("-")
                self.conn.execute(
                    "INSERT OR IGNORE INTO committees (id, chamber, name) VALUES (?, ?, ?)",
                    (committee_id, chamber, committee_name),
                )
        agenda_bills = []
        for item in event.get("agenda", []):
            for entity in item.get("related_entities", []):
                if entity.get("entity_type") == "bill" and entity.get("name"):
                    try:
                        agenda_bills.append(normalize_identifier(entity["name"]))
                    except ValueError:
                        agenda_bills.append(entity["name"])
        start = event.get("start_date") or ""
        local_date, local_time = to_local(start)
        self.conn.execute(
            "INSERT INTO hearings (id, title, committee_id, date, time, location,"
            " agenda_bill_ids_json, source_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.get("_id") or f"{name}-{start}",
                name or None,
                committee_id,
                local_date,
                local_time,
                (event.get("location") or {}).get("name"),
                json.dumps(agenda_bills),
                (event.get("sources") or [{}])[0].get("url"),
            ),
        )

    def tag_data_quality(self) -> None:
        """full = roll calls present; partial = actions only (older sessions)."""
        self.conn.execute(
            """UPDATE sessions SET data_quality = CASE WHEN EXISTS (
                   SELECT 1 FROM vote_records r
                   JOIN vote_events e ON e.id = r.vote_event_id
                   JOIN bills b ON b.id = e.bill_id
                   WHERE b.session_id = sessions.id
               ) THEN 'full' ELSE 'partial' END"""
        )

    def write_meta(self) -> None:
        counts = self.conn.execute(
            "SELECT session_id, COUNT(*) FROM bills GROUP BY session_id"
        ).fetchall()
        for session_id, n in counts:
            self.conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                (f"bill_count_{session_id}", str(n)),
            )
        latest = self.conn.execute("SELECT MAX(date) FROM actions").fetchone()[0]
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES ('data_through', ?)", (latest,)
        )
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES ('imported_at', ?)",
            (datetime.now(UTC).isoformat(timespec="seconds"),),
        )


def build_rosters(
    people: list[Person],
    session_defs: dict[str, dict],
    seen: set[str],
    rosters_dir: Path,
) -> tuple[dict[str, Roster], dict[str, tuple[str, str]]]:
    rosters = {}
    windows: dict[str, tuple[str, str]] = {}
    for identifier in seen:
        meta = session_defs.get(identifier)
        if not meta or not meta.get("start_date"):
            raise RuntimeError(f"no session dates for {identifier!r} in jurisdiction data")
        start = meta["start_date"]
        # sessions without an end_date are bounded to their biennium: the
        # next Legislature convenes in early January two years on, and an
        # unbounded window would sweep later members into old rosters
        end = meta.get("end_date") or f"{int(start[:4]) + 2}-01-01"
        key = session_key(identifier)
        roster = roster_for(people, start, end)
        # union in the docs.legis membership listing (authoritative for who
        # served; covers people-file date gaps and mid-session replacements)
        listing_path = rosters_dir / f"{biennium(key)}.json"
        if listing_path.exists():
            listing = json.loads(listing_path.read_text(encoding="utf-8"))
            roster = merge_listing(roster, listing, people)
        rosters[key] = roster
        windows[key] = (start, end)
    return rosters, windows


def current_session_keys(seen: set[str]) -> set[str]:
    """Sessions of the newest biennium present (chairs only known for these)."""
    keys = {session_key(s) for s in seen}
    newest = max(biennium(k) for k in keys)
    return {k for k in keys if biennium(k) == newest}


def run_import(
    scrape_dirs: list[Path],
    db_path: Path,
    people_dir: Path,
    retired_dir: Path,
    committees_dir: Path,
    executive_dir: Path | None = None,
) -> None:
    extra = [executive_dir] if executive_dir else []
    people_dirs = [d for d in (people_dir, retired_dir, *extra) if d and d.exists()]
    people = load_people(people_dirs)
    legacy_dir = people_dir.parents[1] / "legacy"
    people = load_legacy_terms(legacy_dir, people)
    if len(people) < 120:
        raise RuntimeError(
            f"only {len(people)} people loaded from {people_dirs};"
            " run: python -m scraper.fetch_people --retired"
        )
    committee_index = CommitteeIndex(load_committees(committees_dir))
    if not committee_index.committees:
        raise RuntimeError(
            f"no committees in {committees_dir}; run: python -m scraper.fetch_committees"
        )
    bills = load_json_files(scrape_dirs, "bill")
    votes = load_json_files(scrape_dirs, "vote_event")
    events = load_json_files(scrape_dirs, "event")
    if not bills:
        raise RuntimeError(f"no bill_*.json files in {scrape_dirs}")

    session_defs = load_session_defs(scrape_dirs)
    seen_sessions = {b["legislative_session"] for b in bills}
    rosters_dir = people_dir.parents[1] / "rosters"
    rosters, session_windows = build_rosters(people, session_defs, seen_sessions, rosters_dir)
    current = current_session_keys(seen_sessions)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    importer = Importer(conn, rosters, committee_index, current)
    with conn:
        importer.import_sessions(session_defs, seen_sessions)
        importer.import_people()
        importer.import_terms(people, session_windows)
        importer.import_committees()
        for bill in bills:
            importer.import_bill(bill)
        for vote in votes:
            importer.import_vote_event(vote)
        for event in events:
            importer.import_event(event)
        expected_fixes = {
            (src, name) for src, names in VOTE_NAME_FIXES.items() for name in names
        }
        dangling_fixes = expected_fixes - importer.used_vote_fixes
        if dangling_fixes:
            raise RuntimeError(f"vote_corrections match no vote record: {dangling_fixes}")
        importer.tag_data_quality()
        importer.write_meta()

    for warning in importer.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    stats = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        for table in ("sessions", "people", "bills", "actions", "sponsorships",
                      "bill_documents", "vote_events", "vote_records", "committees",
                      "hearings")
    }
    quality = conn.execute(
        "SELECT id, data_quality FROM sessions ORDER BY id"
    ).fetchall()
    conn.close()
    print("imported:", ", ".join(f"{k}={v}" for k, v in stats.items()))
    print("sessions:", ", ".join(f"{k}={q}" for k, q in quality))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path,
                        help="scrape dir(s)... followed by the sqlite path")
    data_root = Path(__file__).resolve().parents[1] / "_data"
    parser.add_argument("--people-dir", type=Path, default=data_root / "people" / "wi")
    parser.add_argument(
        "--retired-dir", type=Path, default=data_root / "people" / "wi-retired"
    )
    parser.add_argument(
        "--executive-dir", type=Path, default=data_root / "people" / "wi-executive"
    )
    parser.add_argument(
        "--committees-dir", type=Path, default=data_root / "people" / "wi-committees"
    )
    ns = parser.parse_args(argv)
    *scrape_dirs, db_path = ns.paths
    if not scrape_dirs:
        parser.error("need at least one scrape dir and the sqlite path")
    run_import(
        scrape_dirs, db_path, ns.people_dir, ns.retired_dir, ns.committees_dir,
        ns.executive_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
