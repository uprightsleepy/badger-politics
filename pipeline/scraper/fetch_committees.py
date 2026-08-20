"""Fetch Wisconsin committee rosters from the openstates/people repo.

Usage: python -m scraper.fetch_committees [dest_dir]

Downloads data/wi/committees/*.yml (one file per committee, with members and
chair roles). Chairs power the Hearing None view.
"""

import sys
from pathlib import Path

from scraper.http import fetch_github_dir

API_URL = "https://api.github.com/repos/openstates/people/contents/data/wi/committees"
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "_data" / "people" / "wi-committees"


def main(argv: list[str]) -> int:
    dest = Path(argv[0]) if argv else DEFAULT_DEST
    count = fetch_github_dir(API_URL, dest)
    print(f"fetched {count} committee files -> {dest}")
    if count < 40:  # WI runs ~80 standing/joint committees; far fewer means breakage
        print(f"WARNING: expected ~80 committees, got {count}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
