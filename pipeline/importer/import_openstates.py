"""Import openstates-scrapers JSON output into SQLite.

Usage: python -m importer.import_openstates <scrape_dir> <sqlite_path>
                                            [--people-dir DIR]

Reads bill_*.json, vote_event_*.json, event_*.json and the jurisdiction file
produced by `os-update wi ... --scrape`, plus the openstates/people roster,
and rebuilds the database from schema.sql. Vote attribution goes through the
session-scoped roster; ambiguous or unmatched voter names abort the import.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from importer.committees import CommitteeIndex, load_committees
from importer.roster import Roster, load_roster
from importer.status import SJR1_RE, derive_status

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Roll call pages record presiding officers by TITLE, not name. Mapping a
# title to a member is a documented per-biennium fact (verified against
# docs.legis officer listings), never inferred. Historical sessions imported
# in Phase 4 must add their own entries — unknown titles hard-fail the build.
TITLE_VOTERS: dict[tuple[str, str], dict[str, str]] = {
    # 2025-26 biennium: Speaker Robin Vos, Speaker Pro Tempore Kevin Petersen
    ("2025", "lower"): {"SPEAKER": "Vos", "SPEAKER PRO TEMPORE": "Petersen"},
}


def biennium(session: str) -> str:
    """Session identifier -> odd-year biennium key ('2026S1' -> '2025')."""
    year = int(session[:4])
    return str(year if year % 2 else year - 1)


HEARING_RE = re.compile(r"\b(public hearing held|executive session held)\b", re.I)
REFERRAL_RE = re.compile(r"referred to (?:the )?(.+?)\s*$", re.I)
IDENTIFIER_RE = re.compile(r"^([A-Za-z]+)\s*(\d+)$")


def normalize_identifier(raw: str) -> str:
    """'AB656' / 'ab 656' -> 'AB 656'."""
    m = IDENTIFIER_RE.match(raw.strip())
    if not m:
        raise ValueError(f"unrecognized bill identifier: {raw!r}")
    return f"{m.group(1).upper()} {m.group(2)}"


def bill_key(session: str, identifier: str) -> str:
    """Deterministic, URL-friendly PK: ('2025', 'AB 656') -> '2025-ab656'."""
    return f"{session.lower()}-{identifier.replace(' ', '').lower()}"


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
    """(died_without_hearing, committee_at_death, committee_chamber) per plan
    §4: a referral, no hearing/executive-session action, then the SJR1
    failure action. Chamber comes from the referral action, so a same-named
    committee in the other chamber can never be blamed."""
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


def load_json_files(scrape_dir: Path, prefix: str) -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(scrape_dir.glob(f"{prefix}_*.json"))
    ]


def option_bucket(option: str) -> str:
    return option if option in ("yes", "no") else "other"


class Importer:
    def __init__(self, conn: sqlite3.Connection, roster: Roster, committees: CommitteeIndex):
        self.conn = conn
        self.roster = roster
        self.committees = committees
        self.bill_ids: dict[str, str] = {}  # scraper _id uuid -> our bill PK
        self.warnings: list[str] = []

    def import_committees(self) -> None:
        for c in self.committees.committees:
            self.conn.execute(
                "INSERT INTO committees (id, chamber, name, chair_person_id)"
                " VALUES (?, ?, ?, ?)",
                (c.id, c.chamber, c.name, c.chair_person_id),
            )

    def import_sessions(self, scrape_dir: Path, seen_sessions: set[str]) -> None:
        jurisdiction_files = list(scrape_dir.glob("jurisdiction_*.json"))
        defined = {}
        if jurisdiction_files:
            jur = json.loads(jurisdiction_files[0].read_text(encoding="utf-8"))
            defined = {s["identifier"]: s for s in jur.get("legislative_sessions", [])}
        for identifier in sorted(seen_sessions):
            meta = defined.get(identifier, {})
            self.conn.execute(
                "INSERT INTO sessions (id, identifier, name, start_date, end_date)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    identifier.lower(),
                    identifier,
                    meta.get("name"),
                    meta.get("start_date"),
                    meta.get("end_date"),
                ),
            )

    def import_people(self) -> None:
        for m in self.roster.members:
            role = "Representative" if m.chamber == "lower" else "Senator"
            self.conn.execute(
                "INSERT INTO people (id, name, party, current_role, chamber, district,"
                " image_url, openstates_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (m.id, m.name, m.party, role, m.chamber, m.district, m.image_url, m.id),
            )

    def import_bill(self, bill: dict) -> None:
        session = bill["legislative_session"]
        identifier = normalize_identifier(bill["identifier"])
        pk = bill_key(session, identifier)
        self.bill_ids[bill["_id"]] = pk

        actions = [
            {**a, "chamber": pseudo_chamber(a.get("organization_id"))}
            for a in sorted(bill.get("actions", []), key=lambda a: a["date"])
        ]
        died, committee, committee_chamber = derive_graveyard(actions)
        status = derive_status(actions)
        chair_name = None
        if died and committee:
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
            " committee_chair_at_death, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'openstates')",
            (
                pk,
                session.lower(),
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
        for sp in bill.get("sponsorships", []):
            person_id = None
            if sp.get("entity_type") == "person":
                sp_chamber = None
                if sp.get("person_id"):
                    sp_chamber = json.loads(sp["person_id"][1:]).get("chamber")
                member = self.roster.resolve_or_none(sp["name"], sp_chamber or chamber)
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
        bill_pk = self.bill_ids.get(vote.get("bill") or "")
        if bill_pk is None and vote.get("bill_identifier"):
            bill_pk = bill_key(session, normalize_identifier(vote["bill_identifier"]))
        row = self.conn.execute("SELECT 1 FROM bills WHERE id = ?", (bill_pk,)).fetchone()
        if row is None:
            raise RuntimeError(f"vote event references unknown bill: {vote.get('_id')}")

        vote_id = f"{session.lower()}-{vote.get('dedupe_key') or vote['_id']}".lower()
        chamber = pseudo_chamber(vote.get("organization"))
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
                (vote.get("sources") or [{}])[0].get("url"),
            ),
        )
        titles = TITLE_VOTERS.get((biennium(session), chamber), {})
        for record in vote.get("votes", []):
            voter_name = record["voter_name"].strip()
            voter_name = titles.get(voter_name.upper(), voter_name)
            # Hard rule: roster.resolve raises on ambiguity/no-match, aborting
            # the import — a roll call is never attributed by best guess.
            member = self.roster.resolve(voter_name, chamber)
            self.conn.execute(
                "INSERT INTO vote_records (vote_event_id, person_id, option)"
                " VALUES (?, ?, ?)",
                (vote_id, member.id, record["option"]),
            )

    def import_event(self, event: dict) -> None:
        """Committee hearing (from the events scrape) -> hearings + committees."""
        name = event.get("name") or ""
        hosts = [
            p["name"]
            for p in event.get("participants", [])
            if p.get("entity_type") == "organization"
        ]
        committee_id = None
        if hosts:
            committee_name = hosts[0]
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
        self.conn.execute(
            "INSERT INTO hearings (id, committee_id, date, time, location,"
            " agenda_bill_ids_json, source_url) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.get("_id") or f"{name}-{start}",
                committee_id,
                start[:10],
                start[11:16] if len(start) > 11 else None,
                (event.get("location") or {}).get("name"),
                json.dumps(agenda_bills),
                (event.get("sources") or [{}])[0].get("url"),
            ),
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


def run_import(
    scrape_dir: Path, db_path: Path, people_dir: Path, committees_dir: Path
) -> None:
    roster = load_roster(people_dir)
    committee_index = CommitteeIndex(load_committees(committees_dir))
    if not committee_index.committees:
        raise RuntimeError(
            f"no committees in {committees_dir}; run: python -m scraper.fetch_committees"
        )
    bills = load_json_files(scrape_dir, "bill")
    votes = load_json_files(scrape_dir, "vote_event")
    events = load_json_files(scrape_dir, "event")
    if not bills:
        raise RuntimeError(f"no bill_*.json files in {scrape_dir}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    importer = Importer(conn, roster, committee_index)
    with conn:
        importer.import_sessions(scrape_dir, {b["legislative_session"] for b in bills})
        importer.import_people()
        importer.import_committees()
        for bill in bills:
            importer.import_bill(bill)
        for vote in votes:
            importer.import_vote_event(vote)
        for event in events:
            importer.import_event(event)
        importer.write_meta()

    for warning in importer.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    stats = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        for table in ("sessions", "people", "bills", "actions", "sponsorships",
                      "vote_events", "vote_records", "committees", "hearings")
    }
    conn.close()
    print("imported:", ", ".join(f"{k}={v}" for k, v in stats.items()))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scrape_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    parser.add_argument(
        "--people-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "_data" / "people" / "wi",
    )
    parser.add_argument(
        "--committees-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "_data" / "people" / "wi-committees",
    )
    ns = parser.parse_args(argv)
    run_import(ns.scrape_dir, ns.db_path, ns.people_dir, ns.committees_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
