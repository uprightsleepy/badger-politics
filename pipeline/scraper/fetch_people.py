"""Fetch Wisconsin legislator rosters from the openstates/people repo.

Usage: python -m scraper.fetch_people [--retired]

Downloads data/wi/legislature/*.yml (sitting members) into _data/people/wi/,
and with --retired also data/wi/retired/*.yml (everyone who served since
~2009, needed for historical vote attribution) into _data/people/wi-retired/.
This is data (CC0), not GPL code.
"""

import sys
import time
from pathlib import Path

import requests

API_BASE = "https://api.github.com/repos/openstates/people/contents/data/wi"
USER_AGENT = "badgerpolitics.org data pipeline (contact: hphil.work@gmail.com)"
PEOPLE_ROOT = Path(__file__).resolve().parents[1] / "_data" / "people"


def fetch_dir(repo_dir: str, dest: Path) -> int:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    listing = session.get(f"{API_BASE}/{repo_dir}?per_page=1000", timeout=30)
    listing.raise_for_status()
    entries = [e for e in listing.json() if e["name"].endswith(".yml")]
    if not entries:
        raise RuntimeError(f"no YAML files listed for {repo_dir}")

    dest.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        response = session.get(entry["download_url"], timeout=30)
        response.raise_for_status()
        (dest / entry["name"]).write_bytes(response.content)
        time.sleep(0.1)
    return len(entries)


def main(argv: list[str]) -> int:
    count = fetch_dir("legislature", PEOPLE_ROOT / "wi")
    print(f"fetched {count} sitting legislator files -> {PEOPLE_ROOT / 'wi'}")
    if count < 120:  # 99 Assembly + 33 Senate minus vacancies; far fewer means breakage
        print(f"WARNING: expected ~132 sitting legislators, got {count}", file=sys.stderr)
        return 1
    if "--retired" in argv:
        retired = fetch_dir("retired", PEOPLE_ROOT / "wi-retired")
        print(f"fetched {retired} retired legislator files -> {PEOPLE_ROOT / 'wi-retired'}")
        # current executives may carry past legislative roles (e.g. a sitting
        # Lt. Governor who served in the Assembly) — they live in neither
        # legislature/ nor retired/
        executive = fetch_dir("executive", PEOPLE_ROOT / "wi-executive")
        print(f"fetched {executive} executive files -> {PEOPLE_ROOT / 'wi-executive'}")
        if retired < 150:
            print(f"WARNING: expected 200+ retired members, got {retired}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
