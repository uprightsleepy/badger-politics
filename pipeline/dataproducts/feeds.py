"""Atom feeds: free alerts via any feed reader, zero email infrastructure.

  /feeds/bills/{bill_id}.xml        a bill's action timeline
  /feeds/legislators/{slug}.xml     a legislator's votes + sponsorships
  /feeds/committees/{id}.xml        a committee's hearings
  /feeds/weekly.xml                 "this week in the legislature" digest
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET

from dataproducts import queries
from dataproducts.api import bill_slug, person_slug

SITE = "https://badgerpolitics.org"
ATOM = "http://www.w3.org/2005/Atom"


def _feed(title: str, feed_path: str, updated: str) -> ET.Element:
    root = ET.Element("feed", xmlns=ATOM)
    ET.SubElement(root, "title").text = title
    ET.SubElement(root, "id").text = f"{SITE}{feed_path}"
    ET.SubElement(root, "link", rel="self", href=f"{SITE}{feed_path}")
    ET.SubElement(root, "link", rel="alternate", href=SITE)
    ET.SubElement(root, "updated").text = updated
    author = ET.SubElement(root, "author")
    ET.SubElement(author, "name").text = "Badger Politics"
    return root


def _entry(
    root: ET.Element, entry_id: str, title: str, updated: str, link: str, summary: str
) -> None:
    entry = ET.SubElement(root, "entry")
    ET.SubElement(entry, "id").text = entry_id
    ET.SubElement(entry, "title").text = title
    ET.SubElement(entry, "updated").text = updated
    ET.SubElement(entry, "link", rel="alternate", href=link)
    ET.SubElement(entry, "summary").text = summary


def _stamp(date: str | None) -> str:
    """Feed timestamps are dates in the data; render as UTC midnight."""
    return f"{date or '1970-01-01'}T00:00:00Z"


def _write(root: ET.Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def build_feeds(
    conn: sqlite3.Connection, out: Path, hearings: list[dict] | None = None
) -> int:
    feeds_dir = out / "feeds"
    files = 0

    bill_columns = "id, identifier, title, session_id, latest_action_date"
    for bill in queries.bills(conn, columns=bill_columns):
        actions = queries.actions_for(conn, bill["id"])
        if not actions:
            continue
        session = bill["session_id"]
        slug = bill_slug(bill)
        page = f"{SITE}/bills/{session}/{slug}"
        path = f"/feeds/bills/{bill['id']}.xml"
        root = _feed(
            f"{bill['identifier']}: {(bill['title'] or '')[:80]}",
            path,
            _stamp(bill["latest_action_date"]),
        )
        for i, action in enumerate(actions):
            _entry(
                root,
                f"{SITE}{path}#a{i}",
                f"{bill['identifier']}: {action['description'][:120]}",
                _stamp(action["date"]),
                page,
                action["description"],
            )
        _write(root, feeds_dir / "bills" / f"{bill['id']}.xml")
        files += 1

    for person in queries.people(conn):
        slug = person_slug(person["id"])
        votes = queries.votes_by_person(conn, person["id"], limit=100)
        path = f"/feeds/legislators/{slug}.xml"
        updated = _stamp(votes[0]["date"] if votes else None)
        root = _feed(f"{person['name']} — votes", path, updated)
        for vote in votes:
            _entry(
                root,
                f"{SITE}{path}#{vote['vote_event_id']}",
                f"Voted '{vote['option']}' on {vote['identifier']}",
                _stamp(vote["date"]),
                f"{SITE}/votes/{vote['vote_event_id']}",
                f"{vote['motion'] or 'Vote'} — {vote['identifier']}:"
                f" {(vote['title'] or '')[:120]}",
            )
        _write(root, feeds_dir / "legislators" / f"{slug}.xml")
        files += 1

    if hearings is None:
        hearings = queries.hearings(conn)
    by_committee: dict[str, list[dict]] = {}
    for hearing in hearings:
        if hearing["committee_id"]:
            by_committee.setdefault(hearing["committee_id"], []).append(hearing)
    for committee_id, committee_hearings in by_committee.items():
        name = committee_hearings[0]["committee_name"] or committee_id
        path = f"/feeds/committees/{committee_id.rsplit('/', 1)[-1]}.xml"
        updated = _stamp(max(h["date"] or "" for h in committee_hearings) or None)
        root = _feed(f"{name} — hearings", path, updated)
        for hearing in committee_hearings[-100:]:
            bills_text = ", ".join(hearing["agenda_bills"]) or "agenda posted"
            _entry(
                root,
                f"{SITE}{path}#{hearing['id']}",
                f"Hearing {hearing['date']}: {bills_text[:100]}",
                _stamp(hearing["date"]),
                hearing["source_url"] or f"{SITE}/hearings",
                f"{name}, {hearing['date']} {hearing['time'] or ''}"
                f" — {hearing['location'] or 'location TBA'}. Bills: {bills_text}",
            )
        _write(root, feeds_dir / "committees" / f"{committee_id.rsplit('/', 1)[-1]}.xml")
        files += 1

    # weekly digest: everything that moved in the 7 days up to the data's edge
    data_through = queries.meta(conn).get("data_through")
    if data_through:
        cutoff = (
            datetime.fromisoformat(data_through).replace(tzinfo=UTC) - timedelta(days=7)
        ).date().isoformat()
        rows = conn.execute(
            f"""SELECT a.date, a.description, b.id, b.identifier, b.title, b.session_id
                FROM actions a JOIN bills b ON b.id = a.bill_id
                WHERE a.date >= ? AND {queries.exportable("b.")}
                ORDER BY a.date DESC LIMIT 200""",
            (cutoff,),
        ).fetchall()
        root = _feed(
            "This week in the Wisconsin Legislature", "/feeds/weekly.xml",
            _stamp(data_through),
        )
        for i, (date, desc, bill_id, identifier, title, session_id) in enumerate(rows):
            _entry(
                root,
                f"{SITE}/feeds/weekly.xml#{bill_id}-{date}-{i}",
                f"{identifier}: {desc[:100]}",
                _stamp(date),
                f"{SITE}/bills/{session_id}/{identifier.replace(' ', '').lower()}",
                f"{identifier} — {(title or '')[:150]}: {desc}",
            )
        _write(root, feeds_dir / "weekly.xml")
        files += 1

    return files
