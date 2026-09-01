"""Import council votes from the local Legistar cache into SQLite.

Usage: python -m importer.import_local <local_data_dir> <sqlite_path>

Attribution is the tenant's own person id on every vote row; there is no
name matching. Seats come from office-record titles where the tenant
records them (Milwaukee's "3rd District") and from the human-verified
importer/local_seats.json where it does not (West Allis prints "Ald.").
A member who appears only in vote records (no office record) is kept
with the tenant's own id and name and no term dates; the import reports
how many, and never invents dates for them.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

from importer.local_registry import TENANTS
from importer.person_slugs import slugify
from importer.roster import load_curation

SEATS_PATH = Path(__file__).resolve().parent / "local_seats.json"
# Milwaukee office-record titles carry the seat: '3rd District'
TITLE_SEAT_RE = re.compile(r"^(\d+)(?:st|nd|rd|th) District$")

TABLES = (
    "local_votes", "local_actions", "local_events",
    "local_member_terms", "local_members", "local_vote_types", "local_bodies",
)


def matter_url(spec: dict, item: dict) -> str | None:
    mid, guid = item.get("EventItemMatterId"), item.get("EventItemMatterGuid")
    if not mid or not guid:
        return None
    return f"{spec['insite']}/LegislationDetail.aspx?ID={mid}&GUID={guid}"


def import_members(
    conn: sqlite3.Connection, spec: dict, office: list[dict], curated: dict
) -> dict[int, str]:
    """Insert members and terms; returns person_id -> name."""
    tenant = spec["tenant"]
    today = date.today().isoformat()
    by_person: dict[int, list[dict]] = {}
    for r in office:
        by_person.setdefault(r["OfficeRecordPersonId"], []).append(r)

    names: dict[int, str] = {}
    used_slugs: set[str] = set()
    for person_id, records in sorted(by_person.items()):
        records.sort(key=lambda r: r.get("OfficeRecordStartDate") or "")
        latest = records[-1]
        name = latest["OfficeRecordFullName"].strip()
        is_current = any((r.get("OfficeRecordEndDate") or "")[:10] >= today for r in records)
        # the seat: the tenant's own title, else the curated table
        seat = seat_basis = None
        for r in reversed(records):
            m = TITLE_SEAT_RE.match(r.get("OfficeRecordTitle") or "")
            if m:
                seat = int(m.group(1))
                break
        if seat is None and str(person_id) in curated:
            entry = curated[str(person_id)]
            seat, seat_basis = entry["seat"], entry["basis"]
        if seat is not None and not 1 <= seat <= spec["seats"]:
            raise RuntimeError(f"{tenant} person {person_id}: seat {seat} out of range")
        slug = slugify(name) or str(person_id)
        if slug in used_slugs:  # two members sharing a name: id, never a guess
            slug = f"{slug}-{person_id}"
        used_slugs.add(slug)
        conn.execute(
            "INSERT INTO local_members (tenant, person_id, name, slug, seat,"
            " seat_basis, member_type, is_current) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tenant, person_id, name, slug, seat, seat_basis,
             latest.get("OfficeRecordMemberType"), int(is_current)),
        )
        names[person_id] = name
        for r in records:
            conn.execute(
                "INSERT INTO local_member_terms (tenant, person_id, title, start, end)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    tenant, person_id, r.get("OfficeRecordTitle"),
                    (r.get("OfficeRecordStartDate") or "")[:10],
                    (r.get("OfficeRecordEndDate") or "")[:10] or None,
                ),
            )
    return names


def import_tenant(conn: sqlite3.Connection, spec: dict, local_dir: Path) -> dict:
    tenant = spec["tenant"]
    src = local_dir / tenant
    office = json.loads((src / "officerecords.json").read_text(encoding="utf-8"))
    vote_types = json.loads((src / "votetypes.json").read_text(encoding="utf-8"))
    curated = load_curation(SEATS_PATH).get(tenant, {})

    conn.execute(
        "INSERT INTO local_bodies (tenant, slug, city, name, insite_url, seats)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (tenant, spec["slug"], spec["city"], spec["body_display"],
         spec["insite"], spec["seats"]),
    )
    for vt in vote_types:
        conn.execute(
            "INSERT INTO local_vote_types (tenant, value) VALUES (?, ?)",
            (tenant, vt["VoteTypeName"]),
        )
    names = import_members(conn, spec, office, curated)

    events = actions = votes = unvalued = duplicated = conflicting = 0
    vote_only_members: set[int] = set()
    voter_names: dict[int, str] = {}
    for path in sorted(src.glob("event_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        event, items = data["event"], data["items"]
        if not items:
            continue  # duplicate or empty event records carry nothing
        if not event.get("EventInSiteURL"):
            raise RuntimeError(f"{tenant} event {event['EventId']}: no InSite URL")
        conn.execute(
            "INSERT INTO local_events (tenant, event_id, date, minutes_status,"
            " insite_url) VALUES (?, ?, ?, ?, ?)",
            (tenant, event["EventId"], event["EventDate"][:10],
             event.get("EventMinutesStatusName"), event["EventInSiteURL"]),
        )
        events += 1
        for item in items:
            if not item.get("EventItemActionName"):
                continue
            conn.execute(
                "INSERT INTO local_actions (tenant, event_item_id, event_id,"
                " matter_id, matter_file, matter_type, matter_status, title,"
                " action, passed, agenda_number, matter_url)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant, item["EventItemId"], event["EventId"],
                    item.get("EventItemMatterId"), item.get("EventItemMatterFile"),
                    item.get("EventItemMatterType"), item.get("EventItemMatterStatus"),
                    item.get("EventItemTitle"), item["EventItemActionName"],
                    item.get("EventItemPassedFlag"), item.get("EventItemAgendaNumber"),
                    matter_url(spec, item),
                ),
            )
            actions += 1
            # One row per (item, person). The source occasionally lists a
            # voter twice: the same value twice is one fact, kept once; two
            # different values is the record disagreeing with itself, and no
            # position is attributed. Both are counted, neither is guessed.
            positions: dict[int, str] = {}
            conflicted: set[int] = set()
            for v in data["votes"].get(str(item["EventItemId"]), []):
                if not v.get("VoteValueName"):
                    # the clerk listed the voter but recorded no position:
                    # not a vote, so nothing to attribute; counted, never guessed
                    unvalued += 1
                    continue
                pid, value = v["VotePersonId"], v["VoteValueName"]
                if pid in positions:
                    if positions[pid] == value:
                        duplicated += 1
                    else:
                        conflicted.add(pid)
                    continue
                positions[pid] = value
                voter_names[pid] = v["VotePersonName"].strip()
            conflicting += len(conflicted)
            for person_id, value in positions.items():
                if person_id in conflicted:
                    continue
                if person_id not in names:
                    # in the votes but not the body's office records: keep
                    # the tenant's own id and name, invent nothing
                    vote_only_members.add(person_id)
                    names[person_id] = voter_names[person_id]
                    conn.execute(
                        "INSERT INTO local_members (tenant, person_id, name, slug,"
                        " seat, seat_basis, member_type, is_current)"
                        " VALUES (?, ?, ?, ?, NULL, NULL, NULL, 0)",
                        (tenant, person_id, names[person_id],
                         f"{slugify(names[person_id]) or 'member'}-{person_id}"),
                    )
                conn.execute(
                    "INSERT INTO local_votes (tenant, event_item_id, person_id, value)"
                    " VALUES (?, ?, ?, ?)",
                    (tenant, item["EventItemId"], person_id, value),
                )
                votes += 1
    # Office records are incomplete for earlier years (Milwaukee's carry no
    # dates for several long-serving members), so a vote outside its
    # member's recorded dates is reported, not gated: the vote itself is
    # the tenant's record, the term table is the weaker of the two.
    outside = conn.execute(
        """SELECT COUNT(*) FROM local_votes v
           JOIN local_actions a ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id
           JOIN local_events e ON e.tenant = a.tenant AND e.event_id = a.event_id
           WHERE v.tenant = ? AND NOT EXISTS (
             SELECT 1 FROM local_member_terms t WHERE t.tenant = v.tenant
             AND t.person_id = v.person_id AND e.date >= t.start
             AND e.date <= COALESCE(t.end, '9999'))""",
        (tenant,),
    ).fetchone()[0]
    return {
        "events": events, "actions": actions, "votes": votes,
        "members": len(names), "vote_only": len(vote_only_members),
        "unvalued": unvalued, "outside_terms": outside,
        "duplicated": duplicated, "conflicting": conflicting,
    }


def run(local_dir: Path, db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    with conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed list above
        conn.execute("DELETE FROM meta WHERE key LIKE 'local_%'")
        for spec in TENANTS:
            stats = import_tenant(conn, spec, local_dir)
            print(
                f"{spec['tenant']}: {stats['events']} meetings, {stats['actions']}"
                f" actions, {stats['votes']} votes, {stats['members']} members"
                + (f" ({stats['vote_only']} known only from vote records)"
                   if stats["vote_only"] else "")
            )
            if stats["unvalued"]:
                print(f"  {stats['unvalued']} vote rows carried no recorded value: skipped")
            if stats["duplicated"]:
                print(f"  {stats['duplicated']} rows repeated a member's recorded value: kept once")
            if stats["conflicting"]:
                print(f"  {stats['conflicting']} member positions recorded two ways on one item:"
                      " no position attributed")
            if stats["outside_terms"]:
                print(f"  {stats['outside_terms']} votes fall outside the member's recorded"
                      " office dates (term records incomplete; reported, not gated)")
        through = conn.execute("SELECT MAX(date) FROM local_events").fetchone()[0]
        if through:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('local_votes_through', ?)",
                (through,),
            )
    conn.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("local_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    run(ns.local_dir, ns.db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
