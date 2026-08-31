"""Fetch authoritative per-session membership lists from docs.legis.

Usage: python -m scraper.fetch_session_rosters [year ...]

docs.legis.wisconsin.gov/{year}/legislators/{assembly,senate} lists every
member of that biennium — the ground truth for who served, independent of
openstates people-file date quality. Listings exist back to 2013 (2009/2011
return 404). Output: _data/rosters/{year}.json with name/chamber/district.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests
from lxml import html as lxml_html

from scraper.http import session

DEST = Path(__file__).resolve().parents[1] / "_data" / "rosters"
CHAMBERS = {"assembly": "lower", "senate": "upper"}
DEFAULT_YEARS = [2013, 2015, 2017, 2019, 2021, 2023, 2025]

ROW_RE = re.compile(r"District (\d+)")


def parse_listing(page_html: str, chamber: str) -> list[dict]:
    """Members render as <div id="districtN"> blocks holding
    <strong><a>Last, First</a></strong> ... <small>District N</small>."""
    tree = lxml_html.fromstring(page_html)
    members = []
    for block in tree.xpath("//div[starts-with(@id, 'district')]"):
        names = block.xpath(".//strong/a/text()")
        district = ROW_RE.search(" ".join(block.text_content().split()))
        if not names or not district:
            continue
        raw = names[0].strip()
        if ", " in raw:  # 'August, Tyler' -> 'Tyler August'
            last, first = raw.split(", ", 1)
            raw = f"{first} {last}"
        members.append(
            {"name": raw, "chamber": chamber, "district": int(district.group(1))}
        )
    return members


def fetch_year(session: requests.Session, year: int) -> list[dict]:
    members: list[dict] = []
    for path, chamber in CHAMBERS.items():
        url = f"https://docs.legis.wisconsin.gov/{year}/legislators/{path}"
        response = session.get(url, timeout=60)
        if response.status_code == 404:
            return []  # listings don't exist this far back
        response.raise_for_status()
        parsed = parse_listing(response.text, chamber)
        if not parsed:
            raise RuntimeError(f"docs.legis drift: no members parsed from {url}")
        members.extend(parsed)
        time.sleep(0.5)
    return members


def main(argv: list[str]) -> int:
    years = [int(a) for a in argv] if argv else DEFAULT_YEARS
    http = session()
    DEST.mkdir(parents=True, exist_ok=True)
    for year in years:
        members = fetch_year(http, year)
        if not members:
            print(f"{year}: no listing (404) — skipped")
            continue
        lower = sum(1 for m in members if m["chamber"] == "lower")
        upper = len(members) - lower
        if lower < 95 or upper < 30:
            raise RuntimeError(
                f"{year}: implausible membership parsed ({lower} assembly,"
                f" {upper} senate) — page format changed?"
            )
        (DEST / f"{year}.json").write_text(
            json.dumps(members, indent=1), encoding="utf-8"
        )
        print(f"{year}: {lower} assembly + {upper} senate -> {DEST / f'{year}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
