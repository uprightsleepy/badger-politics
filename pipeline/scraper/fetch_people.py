"""Fetch Wisconsin legislator rosters from the openstates/people repo.

Usage: python -m scraper.fetch_people [--retired]

Downloads data/wi/legislature/*.yml (sitting members) into _data/people/wi/,
and with --retired also data/wi/retired/*.yml plus data/wi/executive/*.yml
(needed for historical vote attribution) into sibling directories.
This is data (CC0), not GPL code.
"""

import sys
from pathlib import Path

from scraper.http import fetch_github_dir

API_BASE = "https://api.github.com/repos/openstates/people/contents/data/wi"
PEOPLE_ROOT = Path(__file__).resolve().parents[1] / "_data" / "people"


def fetch_dir(repo_dir: str, dest: Path) -> int:
    return fetch_github_dir(f"{API_BASE}/{repo_dir}", dest)


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
        # Lt. Governor who served in the Assembly)
        executive = fetch_dir("executive", PEOPLE_ROOT / "wi-executive")
        print(f"fetched {executive} executive files -> {PEOPLE_ROOT / 'wi-executive'}")
        if retired < 150:
            print(f"WARNING: expected 200+ retired members, got {retired}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
