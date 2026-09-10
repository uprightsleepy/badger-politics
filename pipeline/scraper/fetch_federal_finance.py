"""Refresh the official FEC two-year summary for Wisconsin's federal delegation."""

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from importer.federal_finance import candidate_ids, fec_url, parse_summary
from scraper.http import session

DATA_DIR = Path(__file__).resolve().parents[1] / "_data/federal"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    cycle = args.as_of.year + args.as_of.year % 2
    identities = candidate_ids(json.loads((DATA_DIR / "legislators-current.json").read_text()))
    url = fec_url(cycle)
    response = session().get(url, timeout=90)
    response.raise_for_status()
    rows = parse_summary(response.content, identities, cycle)
    if not rows:
        raise ValueError("FEC summary contains no Wisconsin delegation records")
    raw = DATA_DIR / f"weball-{cycle}.zip"
    pending_raw = raw.with_suffix(".pending")
    pending_raw.write_bytes(response.content)
    pending_raw.replace(raw)
    output = DATA_DIR / f"finance-{cycle}.json"
    pending = output.with_suffix(".pending")
    pending.write_text(json.dumps({"cycle": cycle, "source_url": url,
        "fetched_at": datetime.now(UTC).isoformat(), "identities": identities,
        "rows": rows}, indent=2), encoding="utf-8")
    pending.replace(output)
    print(f"FEC {cycle}: {len(rows)} of {len(identities)} candidate summaries")


if __name__ == "__main__":
    main()
