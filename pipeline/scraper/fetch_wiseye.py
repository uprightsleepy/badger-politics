"""Fetch WisconsinEye recording metadata for hearing video links.

Usage: python -m scraper.fetch_wiseye [--backfill]

Retrieval is paused as of 2026-09-07: the user agreement requires
clarification/approval for metadata reuse. Robots allowance alone does
not establish permission. Retained code may return after site approval
and a fresh policy review; existing archives are unchanged.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

from scraper.http import save_json, session
from scraper.source_access import SourceAccessError

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
    # May be restored with site approval and a fresh robots.txt/terms review.
    print("WisconsinEye retrieval paused pending metadata-reuse approval", file=sys.stderr)
    return 2


def collect(argv: list[str]) -> int:
    http = session()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, dict] = {}
    if DATA_PATH.exists():
        existing = {v["url"]: v for v in json.loads(DATA_PATH.read_text(encoding="utf-8"))}
    params = {} if "--backfill" in argv else {"after": _cutoff()}
    try:
        fresh = fetch_pages(http, params)
    except SourceAccessError:
        raise
    except requests.RequestException as error:  # outages keep the old archive
        print(f"WARNING: wiseye fetch failed ({error}); keeping old archive", file=sys.stderr)
        return 0
    for v in fresh:
        existing[v["url"]] = v
    merged = sorted(existing.values(), key=lambda v: v["date"], reverse=True)
    save_json(DATA_PATH, merged)
    print(f"wiseye: {len(fresh)} fetched, {len(merged)} archived -> {DATA_PATH.name}")
    return 0


def _cutoff() -> str:
    from datetime import date, timedelta

    return (date.today() - timedelta(days=21)).isoformat() + "T00:00:00"


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
