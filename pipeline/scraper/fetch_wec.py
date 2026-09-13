"""Download the Commission's pinned candidate records for an election cycle.

Usage: python -m scraper.fetch_wec [--cycle 2026]

Two files per cycle, both immutable once posted, so a present file is never
fetched again:
- the ballot-access report whose "Candidate Tracking by Office" appendix
  lists every filing and its status (independents come only from here);
- the certified partisan primary ward-by-ward workbook, which names each
  party's nominee for November.

Reviewed 2026-09-13 (scraper/README.md): robots.txt permits the documents
path and the site publishes no separate terms. Add each cycle's URLs after
its ballot-access meeting and its primary certification.
"""

import argparse
import sys
from pathlib import Path

from scraper.http import session

DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "wec"
BASE = "https://elections.wi.gov/sites/default/files/documents/"
CYCLES = {
    2026: {
        "ballot-access.pdf": BASE + "D.%20Ballot%20Access%20Report%206.9.2026.pdf",
        "primary-2026.xlsx": (BASE + "Ward%20by%20Ward%20Report_Partisan%20Primary%202026"
                              "_All%20State%20Contests.xlsx"),
    },
}
MAGIC = {".pdf": b"%PDF", ".xlsx": b"PK"}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cycle", type=int, default=2026)
    ns = ap.parse_args(argv)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    http = session()
    for name, url in CYCLES[ns.cycle].items():
        target = DATA_DIR / name
        if target.exists():
            print(f"{name}: already present")
            continue
        response = http.get(url, timeout=120)
        response.raise_for_status()
        if not response.content.startswith(MAGIC[target.suffix]):
            raise RuntimeError(f"{url} did not return a {target.suffix} file (page moved?)")
        target.write_bytes(response.content)
        print(f"{name}: {len(response.content):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
