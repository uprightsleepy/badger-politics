"""Load the CFIS committee registry and non-candidate committee money.

Usage: python -m importer.import_cf_committees <cfis_dir> <sqlite_path>

Reads scraper.fetch_cf_committees archives (committees.json, pac-YYYY-MM.json).
Candidate-committee receipts are NOT touched here; they stay in
`contributions` with their verified person mapping.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

FIELDS = (
    "id", "filer_entity_id", "filer_type", "direction", "date", "amount",
    "other_entity_id", "other_name", "other_type", "stance", "related_name",
    "related_office", "related_district", "final_recipient_id",
    "final_recipient_name", "purpose", "report_id", "report_name",
)


def run(cfis_dir: Path, db_path: Path) -> int:
    registry_path = cfis_dir / "committees.json"
    if not registry_path.exists():
        raise RuntimeError(f"no committee registry at {registry_path}")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))

    months = sorted(cfis_dir.glob("pac-*.json"))
    if not months:
        raise RuntimeError(f"no pac-*.json archives in {cfis_dir}")

    conn = sqlite3.connect(db_path)
    # databases built before report links existed lack the two columns;
    # add them in place rather than demanding a from-scratch rebuild
    have = {row[1] for row in conn.execute("PRAGMA table_info(cf_transactions)")}
    for col, kind in (("report_id", "INTEGER"), ("report_name", "TEXT")):
        if col not in have:
            conn.execute(f"ALTER TABLE cf_transactions ADD COLUMN {col} {kind}")
    kept = 0
    with conn:
        conn.execute("DELETE FROM cf_committees")
        conn.executemany(
            "INSERT INTO cf_committees (entity_id, name, committee_type, assigned_id)"
            " VALUES (?, ?, ?, ?)",
            [(c["entity_id"], c["name"], c["committee_type"], c["assigned_id"])
             for c in registry if c.get("entity_id") and c.get("name")],
        )
        conn.execute("DELETE FROM cf_transactions")
        for path in months:
            rows = json.loads(path.read_text(encoding="utf-8"))
            batch = []
            for r in rows:
                # a filer and an amount are the minimum for an attributable row
                if not r.get("filer_entity_id") or r.get("amount") is None:
                    continue
                if r.get("direction") not in ("INCOMING", "OUTGOING"):
                    continue
                batch.append(tuple(r.get(f) for f in FIELDS))
            conn.executemany(
                f"INSERT OR REPLACE INTO cf_transactions ({', '.join(FIELDS)})"
                f" VALUES ({', '.join('?' * len(FIELDS))})",
                batch,
            )
            kept += len(batch)

    committees = conn.execute("SELECT COUNT(*) FROM cf_committees").fetchone()[0]
    stanced = conn.execute(
        "SELECT COUNT(*) FROM cf_transactions WHERE stance IS NOT NULL"
    ).fetchone()[0]
    conn.close()
    print(f"cf: {committees} committees, {kept} transactions ({stanced} express advocacy)")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cfis_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.cfis_dir, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
