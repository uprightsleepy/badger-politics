"""Download WEC ward-by-ward canvass spreadsheets for general elections.

Usage: python -m scraper.fetch_wec_results

URLs are pinned per election (WEC posts one set of files per certified
election; they do not change after certification). Add each new general
election's files after certification, roughly every November of even years.
"""

import sys
from pathlib import Path

import requests

from scraper.http import USER_AGENT

DEST = Path(__file__).resolve().parents[1] / "_data" / "wec-results"

FILES = {
    "ger2024.xlsx": (
        "https://elections.wi.gov/sites/default/files/documents/"
        "Ward%20by%20Ward%20Report_November%205%202024%20General%20Election_"
        "Federal%20and%20State%20Contests.xlsx"
    ),
    "ger2022-assembly.xlsx": (
        "https://elections.wi.gov/sites/default/files/documents/"
        "Ward%20by%20Ward%20Report%20by%20Congressional%20District%20-%20"
        "Representative%20to%20the%20Assembly.xlsx"
    ),
    "ger2022-senate.xlsx": (
        "https://elections.wi.gov/sites/default/files/documents/"
        "Ward%20by%20Ward%20Report_State%20Senator_0.xlsx"
    ),
}


def main(argv: list[str]) -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        target = DEST / name
        if target.exists():
            print(f"{name}: already present")
            continue
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
        response.raise_for_status()
        if not response.content.startswith(b"PK"):  # xlsx = zip container
            raise RuntimeError(f"{url} did not return an xlsx")
        target.write_bytes(response.content)
        print(f"{name}: {len(response.content):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
