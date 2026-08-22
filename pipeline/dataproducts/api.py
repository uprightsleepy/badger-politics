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


def bill_slug(bill: dict) -> str:
    return bill["identifier"].replace(" ", "").lower()


def person_slug(person_id: str) -> str:
    return person_id.rsplit("/", 1)[-1]


def build_api(conn: sqlite3.Connection, out: Path) -> int:
    api = out / "api" / "v1"
    files = 0

    sessions = queries.sessions(conn)
    write_json(api / "sessions.json", sessions)
    write_json(api / "meta.json", queries.meta(conn))
    files += 2

    # one pass over all roll calls serves both the /votes/ tree and the
    # per-bill payloads; grouping preserves the query's (date, id) order
    events_by_bill: dict[str, list[dict]] = {}
    for event in queries.vote_events(conn):
        records = queries.vote_records_for(conn, event["id"])
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

        for bill in session_bills:
            payload = {
                **{k: bill[k] for k in bill.keys() if k != "session_id"},
                "session": session_id,
                "sponsors": queries.sponsors_for(conn, bill["id"]),
                "actions": queries.actions_for(conn, bill["id"]),
                "votes": events_by_bill.get(bill["id"], []),
            }
            write_json(api / "bills" / session_id / f"{bill_slug(bill)}.json", payload)
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
