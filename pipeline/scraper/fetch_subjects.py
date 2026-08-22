"""Fetch the docs.legis subject index per biennium into archives.

Usage: python -m scraper.fetch_subjects [--since 2009]

Walks /{year}/related/subject_index/index following the "?down=1"
continuation links (the /scroll/ variant is robots-disallowed; these
entry-path links are not). Archives subject -> [identifiers] per
biennium; historical bienniums are immutable and fetched once, the
current one refreshes nightly. Only REG-session references are kept;
special-session references are counted and skipped.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

BASE = "https://docs.legis.wisconsin.gov"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "subjects"
USER_AGENT = "BadgerPolitics/1.0 (badgerpolitics.org; hphil.work@gmail.com)"
DELAY = 0.5
MAX_PAGES = 800  # safety valve far above any real index size

SUBJECT_RE = re.compile(
    r'<div class="qsSubject[^"]*"[^>]*data-cites=\'\["subjectindex/\d+/([^"]+)"\]\'', re.S
)
# bill identifiers print lowercase in older bienniums (ab224 vs SB553)
BILL_RE = re.compile(r'href="/document/session/(\d+)/([A-Za-z0-9]+)/([A-Za-z]+)(\d+)"')
DOWN_RE = re.compile(r"<a href='(/\d{4}/related/subject_index/[^']+\?down=1)'>\s*Down")


def parse_page(
    html: str, year: int, subjects: dict, current: str | None, skipped: list
) -> str | None:
    """Attribute each REG bill reference to the most recent preceding
    subject heading, in document order. Headings carry across page breaks:
    takes the heading open at the top of this page, returns the one open
    at the bottom."""
    events = []
    for m in SUBJECT_RE.finditer(html):
        name = m.group(1)
        if len(name) > 1:  # single letters are section headings
            events.append((m.start(), "subject", name))
    for m in BILL_RE.finditer(html):
        if int(m.group(1)) != year:
            continue
        if m.group(2).upper() != "REG":
            skipped.append(f"{m.group(2)}/{m.group(3)}{m.group(4)}")
            continue
        events.append((m.start(), "bill", f"{m.group(3).upper()} {m.group(4)}"))
    events.sort()
    for _, kind, value in events:
        if kind == "subject":
            current = value
        elif current:
            subjects.setdefault(current, [])
            if value not in subjects[current]:
                subjects[current].append(value)
    return current


def fetch_year(http: requests.Session, year: int) -> dict:
    subjects: dict[str, list[str]] = {}
    current: str | None = None
    skipped: list[str] = []
    url = f"{BASE}/{year}/related/subject_index/index"
    seen = set()
    for _ in range(MAX_PAGES):
        if url in seen:
            break
        seen.add(url)
        response = http.get(url, timeout=60)
        response.raise_for_status()
        current = parse_page(response.text, year, subjects, current, skipped)
        m = DOWN_RE.search(response.text)
        if not m:
            break
        url = BASE + m.group(1)
        time.sleep(DELAY)
    else:
        raise RuntimeError(f"subject index {year}: exceeded {MAX_PAGES} pages")
    if skipped:
        print(f"{year}: skipped {len(skipped)} non-REG references", file=sys.stderr)
    return subjects


def main(argv: list[str]) -> int:
    since = int(argv[argv.index("--since") + 1]) if "--since" in argv else 2009
    today = date.today()
    current_biennium = today.year if today.year % 2 else today.year - 1
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    for year in range(since, current_biennium + 1, 2):
        out = DATA_DIR / f"subjects-{year}.json"
        # historical bienniums are immutable; the current one refreshes
        if out.exists() and year != current_biennium:
            continue
        subjects = fetch_year(http, year)
        out.write_text(json.dumps(subjects, indent=0, sort_keys=True), encoding="utf-8")
        refs = sum(len(v) for v in subjects.values())
        print(f"{year}: {len(subjects)} subjects, {refs} bill references -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
