"""Non-candidate committee money from CFIS: PACs, conduits, parties, and
independent expenditure committees.

Usage: python -m scraper.fetch_cf_committees [--since YYYY-MM] [--until YYYY-MM]

The date-windowed feed includes all filers. Keep non-candidate committee
transactions and any support/opposition rows. Candidate receipt attribution
remains in fetch_cfis, using its verified committee map.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

from scraper.cfis_api import DELAY, PAGE, month_windows, transaction_count, transaction_pages
from scraper.http import session

DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "cfis"

# Candidate committees belong to fetch_cfis; support/opposition rows are kept below.
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


def _fetch_month(http: requests.Session, first: str, last: str, page_size: int | None = None):
    page_size = PAGE if page_size is None else page_size
    expected = transaction_count(http, first, last)
    rows, registry = [], {}
    scanned, seen_ids = 0, set()
    for results in transaction_pages(http, first, last, timeout=90,
                                     offset_step=page_size, page_size=page_size):
        scanned += len(results)
        for t in results:
            seen_ids.add(t["id"])
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
                # The report page provides the reader's filing-level source link.
                "report_id": ((t.get("reports") or [{}])[0]).get("id"),
                "report_name": ((t.get("reports") or [{}])[0]).get("name"),
            })
    return rows, registry, scanned, expected, seen_ids


def fetch_month(http: requests.Session, first: str, last: str):
    """Return transactions and registry only after full, unique coverage is verified."""
    page_size = PAGE
    for attempt in range(3):
        rows, registry, scanned, expected, seen_ids = _fetch_month(http, first, last, page_size)
        if scanned == expected == len(seen_ids):
            if attempt:
                expected = transaction_count(http, first, last)
            if scanned == expected:
                return rows, registry
        if attempt < 2:
            print(f"{first[:7]}: incomplete listing ({scanned} rows, {len(seen_ids)} unique,"
                  f" expected {expected}), retaking")
            page_size = min(PAGE, 100) if expected <= PAGE else PAGE
            time.sleep(5)
    raise RuntimeError(f"CFIS drift: {first[:7]} paged {scanned} rows"
                       f" ({len(seen_ids)} unique) but count said {expected}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default="2025-01")
    parser.add_argument("--until", help="YYYY-MM; defaults to this month")
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
