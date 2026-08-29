"""Static JSON API tree: /api/v1/... pre-generated at build time.

Layout (all CDN-served static files):
  /api/v1/meta.json                      freshness + session stats
  /api/v1/sessions.json
  /api/v1/bills/{session}/index.json     light per-session bill index
  /api/v1/bills/{session}/{ab656}.json   full bill + sponsors + actions + votes
  /api/v1/votes/{vote_id}.json           full roll call
  /api/v1/legislators/index.json
  /api/v1/legislators/{person_id}.json   profile + election + sponsorships + votes
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dataproducts import queries

_ensured_dirs: set[Path] = set()  # builds only add directories, never remove


def write_json(path: Path, payload: dict | list) -> None:
    if path.parent not in _ensured_dirs:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ensured_dirs.add(path.parent)
    path.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )


def bill_slug(identifier: str) -> str:
    return identifier.replace(" ", "").lower()


# The site and the data products have to agree on a person's slug, or the
# Atom feed a page links to does not exist. Both read this one committed
# map; see importer/person_slugs.py for why it is a file and not a rule.
_SLUGS_PATH = Path(__file__).resolve().parents[2] / "site" / "src" / "data" / "person-slugs.json"
try:
    _PERSON_SLUGS: dict[str, str] = json.loads(_SLUGS_PATH.read_text(encoding="utf-8"))
except (OSError, ValueError):
    _PERSON_SLUGS = {}


def person_slug(person_id: str) -> str:
    """Name slug where one is on file, the old uuid tail otherwise."""
    return _PERSON_SLUGS.get(person_id) or person_id.rsplit("/", 1)[-1]


def build_api(conn: sqlite3.Connection, out: Path) -> int:
    api = out / "api" / "v1"
    files = 0

    sessions = queries.sessions(conn)
    write_json(api / "sessions.json", sessions)
    write_json(api / "meta.json", queries.meta(conn))
    files += 2

    # one pass over all roll calls serves both the /votes/ tree and the
    # per-bill payloads; grouping preserves the query's (date, id) order.
    # One grouped scan replaces a per-event query; the lists live exactly
    # as long as events_by_bill kept them before (shared objects, no copy).
    records_by_event = dict(queries.vote_records_grouped(conn))
    events_by_bill: dict[str, list[dict]] = {}
    for event in queries.vote_events(conn):
        records = records_by_event.get(event["id"], [])
        write_json(api / "votes" / f"{event['id']}.json", {**event, "records": records})
        files += 1
        events_by_bill.setdefault(event["bill_id"], []).append(
            {
                "id": event["id"],
                "date": event["date"],
                "chamber": event["chamber"],
                "motion": event["motion"],
                "result": event["result"],
                "yes_count": event["yes_count"],
                "no_count": event["no_count"],
                "nv_count": event["nv_count"],
                "source_url": event["source_url"],
                "records": records,
            }
        )

    for session in sessions:
        session_id = session["id"]
        session_bills = queries.bills(conn, session_id)
        index = [
            {
                "id": b["id"],
                "identifier": b["identifier"],
                "title": b["title"],
                "status": b["status"],
                "latest_action_date": b["latest_action_date"],
                "died_without_hearing": b["died_without_hearing"],
            }
            for b in session_bills
        ]
        write_json(api / "bills" / session_id / "index.json", index)
        files += 1

        # two grouped scans per session replace two queries per bill
        session_sponsors = queries.sponsors_for_session(conn, session_id)
        session_actions = queries.actions_for_session(conn, session_id)
        # companion edges are an enrichment; the table may not exist yet
        companions: dict[str, list[dict]] = {}
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bill_companions'"
        ).fetchone():
            for row in conn.execute(
                """SELECT bc.bill_id, b.identifier, b.status FROM bill_companions bc
                   JOIN bills b ON b.id = bc.companion_bill_id
                   WHERE b.session_id = ? ORDER BY b.identifier""",
                (session_id,),
            ):
                companions.setdefault(row[0], []).append(
                    {"identifier": row[1], "status": row[2]}
                )
        for bill in session_bills:
            payload = {
                **{k: bill[k] for k in bill.keys() if k != "session_id"},
                "session": session_id,
                "sponsors": session_sponsors.get(bill["id"], []),
                "actions": session_actions.get(bill["id"], []),
                "votes": events_by_bill.get(bill["id"], []),
                "companions": companions.get(bill["id"], []),
            }
            write_json(
                api / "bills" / session_id / f"{bill_slug(bill['identifier'])}.json",
                payload,
            )
            files += 1

    write_json(
        api / "elections" / "statewide.json",
        {
            "races": queries.statewide_races(conn),
            "history": queries.statewide_history(conn),
            "counties": queries.statewide_counties(conn),
        },
    )
    files += 1

    people = queries.people(conn)
    write_json(
        api / "legislators" / "index.json",
        [
            {
                "id": person_slug(p["id"]),
                "name": p["name"],
                "party": p["party"],
                "chamber": p["chamber"],
                "district": p["district"],
            }
            for p in people
        ],
    )
    files += 1
    for person in people:
        payload = {
            **person,
            "id": person_slug(person["id"]),
            "election": queries.election_for(conn, person["id"]),
            "sponsorships": queries.sponsorships_by_person(conn, person["id"]),
            "votes": queries.votes_by_person(conn, person["id"]),
        }
        write_json(api / "legislators" / f"{person_slug(person['id'])}.json", payload)
        files += 1

    return files
