"""Fetch bill-text pages and extract the LRB plain-language analysis.

Usage: python -m importer.enrich_lrb <sqlite_path> [--limit N] [--only BILL_ID]
                                     [--delay SECONDS]

Every Wisconsin bill text opens with an "Analysis by the Legislative
Reference Bureau" section written in plain language — the site leads with it
instead of legalese. The scraper doesn't capture it, so this step fetches
each bill's official text page (bills.text_url) and extracts the section.

Politeness: identifying User-Agent, throttled (default 0.5s between fetches),
and raw HTML is cached under pipeline/_data/lrb_cache/ so re-runs are free.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests
from lxml import html as lxml_html

USER_AGENT = "badgerpolitics.org data pipeline (contact: hphil.work@gmail.com)"
CACHE_DIR = Path(__file__).resolve().parents[1] / "_data" / "lrb_cache"

ANALYSIS_START = re.compile(r"analysis by the legislative reference bureau", re.I)
# The bill body begins with the enacting clause; earlier stop: fiscal estimate.
ANALYSIS_END = re.compile(
    r"(the people of the state of wisconsin.*represented in senate and assembly"
    r"|for further information see the state|fiscal estimate)",
    re.I,
)


def extract_analysis(page_html: str) -> str | None:
    """Text between the LRB analysis heading and the enacting clause."""
    tree = lxml_html.fromstring(page_html)
    blocks = [
        text.strip()
        for text in tree.xpath("//body//text()")
        if text.strip()
    ]
    start = end = None
    for i, block in enumerate(blocks):
        if start is None and ANALYSIS_START.search(block):
            start = i + 1
        elif start is not None and ANALYSIS_END.search(block):
            end = i
            break
    if start is None:
        return None
    section = blocks[start:end]
    text = re.sub(r"[ \t]+", " ", "\n".join(section)).strip()
    return text or None


def fetch_page(session: requests.Session, bill_id: str, url: str) -> str:
    cache_file = CACHE_DIR / f"{bill_id}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8", errors="replace")
    response = session.get(url, timeout=60)
    response.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(response.text, encoding="utf-8")
    return response.text


def enrich(db_path: Path, limit: int | None, only: str | None, delay: float) -> int:
    conn = sqlite3.connect(db_path)
    query = (
        "SELECT id, text_url FROM bills"
        " WHERE lrb_analysis IS NULL AND text_url IS NOT NULL AND source = 'openstates'"
    )
    params: tuple = ()
    if only:
        query += " AND id = ?"
        params = (only,)
    rows = conn.execute(query, params).fetchall()
    if limit:
        rows = rows[:limit]

    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    done = missing = failed = 0
    for bill_id, url in rows:
        cached = (CACHE_DIR / f"{bill_id}.html").exists()
        try:
            page = fetch_page(http, bill_id, url)
        except requests.RequestException as exc:
            failed += 1
            print(f"FETCH FAILED {bill_id}: {exc}", file=sys.stderr)
            continue
        analysis = extract_analysis(page)
        if analysis:
            with conn:
                conn.execute(
                    "UPDATE bills SET lrb_analysis = ? WHERE id = ?", (analysis, bill_id)
                )
            done += 1
        else:
            missing += 1
            print(f"NO ANALYSIS SECTION {bill_id}: {url}", file=sys.stderr)
        if not cached and delay:
            time.sleep(delay)
    conn.close()
    print(f"lrb: {done} extracted, {missing} without analysis section, {failed} fetch failures")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only")
    parser.add_argument("--delay", type=float, default=0.5)
    ns = parser.parse_args(argv)
    return enrich(ns.db_path, ns.limit, ns.only, ns.delay)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
