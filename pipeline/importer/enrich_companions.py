"""Companion-bill edges from the official record's own "See Also" links.

Wisconsin routinely introduces the same legislation in both chambers at
once. On docs.legis, each proposal page cross-references its twin under
"See Also"; that declaration is the only source of truth used here.
Nothing is matched on titles or inferred from similarity: an edge exists
because the Legislature's page says so, and a "See Also" pointing at a
proposal we do not hold is dropped, not guessed at.

Proposal URLs come from the scrape's own source records (the bills' page
URLs as openstates captured them), so no URL is constructed. Fetches are
throttled and cached under _data/companions_cache/.

Usage: python -m importer.enrich_companions <sqlite> [scrape_dirs...]
           [--limit N] [--delay S]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

from scraper.http import cached_page, session

CACHE_DIR = Path(__file__).resolve().parents[1] / "_data" / "companions_cache"

# a proposal link inside the See Also block. The links use the short form
# ("/2025/proposals/sb997", "/2025/proposals/my6/sb1"): the identifier is
# the last path segment, with an optional special-session fragment before it
SEE_ALSO = re.compile(r"See Also(.{0,2000}?)</ul>", re.I | re.S)
PROPOSAL_LINK = re.compile(
    r'href="[^"]*/proposals/(?:[a-z0-9]+/)?((?:ab|sb|ajr|sjr|ar|sr)\d+)"', re.I
)


def norm_session(raw: str) -> str:
    """Openstates '2026S1' -> our session id '2026s1'."""
    return raw.lower()


def norm_identifier(raw: str) -> str:
    """'SB1' or 'sb1' -> the imported form 'SB 1'."""
    m = re.match(r"([a-z]+)\s*0*(\d+)$", raw.strip(), re.I)
    if not m:
        return raw
    return f"{m.group(1).upper()} {int(m.group(2))}"


def extract_companions(page_html: str) -> list[str]:
    """Identifiers the page's See Also block points at, normalized."""
    block = SEE_ALSO.search(page_html)
    if not block:
        return []
    return sorted({norm_identifier(m) for m in PROPOSAL_LINK.findall(block.group(1))})


def scrape_sources(scrape_dirs: list[Path]) -> dict[tuple[str, str], str]:
    """(session_id, identifier) -> official proposal-page URL."""
    out: dict[tuple[str, str], str] = {}
    for d in scrape_dirs:
        for p in d.glob("bill_*.json"):
            data = json.loads(p.read_text(encoding="utf-8"))
            sources = data.get("sources") or []
            if not sources:
                continue
            key = (norm_session(data["legislative_session"]), norm_identifier(data["identifier"]))
            out[key] = sources[0]["url"]
    return out


def enrich(db_path: Path, scrape_dirs: list[Path], limit: int | None, delay: float) -> int:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS bill_companions (
             bill_id           TEXT NOT NULL REFERENCES bills (id),
             companion_bill_id TEXT NOT NULL REFERENCES bills (id),
             source_url        TEXT NOT NULL,  -- the page that declared the edge
             UNIQUE (bill_id, companion_bill_id)
           )"""
    )
    conn.execute("DELETE FROM bill_companions")

    urls = scrape_sources(scrape_dirs)
    sessions = sorted({s for s, _ in urls})
    by_key = {
        (row[1], row[2]): row[0]
        for row in conn.execute(
            f"SELECT id, session_id, identifier FROM bills"
            f" WHERE session_id IN ({','.join('?' * len(sessions))})",
            sessions,
        )
    }

    todo = [(key, url) for key, url in sorted(urls.items()) if key in by_key]
    if limit:
        todo = todo[:limit]

    http = session()
    fetched = edges = unresolved = failed = 0
    for (session_id, identifier), url in todo:
        try:
            page, cached = cached_page(http, url, CACHE_DIR)
        except requests.RequestException as exc:
            failed += 1
            print(f"FETCH FAILED {session_id} {identifier}: {exc}", file=sys.stderr)
            continue
        if not cached:
            fetched += 1
            time.sleep(delay)
        for comp in extract_companions(page):
            comp_id = by_key.get((session_id, comp))
            if comp_id is None:
                unresolved += 1
                continue
            bill_id = by_key[(session_id, identifier)]
            # record both directions: the declaration is one fact about a
            # pair, and a reader lands on either end of it
            for a, b in ((bill_id, comp_id), (comp_id, bill_id)):
                conn.execute(
                    "INSERT OR IGNORE INTO bill_companions VALUES (?, ?, ?)", (a, b, url)
                )
                edges += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM bill_companions").fetchone()[0]
    print(
        f"companions: {total} edges across {len(todo)} proposals"
        f" ({fetched} fetched, {unresolved} unresolved See-Also targets skipped,"
        f" {failed} fetch failures)"
    )
    conn.close()
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("scrape_dirs", nargs="*", default=None)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--delay", type=float, default=0.3)
    ns = ap.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    dirs = [Path(d) for d in ns.scrape_dirs] or [root / "_data" / "wi"]
    return enrich(Path(ns.db), dirs, ns.limit, ns.delay)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
