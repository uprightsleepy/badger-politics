"""Shared read layer for all data products — the provenance filter lives here.

Every bill/vote/election query excludes source='legiscan' rows (ToS boundary:
LegiScan data is display-only and never exported). New products must read
through these helpers, not raw SQL.
"""

from __future__ import annotations

import itertools
import json
import re
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


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params)]


def sessions(conn: sqlite3.Connection) -> list[dict]:
    return _rows(conn, "SELECT * FROM sessions ORDER BY identifier")


def meta(conn: sqlite3.Connection) -> dict:
    return dict(conn.execute("SELECT key, value FROM meta"))


def people(conn: sqlite3.Connection) -> list[dict]:
    return _rows(conn, "SELECT * FROM people ORDER BY chamber, district")


# the only shapes callers may splice into SELECT: '*' or a comma list of
# plain column names — anything else is a programming error, not data
_COLUMNS_RE = re.compile(r"^\*$|^[a-z_]+(, ?[a-z_]+)*$")


def bills(
    conn: sqlite3.Connection, session_id: str | None = None, columns: str = "*"
) -> list[dict]:
    if not _COLUMNS_RE.fullmatch(columns):
        raise ValueError(f"bills(columns=...) must be '*' or column names: {columns!r}")
    query = f"SELECT {columns} FROM bills WHERE {EXPORTABLE}"  # noqa: S608 - allowlisted above
    params: tuple = ()
    if session_id:
        query += " AND session_id = ?"
        params = (session_id,)
    return _rows(conn, query + " ORDER BY id", params)


def actions_for(conn: sqlite3.Connection, bill_id: str) -> list[dict]:
    return _rows(
        conn,
        "SELECT date, chamber, description, classification FROM actions"
        " WHERE bill_id = ? ORDER BY date, id",
        (bill_id,),
    )


def sponsors_for(conn: sqlite3.Connection, bill_id: str) -> list[dict]:
    return _rows(
        conn,
        "SELECT s.name, s.person_id, s.classification, s.is_primary,"
        " p.party, p.district, p.chamber"
        " FROM sponsorships s LEFT JOIN people p ON p.id = s.person_id"
        " WHERE s.bill_id = ? ORDER BY s.is_primary DESC, s.name",
        (bill_id,),
    )


def vote_events(conn: sqlite3.Connection) -> list[dict]:
    query = f"SELECT * FROM vote_events WHERE {EXPORTABLE}"
    return _rows(conn, query + " ORDER BY date, id")


def vote_records_for(conn: sqlite3.Connection, vote_event_id: str) -> list[dict]:
    return _rows(
        conn,
        "SELECT r.person_id, r.option, p.name, p.party, p.district, p.chamber"
        " FROM vote_records r JOIN people p ON p.id = r.person_id"
        " WHERE r.vote_event_id = ? ORDER BY p.name",
        (vote_event_id,),
    )


def vote_records_grouped(conn: sqlite3.Connection):
    """(vote_event_id, records) streamed from one ordered scan; each
    record dict is shaped exactly like vote_records_for's rows."""
    cursor = conn.execute(
        "SELECT r.vote_event_id, r.person_id, r.option,"
        " p.name, p.party, p.district, p.chamber"
        " FROM vote_records r JOIN people p ON p.id = r.person_id"
        " ORDER BY r.vote_event_id, p.name"
    )
    for event_id, rows in itertools.groupby(cursor, key=lambda r: r["vote_event_id"]):
        yield event_id, [
            {k: r[k] for k in
             ("person_id", "option", "name", "party", "district", "chamber")}
            for r in rows
        ]


def actions_grouped(conn: sqlite3.Connection):
    """(bill_id, actions) for every exportable bill with actions, streamed
    in bill-id order from one scan; row shape matches actions_for."""
    cursor = conn.execute(
        "SELECT a.bill_id, a.date, a.chamber, a.description, a.classification"
        " FROM actions a JOIN bills b ON b.id = a.bill_id"
        f" WHERE {exportable('b.')}"
        " ORDER BY a.bill_id, a.date, a.id"
    )
    for bill_id, rows in itertools.groupby(cursor, key=lambda r: r["bill_id"]):
        yield bill_id, [
            {k: r[k] for k in ("date", "chamber", "description", "classification")}
            for r in rows
        ]


def actions_for_session(conn: sqlite3.Connection, session_id: str) -> dict[str, list[dict]]:
    """bill_id -> actions for one session, from one ordered scan; row
    shape and per-bill order match actions_for exactly."""
    cursor = conn.execute(
        "SELECT a.bill_id, a.date, a.chamber, a.description, a.classification"
        " FROM actions a JOIN bills b ON b.id = a.bill_id"
        f" WHERE b.session_id = ? AND {exportable('b.')}"
        " ORDER BY a.bill_id, a.date, a.id",
        (session_id,),
    )
    return {
        bill_id: [
            {k: r[k] for k in ("date", "chamber", "description", "classification")}
            for r in rows
        ]
        for bill_id, rows in itertools.groupby(cursor, key=lambda r: r["bill_id"])
    }


