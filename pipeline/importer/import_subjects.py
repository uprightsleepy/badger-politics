"""Load archived subject index files into bill_subjects.

Usage: python -m importer.import_subjects <archives_dir> <sqlite_path>

Rows are written only for exact session + identifier matches; anything
unmatched is counted and reported, never guessed across sessions.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

YEAR_RE = re.compile(r"subjects-(\d{4})\.json$")


def run(archives_dir: Path, db_path: Path) -> int:
    files = sorted(archives_dir.glob("subjects-*.json"))
    if not files:
        raise RuntimeError(f"no subject archives in {archives_dir}; run scraper.fetch_subjects")
    conn = sqlite3.connect(db_path)
    total, unmatched = 0, 0
    with conn:
        conn.execute("DELETE FROM bill_subjects")
        for path in files:
            year = YEAR_RE.search(path.name).group(1)
            known = {
                identifier: bill_id
                for bill_id, identifier in conn.execute(
                    "SELECT id, identifier FROM bills WHERE session_id = ?", (year,)
                )
            }
            batch = []
            for subject, identifiers in json.loads(path.read_text(encoding="utf-8")).items():
                for identifier in identifiers:
                    bill_id = known.get(identifier)
                    if bill_id is None:
                        unmatched += 1
                        continue
                    batch.append((bill_id, subject))
            conn.executemany(
                "INSERT INTO bill_subjects (bill_id, subject) VALUES (?, ?)", batch
            )
            total += len(batch)
    subjects = conn.execute("SELECT COUNT(DISTINCT subject) FROM bill_subjects").fetchone()[0]
    conn.close()
    print(
        f"bill_subjects: {total} rows across {subjects} subjects"
        + (f" ({unmatched} references skipped: bill not in db)" if unmatched else "")
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.archives_dir, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
