"""Fetch WisconsinEye recording metadata for hearing video links.

Usage: python -m scraper.fetch_wiseye [--backfill]

wiseye.org exposes the standard WordPress REST API; robots.txt allows
all agents with a 10-second crawl delay, which this fetcher honors. We
store metadata only (date, title, url) and link to their site; nothing
is republished. Nightly mode fetches the last 21 days; --backfill walks
the full archive once. A total failure warns and keeps the old archive:
their outages must never break our run.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

from scraper.http import session

API = "https://wiseye.org/wp-json/wp/v2/posts"
DATA_PATH = Path(__file__).resolve().parents[1] / "_data" / "wiseye" / "videos.json"
DELAY = 10  # their robots.txt crawl-delay


def fetch_pages(http: requests.Session, params: dict) -> list[dict]:
    videos, page = [], 1
    while True:
        response = http.get(API, params={**params, "per_page": 100, "page": page}, timeout=60)
        if response.status_code == 400:  # past the last page
            break
        response.raise_for_status()
        posts = response.json()
        if not posts:
            break
        for p in posts:
            videos.append(
                {
                    "date": p["date"][:10],
                    "title": p["title"]["rendered"].strip(),
                    "url": p["link"],
                }
            )
        total_pages = int(response.headers.get("X-WP-TotalPages", page))
        if page >= total_pages:
            break
        page += 1
        time.sleep(DELAY)
    return videos


def main(argv: list[str]) -> int:
    http = session()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if DATA_PATH.exists():
        existing = {v["url"]: v for v in json.loads(DATA_PATH.read_text(encoding="utf-8"))}
    params = {} if "--backfill" in argv else {"after": _cutoff()}
    try:
        fresh = fetch_pages(http, params)
    except Exception as error:  # their outages never break our run
        print(f"WARNING: wiseye fetch failed ({error}); keeping old archive", file=sys.stderr)
        return 0
    for v in fresh:
        existing[v["url"]] = v
    merged = sorted(existing.values(), key=lambda v: v["date"], reverse=True)
    DATA_PATH.write_text(json.dumps(merged, indent=0), encoding="utf-8")
    print(f"wiseye: {len(fresh)} fetched, {len(merged)} archived -> {DATA_PATH.name}")
    return 0


def _cutoff() -> str:
    from datetime import date, timedelta

    return (date.today() - timedelta(days=21)).isoformat() + "T00:00:00"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
