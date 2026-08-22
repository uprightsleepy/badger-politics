"""Integrity gates run after every import; a failure aborts the deploy.
Hard rule: never weaken a gate to make a run pass.

Usage: python -m importer.checks <sqlite_path> [--counts-file PATH]
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
        # yes/no reconcile exactly (they decide outcomes); NV is all-or-none
        # because docs.legis sometimes omits the NV name list entirely
        # (2013 sv0012) — partial NV parses still fail, see patches/0002
        problems = (yes_c or 0) != yes_r or (no_c or 0) != no_r
        if nv_r != 0 and nv_r != (nv_c or 0):
            problems = True
        if problems:
            failures.append(
                f"vote {event_id}: stored counts y/n/nv="
                f"{(yes_c or 0, no_c or 0, nv_c or 0)} but records="
                f"{(yes_r, no_r, nv_r)}"
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
        "contributions -> people": (
            "SELECT COUNT(*) FROM contributions c"
            " LEFT JOIN people p ON p.id = c.person_id WHERE p.id IS NULL"
        ),
        # every receipt must trace to a live (committee, person) mapping;
        # a stale archive after a map change is a misattribution risk
        "contributions -> committee mapping": (
            "SELECT COUNT(*) FROM contributions c LEFT JOIN cfis_committees m"
            " ON m.entity_id = c.committee_entity_id AND m.person_id = c.person_id"
            " WHERE m.entity_id IS NULL"
        ),
        "one committee mapped to two people": (
            "SELECT COUNT(*) FROM (SELECT entity_id FROM cfis_committees"
            " GROUP BY entity_id HAVING COUNT(DISTINCT person_id) > 1)"
        ),
        "same person twice on one roll call": (
            "SELECT COUNT(*) FROM (SELECT vote_event_id, person_id FROM vote_records"
            " GROUP BY vote_event_id, person_id HAVING COUNT(*) > 1)"
        ),
        "hearing chairs -> people": (
            "SELECT COUNT(*) FROM committees c LEFT JOIN people p ON p.id = c.chair_person_id"
            " WHERE c.chair_person_id IS NOT NULL AND p.id IS NULL"
        ),
        "no vote outside a recorded term": (
            "SELECT COUNT(*) FROM vote_records r"
            " JOIN vote_events e ON e.id = r.vote_event_id"
            " WHERE e.date IS NOT NULL AND NOT EXISTS ("
            "   SELECT 1 FROM person_terms t WHERE t.person_id = r.person_id"
            "   AND e.date >= t.start AND e.date <= COALESCE(t.end, '9999'))"
        ),
        "person_terms -> people": (
            "SELECT COUNT(*) FROM person_terms t"
            " LEFT JOIN people p ON p.id = t.person_id WHERE p.id IS NULL"
        ),
        "every sitting member has a live term": (
            "SELECT COUNT(*) FROM people WHERE current_role IN"
            " ('Representative', 'Senator') AND id NOT IN"
            " (SELECT person_id FROM person_terms"
            "  WHERE end IS NULL OR end >= date('now'))"
        ),
        "hearing_videos -> hearings": (
            "SELECT COUNT(*) FROM hearing_videos v"
            " LEFT JOIN hearings h ON h.id = v.hearing_id WHERE h.id IS NULL"
        ),
        "bill_subjects -> bills": (
            "SELECT COUNT(*) FROM bill_subjects s"
            " LEFT JOIN bills b ON b.id = s.bill_id WHERE b.id IS NULL"
        ),
        "bill_documents -> bills": (
            "SELECT COUNT(*) FROM bill_documents d"
            " LEFT JOIN bills b ON b.id = d.bill_id WHERE b.id IS NULL"
        ),
        "committee_members -> committees": (
            "SELECT COUNT(*) FROM committee_members m"
            " LEFT JOIN committees c ON c.id = m.committee_id WHERE c.id IS NULL"
        ),
        "committee_members -> people": (
            "SELECT COUNT(*) FROM committee_members m"
            " LEFT JOIN people p ON p.id = m.person_id WHERE p.id IS NULL"
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
