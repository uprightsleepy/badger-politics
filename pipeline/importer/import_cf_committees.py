"""Load CFIS committee money and separately attributed state campaigns.

Usage: python -m importer.import_cf_committees <cfis_dir> <sqlite_path>

Reads scraper.fetch_cf_committees archives (committees.json, pac-YYYY-MM.json).
Legislator receipts stay in `contributions`; curated state campaigns use
separate tables so existing PAC totals and donor rankings remain unchanged.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
from pathlib import Path

from importer.federal_finance import STATE_CAMPAIGNS

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
    kept = 0
    with conn:
        conn.execute("DELETE FROM state_campaign_transactions")
        conn.execute("DELETE FROM state_campaign_coverage")
        conn.execute("DELETE FROM state_campaigns")
        by_id = {row["entity_id"]: row for row in registry}
        for entity_id, campaign in STATE_CAMPAIGNS.items():
            conn.execute("INSERT INTO state_campaigns VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (entity_id, campaign["bioguide"], campaign["candidate"],
                          campaign["office"], campaign["cycle"], campaign["committee"],
                          campaign["source_url"]))
            entry = by_id.get(entity_id, {})
            if entry and (entry["name"] != campaign["committee"]
                          or entry["assigned_id"] != campaign["assigned_id"]):
                raise ValueError("State campaign registry identity mismatch")
            for month in entry.get("campaign_months", []):
                if (not isinstance(month, str)
                        or not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", month)
                        or not (cfis_dir / f"pac-{month}.json").exists()):
                    raise ValueError("State campaign coverage archive is missing")
                conn.execute("INSERT INTO state_campaign_coverage VALUES (?, ?)",
                             (entity_id, month))
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
                if r.get("filer_entity_id") in STATE_CAMPAIGNS:
                    if (r.get("amount") is None or r.get("direction") not in
                            ("INCOMING", "OUTGOING") or r.get("filer_type") != "State Candidate"):
                        raise ValueError("Invalid curated state campaign transaction")
                    if not math.isfinite(float(r["amount"])):
                        raise ValueError("Invalid state campaign dollar amount")
                    conn.execute(
                        f"INSERT INTO state_campaign_transactions ({', '.join(FIELDS)})"
                        f" VALUES ({', '.join('?' * len(FIELDS))})",
                        tuple(r.get(f) for f in FIELDS),
                    )
                    # Preserve pre-existing express-advocacy rows in the original table.
                    if not r.get("stance"):
                        continue
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
