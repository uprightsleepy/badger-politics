"""Load archived lobbying interests into lobbying_interests.

Usage: python -m importer.import_lobbying <archives_dir> <sqlite_path>
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

SESSION_RE = re.compile(r"interests-(\d{4})[A-Z0-9]*\.json$")


def run(archives_dir: Path, db_path: Path) -> int:
    files = sorted(archives_dir.glob("interests-*.json"))
    if not files:
        raise RuntimeError(f"no lobbying archives in {archives_dir}")
    conn = sqlite3.connect(db_path)
    known_bills = {r[0] for r in conn.execute("SELECT id FROM bills")}
    total, unknown = 0, 0
    with conn:
        conn.execute("DELETE FROM lobbying_interests")
        for path in files:
            m = SESSION_RE.search(path.name)
            session_year = m.group(1) if m else ""
            lob_session = path.stem.split("-", 1)[1]
            batch = []
            for item in json.loads(path.read_text(encoding="utf-8")):
                bill_id = f"{session_year}-{item['identifier'].replace(' ', '').lower()}"
                if bill_id not in known_bills:
                    unknown += 1
                    continue
                url = (
                    "https://lobbying.wi.gov/What/BillInformation/"
                    f"{lob_session}/Information/{item['info_id']}"
                )
                batch.extend((bill_id, p["id"], p["name"], url) for p in item["principals"])
            conn.executemany(
                "INSERT INTO lobbying_interests (bill_id, principal_id,"
                " principal, source_url) VALUES (?, ?, ?, ?)",
                batch,
            )
            total += len(batch)
    bills = conn.execute(
        "SELECT COUNT(DISTINCT bill_id) FROM lobbying_interests"
    ).fetchone()[0]
    conn.close()
    print(f"lobbying_interests: {total} registrations across {bills} bills"
          + (f" ({unknown} matters skipped: bill not in db)" if unknown else ""))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.archives_dir, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