def sponsors_for_session(conn: sqlite3.Connection, session_id: str) -> dict[str, list[dict]]:
    """bill_id -> sponsors for one session, from one ordered scan; row
    shape and per-bill order match sponsors_for exactly."""
    cursor = conn.execute(
        "SELECT s.bill_id, s.name, s.person_id, s.classification, s.is_primary,"
        " p.party, p.district, p.chamber"
        " FROM sponsorships s LEFT JOIN people p ON p.id = s.person_id"
        " JOIN bills b ON b.id = s.bill_id"
        f" WHERE b.session_id = ? AND {exportable('b.')}"
        " ORDER BY s.bill_id, s.is_primary DESC, s.name",
        (session_id,),
    )
    return {
        bill_id: [
            {k: r[k] for k in
             ("name", "person_id", "classification", "is_primary",
              "party", "district", "chamber")}
            for r in rows
        ]
        for bill_id, rows in itertools.groupby(cursor, key=lambda r: r["bill_id"])
    }


def votes_by_person(
    conn: sqlite3.Connection, person_id: str, limit: int | None = None
) -> list[dict]:
    # ORDER BY is deterministic, so LIMIT returns exactly the unlimited head
    tail = " LIMIT ?" if limit is not None else ""
    params = (person_id, limit) if limit is not None else (person_id,)
    return _rows(
        conn,
        f"""SELECT r.option, e.id AS vote_event_id, e.date, e.motion, e.result,
                   e.bill_id, b.identifier, b.title
            FROM vote_records r
            JOIN vote_events e ON e.id = r.vote_event_id AND {exportable("e.")}
            JOIN bills b ON b.id = e.bill_id
            WHERE r.person_id = ? ORDER BY e.date DESC, e.id{tail}""",
        params,
    )


def sponsorships_by_person(conn: sqlite3.Connection, person_id: str) -> list[dict]:
    return _rows(
        conn,
        f"""SELECT s.classification, s.is_primary, b.id AS bill_id, b.identifier,
                   b.title, b.status, b.session_id
            FROM sponsorships s
            JOIN bills b ON b.id = s.bill_id AND {exportable("b.")}
            WHERE s.person_id = ? ORDER BY b.id""",
        (person_id,),
    )


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
    return _rows(conn, "SELECT * FROM statewide_races ORDER BY office, candidate")


def statewide_history(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn, "SELECT * FROM statewide_history ORDER BY year DESC, office, votes DESC"
    )


def statewide_counties(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn,
        "SELECT * FROM statewide_county_results"
        " ORDER BY year DESC, office, county, votes DESC",
    )


def hearings(conn: sqlite3.Connection) -> list[dict]:
    rows = _rows(
        conn,
        "SELECT h.*, c.name AS committee_name, c.chamber AS committee_chamber"
        " FROM hearings h LEFT JOIN committees c ON c.id = h.committee_id"
        " ORDER BY h.date, h.time",
    )
    for row in rows:
        row["agenda_bills"] = json.loads(row.pop("agenda_bill_ids_json") or "[]")
    return rows


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def local_bodies(conn: sqlite3.Connection) -> list[dict]:
    """Covered city councils; empty when the enrichment tables are absent."""
    if not _has_table(conn, "local_bodies"):
        return []
    return _rows(conn, "SELECT * FROM local_bodies ORDER BY city")


def local_members(conn: sqlite3.Connection, tenant: str) -> list[dict]:
    return _rows(
        conn,
        """SELECT m.*, (SELECT COUNT(*) FROM local_votes v
                        WHERE v.tenant = m.tenant AND v.person_id = m.person_id) AS vote_count
           FROM local_members m WHERE m.tenant = ? ORDER BY m.seat, m.name""",
        (tenant,),
    )


def local_member_votes(
    conn: sqlite3.Connection, tenant: str, person_id: int, limit: int = 100
) -> list[dict]:
    return _rows(
        conn,
        """SELECT v.value, a.event_item_id, a.matter_file, a.title, a.action,
                  a.matter_url, e.date, e.insite_url
           FROM local_votes v
           JOIN local_actions a ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id
           JOIN local_events e ON e.tenant = a.tenant AND e.event_id = a.event_id
           WHERE v.tenant = ? AND v.person_id = ?
           ORDER BY e.date DESC, a.event_item_id DESC LIMIT ?""",
        (tenant, person_id, limit),
    )
