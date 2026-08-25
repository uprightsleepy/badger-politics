"""Shared read layer for all data products — the provenance filter lives here.

Every bill/vote/election query excludes source='legiscan' rows (ToS boundary:
LegiScan data is display-only and never exported). New products must read
through these helpers, not raw SQL.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def exportable(alias: str = "") -> str:
    """The provenance filter, optionally table-qualified: exportable('b.')."""
    return f"COALESCE({alias}source, 'openstates') != 'legiscan'"


EXPORTABLE = exportable()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def sessions(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM sessions ORDER BY identifier")]


def meta(conn: sqlite3.Connection) -> dict:
    return dict(conn.execute("SELECT key, value FROM meta"))


def people(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM people ORDER BY chamber, district")]


def bills(
    conn: sqlite3.Connection, session_id: str | None = None, columns: str = "*"
) -> list[dict]:
    query = f"SELECT {columns} FROM bills WHERE {EXPORTABLE}"  # noqa: S608 - callers pass literals
    params: tuple = ()
    if session_id:
        query += " AND session_id = ?"
        params = (session_id,)
    return [dict(r) for r in conn.execute(query + " ORDER BY id", params)]


def actions_for(conn: sqlite3.Connection, bill_id: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT date, chamber, description, classification FROM actions"
            " WHERE bill_id = ? ORDER BY date, id",
            (bill_id,),
        )
    ]


def sponsors_for(conn: sqlite3.Connection, bill_id: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT s.name, s.person_id, s.classification, s.is_primary,"
            " p.party, p.district, p.chamber"
            " FROM sponsorships s LEFT JOIN people p ON p.id = s.person_id"
            " WHERE s.bill_id = ? ORDER BY s.is_primary DESC, s.name",
            (bill_id,),
        )
    ]


def vote_events(conn: sqlite3.Connection) -> list[dict]:
    query = f"SELECT * FROM vote_events WHERE {EXPORTABLE}"
    return [dict(r) for r in conn.execute(query + " ORDER BY date, id")]


def vote_records_for(conn: sqlite3.Connection, vote_event_id: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT r.person_id, r.option, p.name, p.party, p.district, p.chamber"
            " FROM vote_records r JOIN people p ON p.id = r.person_id"
            " WHERE r.vote_event_id = ? ORDER BY p.name",
            (vote_event_id,),
        )
    ]


def votes_by_person(
    conn: sqlite3.Connection, person_id: str, limit: int | None = None
) -> list[dict]:
    # ORDER BY is deterministic, so LIMIT returns exactly the unlimited head
    tail = " LIMIT ?" if limit is not None else ""
    params = (person_id, limit) if limit is not None else (person_id,)
    return [
        dict(r)
        for r in conn.execute(
            f"""SELECT r.option, e.id AS vote_event_id, e.date, e.motion, e.result,
                       e.bill_id, b.identifier, b.title
                FROM vote_records r
                JOIN vote_events e ON e.id = r.vote_event_id AND {exportable("e.")}
                JOIN bills b ON b.id = e.bill_id
                WHERE r.person_id = ? ORDER BY e.date DESC, e.id{tail}""",
            params,
        )
    ]


def sponsorships_by_person(conn: sqlite3.Connection, person_id: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            f"""SELECT s.classification, s.is_primary, b.id AS bill_id, b.identifier,
                       b.title, b.status, b.session_id
                FROM sponsorships s
                JOIN bills b ON b.id = s.bill_id AND {exportable("b.")}
                WHERE s.person_id = ? ORDER BY b.id""",
            (person_id,),
        )
    ]


def election_for(conn: sqlite3.Connection, person_id: str) -> dict | None:
    row = conn.execute(
        f"SELECT cycle_year, office, district, on_ballot, is_incumbent, opponents_json"
        f" FROM elections WHERE person_id = ? AND {EXPORTABLE}",
        (person_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["opponents"] = json.loads(result.pop("opponents_json") or "[]")
    return result


def statewide_races(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute("SELECT * FROM statewide_races ORDER BY office, candidate")
    ]


def statewide_history(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM statewide_history ORDER BY year DESC, office, votes DESC"
        )
    ]


def statewide_counties(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM statewide_county_results"
            " ORDER BY year DESC, office, county, votes DESC"
        )
    ]


def hearings(conn: sqlite3.Connection) -> list[dict]:
    rows = [
        dict(r)
        for r in conn.execute(
            "SELECT h.*, c.name AS committee_name, c.chamber AS committee_chamber"
            " FROM hearings h LEFT JOIN committees c ON c.id = h.committee_id"
            " ORDER BY h.date, h.time"
        )
    ]
    for row in rows:
        row["agenda_bills"] = json.loads(row.pop("agenda_bill_ids_json") or "[]")
    return rows
