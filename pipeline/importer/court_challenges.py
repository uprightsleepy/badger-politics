"""Curated federal court challenges to Wisconsin Acts.

Usage: python -m importer.court_challenges <court-dockets.json> <sqlite_path>

Which case challenges which act comes only from court_challenges.json, a
human-verified curation; CourtListener supplies the docket facts. A
curated docket or bill that does not resolve fails the import.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

CURATION = Path(__file__).with_name("court_challenges.json")
SITE = "https://www.courtlistener.com"
API = SITE + "/api/rest/v4/dockets/{}/"
# Federal courts first; state courts need their own source review.
COURTS = {
    "wiwd": "U.S. District Court, Western District of Wisconsin",
    "wied": "U.S. District Court, Eastern District of Wisconsin",
    "ca7": "U.S. Court of Appeals for the Seventh Circuit",
    "scotus": "U.S. Supreme Court",
}
# One request per docket each night: stay well inside CourtListener's
# default 50 requests/hour and 125/day, leaving room for a rerun.
MAX_DOCKETS = 40


def curated(path: Path = CURATION) -> list[dict]:
    entries = json.loads(path.read_text(encoding="utf-8"))["challenges"]
    if len(entries) > MAX_DOCKETS:
        raise ValueError(f"More than {MAX_DOCKETS} curated dockets exceeds the API budget")
    seen = set()
    for e in entries:
        docket, bills = e.get("docket"), e.get("bills")
        if type(docket) is not int or docket <= 0 or docket in seen:
            raise ValueError(f"Curated docket id must be a unique positive integer: {docket!r}")
        seen.add(docket)
        if (not isinstance(bills, list) or not bills or len(set(bills)) != len(bills)
                or not all(isinstance(b, str) and re.fullmatch(r"[a-z0-9-]+", b)
                           for b in bills)):
            raise ValueError(f"Docket {docket}: 'bills' must list distinct bill ids")
        if not str(e.get("basis", "")).startswith("https://"):
            raise ValueError(f"Docket {docket}: a public https basis is required")
        date.fromisoformat(e.get("verified", ""))
    return entries


def docket_record(raw: dict, docket_id: int) -> dict:
    """The CourtListener docket fields we show; anything unexpected stops."""
    url = raw.get("absolute_url")
    if (raw.get("id") != docket_id or raw.get("court_id") not in COURTS
            or not str(raw.get("case_name") or "").strip()
            or not isinstance(url, str) or not re.fullmatch(r"/docket/\d+/[^?#]*", url)):
        raise ValueError(f"CourtListener docket {docket_id}: unexpected or out-of-scope record")
    dates = {}
    for field in ("date_filed", "date_terminated", "date_last_filing"):
        value = raw.get(field)
        dates[field] = date.fromisoformat(value[:10]).isoformat() if value else None
    return {"id": docket_id, "court_id": raw["court_id"], "case_name": raw["case_name"].strip(),
            "docket_number": raw.get("docket_number") or None, **dates, "url": SITE + url}


def run(dockets_path: Path, db_path: Path, curation: Path = CURATION) -> int:
    dockets = {d["id"]: d for d in json.loads(dockets_path.read_text(encoding="utf-8"))["dockets"]}
    conn = sqlite3.connect(db_path)
    rows = 0
    try:
        with conn:
            conn.execute("DELETE FROM court_challenges")
            for e in curated(curation):
                d = dockets.get(e["docket"])
                if d is None:
                    raise ValueError(f"Curated docket {e['docket']} missing from the archive")
                for bill in e["bills"]:
                    status = conn.execute(
                        "SELECT status FROM bills WHERE id = ?", (bill,)).fetchone()
                    if status != ("enacted",):
                        raise ValueError(f"Docket {e['docket']}: {bill} is not an enacted bill")
                    conn.execute(
                        "INSERT INTO court_challenges (docket_id, bill_id, court, case_name,"
                        " docket_number, date_filed, date_terminated, date_last_filing, url,"
                        " basis_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (d["id"], bill, COURTS[d["court_id"]], d["case_name"],
                         d["docket_number"], d["date_filed"], d["date_terminated"],
                         d["date_last_filing"], d["url"], e["basis"]),
                    )
                    rows += 1
    finally:
        conn.close()
    print(f"court_challenges: {rows} case-act links")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dockets_path", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.dockets_path, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
