"""Non-candidate committee money from CFIS: PACs, conduits, parties, and
independent expenditure committees.

Usage: python -m scraper.fetch_cf_committees [--since YYYY-MM] [--until YYYY-MM]

The transaction feed is windowed by date, not by committee, so the same
pages that carry legislator receipts already carry every other filer's.
This keeps the rows a candidate committee never files: who funds a PAC,
what it spends, and money spent for or against a candidate by someone
else. Candidate-filed rows stay with fetch_cfis so the verified
legislator attribution is untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import requests

from scraper.http import session

BASE = "https://campaignfinance.wi.gov/api/trpc/"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "cfis"
PAGE = 1000
DELAY = 0.4

# the filer types worth keeping: everything that is not one candidate's
# own committee. "State Candidate" and "Federal Candidate" are excluded
# because fetch_cfis already covers the legislator side with a verified map.
KEEP_TYPES = {
    "PAC",
    "Conduit",
    "Independent Expenditure Committee",
    "Political Party",
    "Legislative Campaign Committee",
    "Sponsoring Organization",
    "Referendum",
    "Unregistered Express Advocacy",
    "Unregistered",
}


def call(http: requests.Session, proc: str, payload: dict):
    url = BASE + proc + "?input=" + requests.utils.quote(json.dumps({"json": payload}))
    response = http.get(url, timeout=90)
    response.raise_for_status()
    body = response.json()
    result = body.get("result", {}).get("data", {}).get("json")
    if result is None:
        raise RuntimeError(f"CFIS drift: unexpected shape from {proc}: {str(body)[:200]}")
    return result


def committee_of(entity: dict | None) -> dict | None:
    """Registry row for a committee entity, or None for people/businesses."""
    if not entity:
        return None
    committee = entity.get("committee") or {}
    ctype = (committee.get("committeeType") or {}).get("name")
    if not ctype:
        return None
    return {
        "entity_id": entity.get("id"),
        "name": entity.get("name"),
        "committee_type": ctype,
        "assigned_id": committee.get("assignedCommitteeId"),
    }


def _name(entity: dict | None) -> str | None:
    return (entity or {}).get("name")


def month_windows(since: str, until: str) -> list[tuple[str, str, str]]:
    y, m = (int(p) for p in since.split("-"))
    end_y, end_m = (int(p) for p in until.split("-"))
    out = []
    while (y, m) <= (end_y, end_m):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last = (date(ny, nm, 1) - date.resolution).isoformat()
        out.append((f"{y:04d}-{m:02d}", f"{y:04d}-{m:02d}-01", last))
        y, m = ny, nm
    return out


def fetch_month(http: requests.Session, first: str, last: str):
    """(kept transactions, committee registry rows) for one month."""
    rows, registry, skip = [], {}, 0
    while True:
        page = call(
            http, "publicFrontendApi.getTransactions",
            {"take": PAGE, "skip": skip, "sortBy": "date",
             "sortDirection": "asc", "dateFrom": first, "dateTo": last},
        )
        results = page.get("results", [])
        for t in results:
            filer = t.get("createdByEntity") or {}
            for side in (filer, t.get("from_entity"), t.get("to_entity")):
                row = committee_of(side)
                if row and row["entity_id"]:
                    registry[row["entity_id"]] = row
            ftype = ((filer.get("committee") or {}).get("committeeType") or {}).get("name")
            stance = t.get("supportStance")
            # keep non-candidate filers, plus any stanced row whoever filed it
            if ftype not in KEEP_TYPES and not stance:
                continue
            direction = (t.get("transactionType") or {}).get("direction")
            other = t.get("from_entity") if direction == "INCOMING" else t.get("to_entity")
            rows.append({
                "id": t["id"],
                "filer_entity_id": t.get("createdByEntityId"),
                "filer_type": ftype,
                "direction": direction,
                "date": (t.get("date") or "")[:10],
                "amount": t.get("amount"),
                "other_entity_id": (other or {}).get("id"),
                "other_name": _name(other),
                "other_type": ((other or {}).get("entityType") or {}).get("name"),
                "stance": stance,
                "related_name": _name(t.get("relatedEntity")),
                "related_office": (t.get("relatedOffice") or {}).get("name"),
                "related_district": (t.get("relatedDistrict") or {}).get("name"),
                "final_recipient_id": (t.get("finalRecipient") or {}).get("id"),
                "final_recipient_name": _name(t.get("finalRecipient")),
                "purpose": (t.get("transactionPurpose") or {}).get("name"),
            })
        if len(results) < PAGE:
            break
        skip += PAGE
        time.sleep(DELAY)
    return rows, registry


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default="2025-01")
    parser.add_argument("--until", default=date.today().strftime("%Y-%m"))
    ns = parser.parse_args(argv)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    http = session()
    registry: dict[int, dict] = {}
    total = 0
    for label, first, last in month_windows(ns.since, ns.until):
        out = DATA_DIR / f"pac-{label}.json"
        rows, month_registry = fetch_month(http, first, last)
        registry.update(month_registry)
        out.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        total += len(rows)
        print(f"{label}: {len(rows)} kept, {len(month_registry)} committees seen")
        time.sleep(DELAY)

    reg_path = DATA_DIR / "committees.json"
    if reg_path.exists():
        existing = {c["entity_id"]: c for c in json.loads(reg_path.read_text(encoding="utf-8"))}
        existing.update(registry)
        registry = existing
    reg_path.write_text(
        json.dumps(sorted(registry.values(), key=lambda c: c["entity_id"]), indent=0),
        encoding="utf-8",
    )
    print(f"total {total} transactions; {len(registry)} committees -> {reg_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
