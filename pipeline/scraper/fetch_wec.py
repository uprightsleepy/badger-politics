"""Download the WEC ballot-access report (candidate tracking) for a cycle.

Usage: python -m scraper.fetch_wec [--url URL] [dest_pdf]

The Wisconsin Elections Commission publishes candidate ballot access as a
commission-meeting memo whose Appendix B is the "Candidate Tracking by
Office" table. The URL changes each cycle (and gets superseded when the
general-election ballot is certified) — update DEFAULT_URL per cycle; the
parser's drift alarms catch format changes.
"""

import sys
from pathlib import Path

import requests

DEFAULT_URL = (
    "https://elections.wi.gov/sites/default/files/documents/"
    "D.%20Ballot%20Access%20Report%206.9.2026.pdf"
)
USER_AGENT = "badgerpolitics.org data pipeline (contact: hphil.work@gmail.com)"
DEFAULT_DEST = Path(__file__).resolve().parents[1] / "_data" / "wec" / "ballot-access.pdf"


def fetch(url: str, dest: Path) -> None:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        raise RuntimeError(f"{url} did not return a PDF (WEC page moved?)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(response.content)
    print(f"fetched {len(response.content):,} bytes -> {dest}")


def main(argv: list[str]) -> int:
    args = list(argv)
    url = DEFAULT_URL
    if "--url" in args:
        i = args.index("--url")
        url = args[i + 1]
        del args[i : i + 2]
    dest = Path(args[0]) if args else DEFAULT_DEST
    fetch(url, dest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
