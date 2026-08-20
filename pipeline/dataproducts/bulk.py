"""Bulk exports: per-session CSVs + a provenance-filtered SQLite snapshot.

Written to data/exports/ (NOT the site tree — large files publish to GitHub
Releases in Phase 6 so the site origin never serves them; plan §11).

The SQLite snapshot is a real copy with every source='legiscan' row deleted
and VACUUMed out — the ToS boundary holds even for someone who downloads the
raw database.
"""

from __future__ import annotations

import csv
import shutil
import sqlite3
from pathlib import Path

from dataproducts import queries

CSV_TABLES = {
    "bills": f"SELECT * FROM bills WHERE {queries.EXPORTABLE} AND session_id = ?",
    "actions": (
        "SELECT a.* FROM actions a JOIN bills b ON b.id = a.bill_id"
        f" WHERE {queries.EXPORTABLE.replace('source', 'b.source')} AND b.session_id = ?"
    ),
    "sponsorships": (
        "SELECT s.* FROM sponsorships s JOIN bills b ON b.id = s.bill_id"
        f" WHERE {queries.EXPORTABLE.replace('source', 'b.source')} AND b.session_id = ?"
    ),
    "vote_events": (
        "SELECT e.* FROM vote_events e JOIN bills b ON b.id = e.bill_id"
        f" WHERE {queries.EXPORTABLE.replace('source', 'e.source')} AND b.session_id = ?"
    ),
    "vote_records": (
        "SELECT r.* FROM vote_records r"
        " JOIN vote_events e ON e.id = r.vote_event_id"
        " JOIN bills b ON b.id = e.bill_id"
        f" WHERE {queries.EXPORTABLE.replace('source', 'e.source')} AND b.session_id = ?"
    ),
}


def export_csvs(conn: sqlite3.Connection, exports_dir: Path) -> int:
    files = 0
    for session in queries.sessions(conn):
        session_dir = exports_dir / session["id"]
        session_dir.mkdir(parents=True, exist_ok=True)
        for table, query in CSV_TABLES.items():
            cursor = conn.execute(query, (session["id"],))
            columns = [d[0] for d in cursor.description]
            with (session_dir / f"{table}.csv").open(
                "w", newline="", encoding="utf-8"
            ) as fh:
                writer = csv.writer(fh)
                writer.writerow(columns)
                writer.writerows(cursor)
            files += 1
    # people are session-independent
    cursor = conn.execute("SELECT * FROM people")
    columns = [d[0] for d in cursor.description]
    with (exports_dir / "people.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows(cursor)
    return files + 1


def export_sqlite(db_path: Path, exports_dir: Path) -> Path:
    exports_dir.mkdir(parents=True, exist_ok=True)
    snapshot = exports_dir / "wi-filtered.sqlite"
    shutil.copyfile(db_path, snapshot)
    conn = sqlite3.connect(snapshot)
    with conn:
        conn.execute(
            "DELETE FROM vote_records WHERE vote_event_id IN"
            " (SELECT id FROM vote_events WHERE source = 'legiscan')"
        )
        conn.execute("DELETE FROM vote_events WHERE source = 'legiscan'")
        conn.execute(
            "DELETE FROM actions WHERE bill_id IN"
            " (SELECT id FROM bills WHERE source = 'legiscan')"
        )
        conn.execute(
            "DELETE FROM sponsorships WHERE bill_id IN"
            " (SELECT id FROM bills WHERE source = 'legiscan')"
        )
        conn.execute("DELETE FROM bills WHERE source = 'legiscan'")
        conn.execute("DELETE FROM elections WHERE source = 'legiscan'")
        conn.execute("DELETE FROM provenance WHERE source = 'legiscan'")
    conn.execute("VACUUM")
    remaining = conn.execute(
        "SELECT (SELECT COUNT(*) FROM bills WHERE source='legiscan')"
        " + (SELECT COUNT(*) FROM vote_events WHERE source='legiscan')"
        " + (SELECT COUNT(*) FROM elections WHERE source='legiscan')"
    ).fetchone()[0]
    conn.close()
    if remaining:
        raise RuntimeError(f"provenance filter failed: {remaining} legiscan rows remain")
    return snapshot


def build_bulk(conn: sqlite3.Connection, db_path: Path, exports_dir: Path) -> int:
    files = export_csvs(conn, exports_dir)
    export_sqlite(db_path, exports_dir)
    return files + 1
