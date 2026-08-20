"""Wisconsin legislative election-cycle rules + elections table population.

Usage: python -m importer.elections <sqlite_path> --cycle 2026

Hardcoded WI rules (tested; see plan §4):
- Assembly: all 99 districts every even year.
- Senate: 4-year terms, staggered — odd-numbered districts in midterm years
  (2026, 2030, ...), even-numbered districts in presidential years
  (2028, 2032, ...).

Populates one elections row per sitting legislator: the next election their
seat faces. on_ballot/opponents_json stay NULL until the WEC overlay
(import_wec) fills them.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def assembly_districts_on_ballot(cycle_year: int) -> list[int]:
    if cycle_year % 2:
        return []
    return list(range(1, 100))


def senate_districts_on_ballot(cycle_year: int) -> list[int]:
    if cycle_year % 2:
        return []
    if cycle_year % 4 == 2:  # midterm: 2026, 2030, ...
        return [d for d in range(1, 34) if d % 2 == 1]
    return [d for d in range(1, 34) if d % 2 == 0]  # presidential: 2028, ...


def next_election_year(chamber: str, district: int, from_year: int) -> int:
    """The next year this seat is on the ballot, starting at from_year."""
    year = from_year + (from_year % 2)  # next even year (or this one)
    while True:
        on_ballot = (
            assembly_districts_on_ballot(year)
            if chamber == "lower"
            else senate_districts_on_ballot(year)
        )
        if district in on_ballot:
            return year
        year += 2


def populate(db_path: Path, cycle_year: int) -> None:
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("DELETE FROM elections")
        people = conn.execute(
            "SELECT id, chamber, district FROM people"
            " WHERE chamber IN ('lower', 'upper') AND district IS NOT NULL"
        ).fetchall()
        for person_id, chamber, district in people:
            year = next_election_year(chamber, district, cycle_year)
            office = "State Assembly" if chamber == "lower" else "State Senate"
            conn.execute(
                "INSERT INTO elections (person_id, cycle_year, office, district,"
                " is_incumbent, source) VALUES (?, ?, ?, ?, 1, 'manual')",
                (person_id, year, office, district),
            )
    count = conn.execute("SELECT COUNT(*) FROM elections").fetchone()[0]
    on_cycle = conn.execute(
        "SELECT COUNT(*) FROM elections WHERE cycle_year = ?", (cycle_year,)
    ).fetchone()[0]
    conn.close()
    print(f"elections: {count} seats populated, {on_cycle} on the {cycle_year} ballot")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--cycle", type=int, required=True)
    ns = parser.parse_args(argv)
    populate(ns.db_path, ns.cycle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
