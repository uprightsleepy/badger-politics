"""Fetch Wisconsin committee rosters from the openstates/people repo.

Usage: python -m scraper.fetch_committees [dest_dir]

Downloads data/wi/committees/*.yml (one file per committee, with members and
chair roles) into _data/people/wi-committees/ for the importer. Chairs power
the Hearing None view ("Committee X, Chair Y: 47 bills, 0 hearings").
"""

import sys
import time
from pathlib import Path

import requests

API_URL = "https://api.github.com/repos/openstates/people/contents/data/wi/committees"
USER_AGENT = "badgerpolitics.org data pipeline (contact: hphil.work@gmail.com)"
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "_data" / "people" / "wi-committees"


def fetch_committees(dest: Path) -> int:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    listing = session.get(API_URL, timeout=30)
    listing.raise_for_status()
    entries = [e for e in listing.json() if e["name"].endswith(".yml")]
    if not entries:
        raise RuntimeError(f"no YAML files listed at {API_URL}")

    dest.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        response = session.get(entry["download_url"], timeout=30)
        response.raise_for_status()
        (dest / entry["name"]).write_bytes(response.content)
        time.sleep(0.1)
    return len(entries)


def main(argv: list[str]) -> int:
    dest = Path(argv[0]) if argv else DEFAULT_DEST
    count = fetch_committees(dest)
    print(f"fetched {count} committee files -> {dest}")
    if count < 40:  # WI runs ~80 standing/joint committees; far fewer means breakage
        print(f"WARNING: expected ~80 committees, got {count}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
