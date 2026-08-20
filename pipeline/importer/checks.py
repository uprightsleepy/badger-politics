"""Integrity gates run after every import. A failure aborts the deploy.

Usage: python -m importer.checks <sqlite_path> [--counts-file PATH]

Gates (hard rule: never weaken one to make a run pass):
1. For every vote event with individual records, the per-option record sums
   must equal the stored yes/no/nv counts (mirrors the scraper's invariant).
2. Per-session bill count must be >= the previous successful run's count
   minus a small tolerance (catches a silently broken scrape). State lives
   in a small JSON file next to the database, updated only on success.
3. Referential integrity: every vote_record resolves to a person and a vote
   event, every bill to a session, every action/sponsorship to a bill.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

TOLERANCE_FRACTION = 0.02  # allow a 2% dip (e.g. scraper-side dedupe changes)


def check_vote_counts(conn: sqlite3.Connection) -> list[str]:
    failures = []
    rows = conn.execute(
        """
        SELECT e.id, e.yes_count, e.no_count, e.nv_count,
               SUM(CASE WHEN r.option = 'yes' THEN 1 ELSE 0 END),
               SUM(CASE WHEN r.option = 'no' THEN 1 ELSE 0 END),
               SUM(CASE WHEN r.option NOT IN ('yes', 'no') THEN 1 ELSE 0 END)
        FROM vote_events e
        JOIN vote_records r ON r.vote_event_id = e.id
        GROUP BY e.id
        """
    ).fetchall()
    for event_id, yes_c, no_c, nv_c, yes_r, no_r, nv_r in rows:
        expected = (yes_c or 0, no_c or 0, nv_c or 0)
        actual = (yes_r, no_r, nv_r)
        if expected != actual:
            failures.append(
                f"vote {event_id}: stored counts y/n/nv={expected} but records={actual}"
            )
    if not rows:
        failures.append("no vote events have individual vote records at all")
    return failures


def check_bill_counts(conn: sqlite3.Connection, counts_file: Path) -> list[str]:
    current = dict(
        conn.execute("SELECT session_id, COUNT(*) FROM bills GROUP BY session_id")
    )
    if not current:
        return ["bills table is empty"]
    previous = {}
    if counts_file.exists():
        previous = json.loads(counts_file.read_text(encoding="utf-8"))
    failures = []
    for session_id, prev_count in previous.items():
        now = current.get(session_id, 0)
        floor = int(prev_count * (1 - TOLERANCE_FRACTION))
        if now < floor:
            failures.append(
                f"session {session_id}: bill count fell {prev_count} -> {now}"
                f" (floor {floor}) — scrape looks broken"
            )
    if not failures:
        counts_file.write_text(json.dumps(current, indent=1), encoding="utf-8")
    return failures


def check_referential_integrity(conn: sqlite3.Connection) -> list[str]:
    queries = {
        "vote_records -> people": (
            "SELECT COUNT(*) FROM vote_records r"
            " LEFT JOIN people p ON p.id = r.person_id WHERE p.id IS NULL"
        ),
        "vote_records -> vote_events": (
            "SELECT COUNT(*) FROM vote_records r"
            " LEFT JOIN vote_events e ON e.id = r.vote_event_id WHERE e.id IS NULL"
        ),
        "vote_events -> bills": (
            "SELECT COUNT(*) FROM vote_events e"
            " LEFT JOIN bills b ON b.id = e.bill_id WHERE b.id IS NULL"
        ),
        "bills -> sessions": (
            "SELECT COUNT(*) FROM bills b"
            " LEFT JOIN sessions s ON s.id = b.session_id WHERE s.id IS NULL"
        ),
        "actions -> bills": (
            "SELECT COUNT(*) FROM actions a"
            " LEFT JOIN bills b ON b.id = a.bill_id WHERE b.id IS NULL"
        ),
        "sponsorships -> bills": (
            "SELECT COUNT(*) FROM sponsorships sp"
            " LEFT JOIN bills b ON b.id = sp.bill_id WHERE b.id IS NULL"
        ),
        "sponsorships -> people (when resolved)": (
            "SELECT COUNT(*) FROM sponsorships sp LEFT JOIN people p ON p.id = sp.person_id"
            " WHERE sp.person_id IS NOT NULL AND p.id IS NULL"
        ),
    }
    failures = []
    for label, query in queries.items():
        orphans = conn.execute(query).fetchone()[0]
        if orphans:
            failures.append(f"{label}: {orphans} orphaned rows")
    return failures


def run_checks(db_path: Path, counts_file: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        failures = check_vote_counts(conn)
        failures += check_bill_counts(conn, counts_file)
        failures += check_referential_integrity(conn)
    finally:
        conn.close()
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--counts-file", type=Path)
    ns = parser.parse_args(argv)
    counts_file = ns.counts_file or ns.db_path.parent / ".bill_counts.json"
    failures = run_checks(ns.db_path, counts_file)
    if failures:
        for failure in failures:
            print(f"CHECK FAILED: {failure}", file=sys.stderr)
        return 1
    print("all integrity checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
