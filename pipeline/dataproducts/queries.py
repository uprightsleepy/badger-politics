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


def named_donor(type_column: str) -> str:
    """Whether a money counterparty may be named (README mandate 5:
    individual donors appear only in aggregate). An untyped counterparty
    could be a person, so it is treated as one."""
    return f"COALESCE({type_column}, 'Individual') != 'Individual'"


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params)]


def has_table(conn: sqlite3.Connection, name: str) -> bool:
    """Releases build from the newest snapshot, which may predate a new table."""
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


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
    # same-day actions keep the importer's insertion order; text ids would
    # sort '-a10' before '-a8'
    return _rows(
        conn,
        "SELECT date, chamber, description, classification FROM actions"
        " WHERE bill_id = ? ORDER BY date, rowid",
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
    # an openstates roll call on a legiscan bill is withheld with its bill
    query = (
        "SELECT e.* FROM vote_events e JOIN bills b ON b.id = e.bill_id"
        f" WHERE {exportable('e.')} AND {exportable('b.')}"
    )
    return _rows(conn, query + " ORDER BY e.date, e.id")


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
        " ORDER BY a.bill_id, a.date, a.rowid"
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
        " ORDER BY a.bill_id, a.date, a.rowid",
        (session_id,),
    )
    return {
        bill_id: [
            {k: r[k] for k in ("date", "chamber", "description", "classification")}
            for r in rows
        ]
        for bill_id, rows in itertools.groupby(cursor, key=lambda r: r["bill_id"])
    }


def links_for_session(
    conn: sqlite3.Connection, session_id: str, table: str
) -> dict[str, list[dict]]:
    """bill_id -> official links (bill_versions or bill_documents) for one
    session, in import order."""
    if table not in ("bill_versions", "bill_documents"):
        raise ValueError(f"links_for_session: unknown table {table!r}")
    if not has_table(conn, table):
        return {}
    cursor = conn.execute(
        f"SELECT d.* FROM {table} d JOIN bills b ON b.id = d.bill_id"  # noqa: S608 - allowlisted
        f" WHERE b.session_id = ? AND {exportable('b.')} ORDER BY d.bill_id, d.rowid",
        (session_id,),
    )
    return {
        bill_id: [{k: r[k] for k in r.keys() if k != "bill_id"} for r in rows]
        for bill_id, rows in itertools.groupby(cursor, key=lambda r: r["bill_id"])
    }


def executive_orders(conn: sqlite3.Connection) -> list[dict]:
    """Newest first. Official links only; no LegiScan rows exist here."""
    if not has_table(conn, "executive_orders"):
        return []
    return _rows(conn, "SELECT governor, year, number, suffix, url FROM executive_orders"
                       " ORDER BY year DESC, folder DESC, number DESC, suffix DESC")


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
            JOIN bills b ON b.id = e.bill_id AND {exportable("b.")}
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


# The district map a general election was held under: 2011 Act 43 (first
# used in 2012), the maps the state Supreme Court adopted in 2022, and 2024
# Act 94. A seat's number names different ground under each.
MAPS = ("CASE WHEN year >= 2024 THEN '2024' WHEN year >= 2022 THEN '2022'"
        " WHEN year >= 2012 THEN '2011' END")


def election_history(conn: sqlite3.Connection) -> list[dict]:
    """Certified WEC results for every legislative seat, newest first."""
    return _rows(
        conn,
        f"SELECT chamber, district, year, {MAPS} AS maps, candidate, party, votes, total_cast"
        " FROM election_history ORDER BY chamber, district, year DESC, votes DESC",
    )


def judicial_history(conn: sqlite3.Connection) -> list[dict]:
    """Certified Supreme Court and Court of Appeals results, newest first."""
    if not has_table(conn, "judicial_history"):
        return []
    return _rows(
        conn,
        "SELECT * FROM judicial_history"
        " ORDER BY year DESC, office DESC, district, votes DESC",
    )


def referendum_history(conn: sqlite3.Connection) -> list[dict]:
    """Certified statewide referendum results, newest first."""
    if not has_table(conn, "referendum_history"):
        return []
    return _rows(
        conn, "SELECT * FROM referendum_history ORDER BY year DESC, election, question"
    )


