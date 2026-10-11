"""Refresh CourtListener docket facts for the curated court challenges.

Requires COURTLISTENER_TOKEN once any docket is curated: the v4 API
serves dockets only to authenticated accounts. With no curated dockets
it writes an empty archive without any request.
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from importer.court_challenges import API, curated, docket_record
from scraper.http import save_json, session

DATA_DIR = Path(__file__).resolve().parents[1] / "_data/federal"


def main() -> int:
    entries = curated()
    dockets = []
    if entries:
        token = os.environ.get("COURTLISTENER_TOKEN")
        if not token:
            sys.exit("COURTLISTENER_TOKEN is not set; curated court challenges need it"
                     " (see scraper/README.md)")
        http = session()
        http.headers["Authorization"] = f"Token {token}"
        for e in entries:
            response = http.get(API.format(e["docket"]), timeout=60)
            response.raise_for_status()
            dockets.append(docket_record(response.json(), e["docket"]))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_json(DATA_DIR / "court-dockets.json",
              {"fetched_at": datetime.now(UTC).isoformat(), "dockets": dockets})
    print(f"CourtListener: {len(dockets)} curated dockets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
