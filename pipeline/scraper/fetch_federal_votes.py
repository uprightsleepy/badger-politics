"""Fetch U.S. Senate roll-call votes and the congressional roster.

The Senate publishes every roll call as XML on senate.gov: a per-session
menu listing vote numbers, and a per-vote file carrying every senator's
position with a stable LIS member id. Both are U.S. government works.
This fetcher mirrors them under _data/federal/ -- the menu is refetched
every run (it grows), per-vote files are immutable once cast and are
cached forever.

The roster (unitedstates/congress-legislators, public domain) maps ids
to people and districts for the whole Wisconsin delegation.

Usage: python -m scraper.fetch_federal_votes [--delay S]
"""

from __future__ import annotations

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from scraper.http import USER_AGENT

DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "federal"

# congress, session, calendar year. Starts at the 112th (2011): Ron
# Johnson's first Congress, so both sitting senators' entire Senate
# careers are covered (Baldwin joined in the 113th). Append the next
# pair when a new session starts. Per-vote files are immutable, so the
# backfill costs one pass and the cache carries it forever.
SESSIONS: list[tuple[int, int, int]] = [
    (c, s, 2009 + (c - 111) * 2 + (s - 1)) for c in range(112, 120) for s in (1, 2)
]

MENU_URL = "https://www.senate.gov/legislative/LIS/roll_call_lists/vote_menu_{c}_{s}.xml"
VOTE_URL = (
    "https://www.senate.gov/legislative/LIS/roll_call_votes/vote{c}{s}/vote_{c}_{s}_{n:05d}.xml"
)
ROSTER_URL = "https://unitedstates.github.io/congress-legislators/legislators-current.json"


def fetch(http: requests.Session, url: str) -> bytes:
    response = http.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.3)
    ns = ap.parse_args(argv)

    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    (DATA_DIR / "legislators-current.json").write_bytes(fetch(http, ROSTER_URL))

    fetched = cached = 0
    for congress, session, _year in SESSIONS:
        senate = DATA_DIR / "senate"
        senate.mkdir(exist_ok=True)
        menu = fetch(http, MENU_URL.format(c=congress, s=session))
        (senate / f"vote_menu_{congress}_{session}.xml").write_bytes(menu)
        numbers = [
            int(el.text)
            for el in ET.fromstring(menu).findall(".//vote/vote_number")
            if el.text
        ]
        for n in sorted(numbers):
            dest = senate / f"vote_{congress}_{session}_{n:05d}.xml"
            if dest.exists():
                cached += 1
                continue
            dest.write_bytes(
                fetch(http, VOTE_URL.format(c=congress, s=session, n=n))
            )
            fetched += 1
            time.sleep(ns.delay)

    print(f"federal votes: {fetched} fetched, {cached} already cached")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