def congressional_races(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn,
        f"SELECT * FROM congressional_races WHERE {EXPORTABLE} ORDER BY district, candidate",
    )


def sitting_legislators(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn,
        "SELECT id, name, party, chamber, district FROM people"
        " WHERE current_role IN ('Representative', 'Senator') ORDER BY chamber, district",
    )


CENSUS_NOTICE = ("This product uses the Census Bureau Data API but is not endorsed or"
                 " certified by the Census Bureau.")


def district_demographics(conn: sqlite3.Connection) -> dict[tuple[str, int], dict]:
    """ACS figures per seat, with their release, map and the Census notice.
    Older snapshots predate the table: no seat has figures."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'district_demographics'"
                        ).fetchone():
        return {}
    seats: dict[tuple[str, int], dict] = {}
    for r in _rows(conn, "SELECT * FROM district_demographics ORDER BY chamber, district"):
        seat = seats.setdefault((r["chamber"], r["district"]), {
            "acs_year": r["acs_year"], "map_year": r["map_year"],
            "source_url": f"https://api.census.gov/data/{r['acs_year']}/acs/acs5/profile.html",
            "notice": CENSUS_NOTICE, "margin_of_error": "90% confidence", "figures": {}})
        seat["figures"][r["measure"]] = {k: int(r[k]) if r[k].is_integer() else r[k]
                                         for k in ("estimate", "moe")}
    return seats


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


def committees(conn: sqlite3.Connection) -> list[dict]:
    return _rows(
        conn,
        "SELECT c.id, c.name, c.chamber, c.chair_person_id, p.name AS chair_name"
        " FROM committees c LEFT JOIN people p ON p.id = c.chair_person_id ORDER BY c.name",
    )


def committee_members(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """committee_id -> members, chairs first (the site's ROLE_ORDER)."""
    cursor = conn.execute(
        "SELECT m.committee_id, m.person_id, m.role, p.name, p.party, p.chamber, p.district"
        " FROM committee_members m JOIN people p ON p.id = m.person_id"
        " ORDER BY m.committee_id, CASE WHEN m.role = 'chair' THEN 0"
        " WHEN m.role LIKE 'co-chair%' THEN 1 WHEN m.role LIKE 'vice%' THEN 2 ELSE 3 END,"
        " p.name"
    )
    return {
        committee_id: [
            {k: r[k] for k in ("person_id", "role", "name", "party", "chamber", "district")}
            for r in rows
        ]
        for committee_id, rows in itertools.groupby(cursor, key=lambda r: r["committee_id"])
    }


def subject_bills(conn: sqlite3.Connection) -> list[dict]:
    """Every (subject heading, exportable bill) pair, newest session first."""
    return _rows(
        conn,
        "SELECT s.subject, b.id, b.identifier, b.session_id, b.title, b.status"
        " FROM bill_subjects s JOIN bills b ON b.id = s.bill_id"
        f" WHERE {exportable('b.')} ORDER BY b.session_id DESC, b.id",
    )


def subject_actions(conn: sqlite3.Connection, per_subject: int) -> list[sqlite3.Row]:
    """The newest actions on each subject heading's exportable bills; seq is
    the insertion order that breaks same-day ties, as in actions_for."""
    return conn.execute(
        f"""SELECT * FROM (
              SELECT s.subject, a.id, a.date, a.description, b.identifier, b.title,
                     b.session_id, a.rowid AS seq,
                     ROW_NUMBER() OVER (PARTITION BY s.subject
                                        ORDER BY a.date DESC, a.rowid DESC) AS n
              FROM bill_subjects s
              JOIN bills b ON b.id = s.bill_id AND {exportable("b.")}
              JOIN actions a ON a.bill_id = b.id)
            WHERE n <= ?""",
        (per_subject,),
    ).fetchall()


def federal_members(conn: sqlite3.Connection) -> list[dict]:
    return _rows(conn, "SELECT * FROM federal_members ORDER BY chamber DESC, district")


def federal_votes_for(conn: sqlite3.Connection, member: dict) -> list[dict]:
    """A member's floor roll calls, keyed as each chamber records them: the
    Senate's LIS id for senators, bioguide for House members."""
    key = member["lis_id"] if member["chamber"] == "senate" else member["bioguide"]
    return _rows(
        conn,
        "SELECT v.id, v.congress, v.session, v.number, v.date, v.question, v.result,"
        " v.title, v.yeas, v.nays, v.majority_requirement, v.document, v.source_url,"
        " r.vote_cast FROM federal_votes v JOIN federal_vote_records r ON r.vote_id = v.id"
        " WHERE r.member_id = ? ORDER BY v.date DESC, v.number DESC",
        (key,),
    )


def local_bodies(conn: sqlite3.Connection) -> list[dict]:
    """Covered city councils."""
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


# ---- Campaign money, at the level the site's money pages publish it
# (README mandate 5): committees by name and CFIS entity id, individual
# donors only in totals, outside spending one filing at a time.

def money_people(conn: sqlite3.Connection) -> list[str]:
    """People with collected receipts; anyone else is unlinked, never $0."""
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT person_id FROM contributions ORDER BY person_id")]


def legislator_money(conn: sqlite3.Connection, person_id: str) -> dict:
    """All collected history of one person's receipts, as the profile's
    money card groups it."""
    p = (person_id,)
    summary = _rows(
        conn,
        "SELECT COUNT(*) AS receipts, COALESCE(SUM(amount), 0) AS total,"
        " COALESCE(SUM(CASE WHEN from_type = 'Individual' THEN amount ELSE 0 END), 0)"
        " AS individual_total, MIN(date) AS first, MAX(date) AS last"
        " FROM contributions WHERE person_id = ?", p,
    )[0]
    return {
        **summary,
        "by_type": _rows(
            conn,
            "SELECT COALESCE(from_type, 'Other') AS type, SUM(amount) AS total,"
            " COUNT(*) AS receipts FROM contributions WHERE person_id = ?"
            " GROUP BY COALESCE(from_type, 'Other') ORDER BY total DESC", p,
        ),
        "quarters": _rows(
            conn,
            "SELECT substr(date, 1, 4) || '-Q' || ((CAST(substr(date, 6, 2) AS INTEGER) + 2) / 3)"
            " AS quarter, SUM(amount) AS total FROM contributions"
            " WHERE person_id = ? AND date != '' GROUP BY quarter ORDER BY quarter", p,
        ),
        "top_committees": _rows(
            conn,
            "SELECT from_entity_id AS entity_id, MAX(from_name) AS name,"
            " SUM(amount) AS total, COUNT(*) AS receipts FROM contributions"
            " WHERE person_id = ? AND from_type = 'Registrant' AND from_entity_id IS NOT NULL"
            " GROUP BY from_entity_id ORDER BY total DESC LIMIT 5", p,
        ),
        # donor-reported occupations, summed: says nothing about any employer
        "top_occupations": _rows(
            conn,
            "SELECT MAX(TRIM(occupation)) AS occupation, SUM(amount) AS total,"
            " COUNT(*) AS receipts FROM contributions"
            " WHERE person_id = ? AND from_type = 'Individual'"
            " AND occupation IS NOT NULL AND TRIM(occupation) != ''"
            " GROUP BY LOWER(TRIM(occupation)) ORDER BY total DESC LIMIT 5", p,
        ),
    }


def donor_committees(conn: sqlite3.Connection) -> list[dict]:
    """Committees that gave today's legislators $1,000 or more in all
    collected history: the site's /money/committees/ pages."""
    return _rows(
        conn,
        "SELECT c.from_entity_id AS entity_id, MAX(c.from_name) AS name,"
        " (SELECT committee_type FROM cf_committees WHERE entity_id = c.from_entity_id)"
        " AS committee_type, SUM(c.amount) AS total, COUNT(*) AS receipts,"
        " COUNT(DISTINCT c.person_id) AS recipients, MIN(c.date) AS first, MAX(c.date) AS last"
        " FROM contributions c WHERE c.from_type = 'Registrant' AND c.from_entity_id IS NOT NULL"
        " GROUP BY c.from_entity_id HAVING SUM(c.amount) >= 1000 ORDER BY total DESC",
    )


def donor_recipients(conn: sqlite3.Connection) -> dict[int, list[dict]]:
    """committee entity id -> the legislators it gave to, largest first."""
    cursor = conn.execute(
        "SELECT c.from_entity_id, c.person_id, p.name, p.party, p.chamber, p.district,"
        " SUM(c.amount) AS total, COUNT(*) AS receipts, MIN(c.date) AS first,"
        " MAX(c.date) AS last FROM contributions c JOIN people p ON p.id = c.person_id"
        " WHERE c.from_type = 'Registrant' AND c.from_entity_id IS NOT NULL"
        " GROUP BY c.from_entity_id, c.person_id ORDER BY c.from_entity_id, total DESC"
    )
    return {
        entity_id: [{k: r[k] for k in r.keys() if k != "from_entity_id"} for r in rows]
        for entity_id, rows in itertools.groupby(cursor, key=lambda r: r["from_entity_id"])
    }


def committee_own_money(conn: sqlite3.Connection, entity_id: int) -> dict | None:
    """A committee's own reported money, like the site's "Its own money".
    None for candidate committees: their receipts are collected through the
    verified legislator map, so the rows here would be a misleading fraction."""
    committee = conn.execute(
        "SELECT committee_type FROM cf_committees WHERE entity_id = ?", (entity_id,)
    ).fetchone()
    if committee is None or committee[0] in ("State Candidate", "Federal Candidate"):
        return None
    p = (entity_id,)
    totals = _rows(
        conn,
        "SELECT COALESCE(SUM(CASE WHEN direction = 'INCOMING' THEN amount END), 0) AS raised,"
        " COALESCE(SUM(CASE WHEN direction = 'OUTGOING' THEN amount END), 0) AS spent,"
        " COUNT(*) AS transactions, MIN(date) AS first, MAX(date) AS last"
        " FROM cf_transactions WHERE filer_entity_id = ?", p,
    )[0]

    def side(direction: str) -> dict:
        named = _rows(
            conn,
            "SELECT other_entity_id AS entity_id, MAX(other_name) AS name,"
            " MAX(other_type) AS type, SUM(amount) AS total, COUNT(*) AS transactions"
            " FROM cf_transactions WHERE filer_entity_id = ? AND direction = ?"
            f" AND other_name IS NOT NULL AND {named_donor('other_type')}"
            " GROUP BY COALESCE(other_entity_id, other_name) ORDER BY total DESC LIMIT 50",
            (entity_id, direction),
        )
        individuals = _rows(
            conn,
            "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS transactions"
            " FROM cf_transactions WHERE filer_entity_id = ? AND direction = ?"
            f" AND NOT {named_donor('other_type')}",
            (entity_id, direction),
        )[0]
        return {"largest": named, "individuals": individuals}

    return {
        **totals,
        "itemized_donors": side("INCOMING"),
        "payees": side("OUTGOING"),
        "advocacy": _rows(
            conn,
            "SELECT id AS transaction_id, date, amount, stance, related_name,"
            " related_office, related_district, purpose, report_id, report_name"
            " FROM cf_transactions WHERE filer_entity_id = ? AND stance IS NOT NULL"
            " AND related_name IS NOT NULL ORDER BY date DESC, id DESC LIMIT 100", p,
        ),
    }


def independent_expenditures(conn: sqlite3.Connection, limit: int = -1) -> list[dict]:
    """Every outside-spending filing, as filed. Candidates' own stanced ads
    are their own spending, not third-party advocacy, and are left out."""
    return _rows(
        conn,
        "SELECT t.id AS transaction_id, t.date, t.amount, t.stance, t.related_name,"
        " t.related_office, t.related_district, t.purpose,"
        f" CASE WHEN {named_donor('t.other_type')} THEN t.other_name END AS paid_to,"
        " t.filer_entity_id, c.name AS filer_name, c.committee_type AS filer_type,"
        " t.report_id, t.report_name"
        " FROM cf_transactions t LEFT JOIN cf_committees c ON c.entity_id = t.filer_entity_id"
        " WHERE t.stance IS NOT NULL AND t.related_name IS NOT NULL"
        " AND COALESCE(t.filer_type, '') NOT IN ('State Candidate', 'Federal Candidate')"
        " ORDER BY t.date DESC, t.amount DESC, t.id DESC LIMIT ?",
        (limit,),
    )
