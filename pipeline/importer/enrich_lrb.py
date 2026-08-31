"""Fetch bill-text pages and extract the LRB plain-language analysis.
Throttled, identifying User-Agent, cached under _data/lrb_cache/.

Usage: python -m importer.enrich_lrb <sqlite_path> [--limit N] [--only ID] [--delay S]
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

from scraper.http import cached_page, session

CACHE_DIR = Path(__file__).resolve().parents[1] / "_data" / "lrb_cache"

ANALYSIS_START = re.compile(r"analysis by the legislative reference bureau", re.I)
# The analysis ends at the enacting clause, or earlier at the boilerplate
# pointer to the fiscal estimate ("For further information see the state /
# local / state and local fiscal estimate..."). Whitespace is flexible
# because these phrases wrap across the document's source lines.
ANALYSIS_END = re.compile(
    r"the\s+people\s+of\s+the\s+state\s+of\s+wisconsin[\s\S]{0,40}?"
    r"represented\s+in\s+senate\s+and\s+assembly"
    r"|for\s+further\s+information\s+see\s+the"
    r"|fiscal\s+estimate"
    # resolutions have no enacting clause; their text opens with the
    # preamble or resolving clause. (The documents' own anchors, e.g.
    # "SJR2,2,4", are unusable: they also punctuate bill analyses.)
    r"|^(?:whereas,|resolved\s+by\s+the|now,\s+therefore)",
    re.I | re.M,
)


TRAILING_ANCHORS = re.compile(
    r"(?:\n[ \t]*(?:[A-Z]{2,3}\d+(?:,\d+)+|\d+))+[ \t]*$"
)


def extract_analysis(page_html: str) -> str | None:
    """Text between the LRB analysis heading and the enacting clause."""
    tree = lxml_html.fromstring(page_html)
    blocks = [
        text.strip()
        for text in tree.xpath("//body//text()")
        if text.strip()
    ]
    start = None
    for i, block in enumerate(blocks):
        if ANALYSIS_START.search(block):
            start = i + 1
            break
    if start is None:
        return None
    # search the joined text, not block by block: a terminator split across
    # source lines matches no single block, so its leading words would be
    # kept as a dangling fragment ("For further information see the / state")
    text = "\n".join(blocks[start:])
    cut = ANALYSIS_END.search(text)
    if cut:
        text = text[: cut.start()]
    text = re.sub(r"[ \t]+", " ", text).strip()
    # drop the document anchors and line numbers ("SJR2,2,4", "3") that
    # sit between the analysis and the text following it
    text = TRAILING_ANCHORS.sub("", text).strip()
    return text or None


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

    http = session()
    done = missing = failed = 0
    # batched commits: one fsync per ~500 rows, not per row; a crash redoes
    # at most one batch, and the HTML cache makes that redo free
    pending: list[tuple[str, str]] = []

    def flush() -> None:
        if pending:
            with conn:
                conn.executemany(
                    "UPDATE bills SET lrb_analysis = ? WHERE id = ?", pending
                )
            pending.clear()

    for bill_id, url in rows:
        try:
            page, cached = cached_page(http, url, CACHE_DIR)
        except requests.RequestException as exc:
            failed += 1
            print(f"FETCH FAILED {bill_id}: {exc}", file=sys.stderr)
            continue
        analysis = extract_analysis(page)
        if analysis:
            pending.append((analysis, bill_id))
            if len(pending) >= 500:
                flush()
            done += 1
        else:
            missing += 1
            print(f"NO ANALYSIS SECTION {bill_id}: {url}", file=sys.stderr)
        if not cached and delay:
            time.sleep(delay)
    flush()
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
