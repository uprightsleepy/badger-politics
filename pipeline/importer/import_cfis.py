"""Load archived CFIS monthly receipt files into contributions.

Usage: python -m importer.import_cfis <archives_dir> <sqlite_path>
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def run(archives_dir: Path, db_path: Path) -> int:
    files = sorted(archives_dir.glob("tx-*.json"))
    if not files:
        raise RuntimeError(f"no CFIS archives in {archives_dir}; run scraper.fetch_cfis")
    conn = sqlite3.connect(db_path)
    known_people = {r[0] for r in conn.execute("SELECT id FROM people")}
    total = 0
    with conn:
        conn.execute("DELETE FROM cfis_committees")
        map_path = archives_dir / "committee_map.json"
        if map_path.exists():
            for m in json.loads(map_path.read_text(encoding="utf-8")):
                if m["person_id"] in known_people:
                    conn.execute(
                        "INSERT INTO cfis_committees (person_id, entity_id, committee)"
                        " VALUES (?, ?, ?)",
                        (m["person_id"], m["entity_id"], m["committee"]),
                    )
        conn.execute("DELETE FROM contributions")
        for path in files:
            rows = json.loads(path.read_text(encoding="utf-8"))
            for r in rows:
                if r["person_id"] not in known_people:
                    raise RuntimeError(
                        f"{path.name}: contribution mapped to unknown person"
                        f" {r['person_id']} — refresh the committee map"
                    )
                conn.execute(
                    "INSERT OR REPLACE INTO contributions (id, person_id,"
                    " committee_entity_id, date, amount, from_entity_id, from_name,"
                    " from_type, occupation, category)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (r["id"], r["person_id"], r["committee_entity_id"], r["date"],
                     r["amount"] or 0, r.get("from_entity_id"), r["from_name"],
                     r["from_type"], r["occupation"], r["category"]),
                )
                total += 1
    count, people = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT person_id) FROM contributions"
    ).fetchone()
    conn.close()
    print(f"contributions: {count} rows for {people} legislators ({len(files)} months)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.archives_dir, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
