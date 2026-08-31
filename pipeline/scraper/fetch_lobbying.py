"""Eye on Lobbying (lobbying.wi.gov): per-bill registered principals.

Usage: python -m scraper.fetch_lobbying [--session 2025REG] [--refresh]

Enumerates the legislative-matter grid for bill-type matters, fetches each
bill's page, and archives (bill, principal) pairs. Pages are cached; use
--refresh to refetch (registrations arrive within 15 days of lobbying).
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import requests
from lxml import html as lxml_html

from scraper.http import session as http_session

BASE = "https://lobbying.wi.gov"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "lobbying"
DELAY = 0.4

BILL_TITLE_RE = re.compile(
    r"^\d{4} .*Session (Assembly|Senate) (Bill|Joint Resolution|Resolution) (\d+)$"
)
PREFIX = {
    ("Assembly", "Bill"): "AB", ("Senate", "Bill"): "SB",
    ("Assembly", "Joint Resolution"): "AJR", ("Senate", "Joint Resolution"): "SJR",
    ("Assembly", "Resolution"): "AR", ("Senate", "Resolution"): "SR",
}


def list_bill_matters(http: requests.Session, session: str) -> dict[str, str]:
    """info_id -> bill identifier ('AB 656') from the matter grid."""
    matters: dict[str, str] = {}
    page_number = 1
    while True:
        response = http.post(
            f"{BASE}/What/WhatAreTheyLobbyingAbout/{session}/ShowLegislativeMatterList",
            data={"Session": session, "SearchText": "", "LegislativeMatterTypeId": 0,
                  "SessionFilter": "false", "TopicCategoryId": -1,
                  "pageNumber": page_number, "pageSize": 100,
                  "sortField": "", "isSortAscending": "true"},
            timeout=60,
        )
        response.raise_for_status()
        tree = lxml_html.fromstring(response.text)
        anchors = tree.xpath("//a[contains(@href, '/Information/')]")
        found_rows = 0
        for a in anchors:
            href = a.get("href") or ""
            title = " ".join(a.text_content().split())
            m = re.search(r"/Information/(\d+)", href)
            if not m:
                continue
            found_rows += 1
            bill = BILL_TITLE_RE.match(title)
            if bill and "BillInformation" in href:
                prefix = PREFIX.get((bill.group(1), bill.group(2)))
                if prefix:
                    matters[m.group(1)] = f"{prefix} {bill.group(3)}"
        if found_rows == 0:
            break
        page_number += 1
        time.sleep(DELAY)
    if not matters:
        raise RuntimeError("lobbying drift: no bill matters found in grid")
    return matters


def parse_principals(page_html: str) -> list[dict]:
    tree = lxml_html.fromstring(page_html)
    principals = []
    seen = set()
    for a in tree.xpath("//a[contains(@href, '/Who/PrincipalInformation/')]"):
        m = re.search(r"/Information/(\d+)", a.get("href") or "")
        name = " ".join(a.text_content().split())
        if m and name and m.group(1) not in seen:
            seen.add(m.group(1))
            principals.append({"id": int(m.group(1)), "name": name})
    return principals


def main(argv: list[str]) -> int:
    session = argv[argv.index("--session") + 1] if "--session" in argv else "2025REG"
    refresh = "--refresh" in argv
    pages_dir = DATA_DIR / "pages" / session
    pages_dir.mkdir(parents=True, exist_ok=True)
    http = http_session()

    matters = list_bill_matters(http, session)
    print(f"{session}: {len(matters)} bill matters in the lobbying registry")

    interests = []
    for info_id, identifier in sorted(matters.items()):
        cache = pages_dir / f"{info_id}.html"
        if refresh or not cache.exists():
            response = http.get(
                f"{BASE}/What/BillInformation/{session}/Information/{info_id}",
                timeout=60,
            )
            response.raise_for_status()
            cache.write_text(response.text, encoding="utf-8")
            time.sleep(DELAY)
        principals = parse_principals(cache.read_text(encoding="utf-8"))
        if principals:
            interests.append(
                {"info_id": info_id, "identifier": identifier, "principals": principals}
            )

    out = DATA_DIR / f"interests-{session}.json"
    out.write_text(json.dumps(interests, indent=0), encoding="utf-8")
    pairs = sum(len(i["principals"]) for i in interests)
    print(f"{len(interests)} bills with registrations, {pairs} pairs -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
