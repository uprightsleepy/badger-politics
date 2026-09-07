"""Offline parser for previously saved Eye on Lobbying bill pages.

Automated retrieval was removed on 2026-09-07 because
https://lobbying.wi.gov/robots.txt disallows all crawling. It may be added
back later with the site's approval and a fresh robots.txt/terms review.
Existing archives and the offline importer remain available.
"""

from __future__ import annotations

import re
import sys

from lxml import html as lxml_html


def parse_principals(page_html: str) -> list[dict]:
    """Extract organization links from HTML supplied locally; never fetch URLs."""
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
    print(
        "Lobbying retrieval was removed: robots.txt disallows crawling. "
        "Site approval and a fresh policy review are required to restore it. "
        "Existing archives are unchanged; see scraper/README.md.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
