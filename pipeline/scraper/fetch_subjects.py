"""Fetch the docs.legis subject index per biennium into archives.

Usage: python -m scraper.fetch_subjects [--since 2009] [--historical 2]

Walks /{year}/related/subject_index/index following the "?down=1"
continuation links (the /scroll/ variant is robots-disallowed; these
entry-path links are not). Archives {printed heading: [identifiers]} per
biennium; historical bienniums are immutable and fetched once, the current
one refreshes nightly. Only REG-session references are kept. At most
--historical older bienniums are (re)fetched per run, so replacing every
archive spreads over several nights instead of one long crawl.

Attribution is structural, never positional: the continuation pages
overlap, so "the last heading seen" names the wrong subject for entries
repeated at the top of a page. Every block carries a data-path, and an
entry belongs to the heading whose path is its parent. An entry without
one fails the fetch.
"""

from __future__ import annotations

import html as html_lib
import json
import re
import sys
from datetime import date
from pathlib import Path

import requests

from scraper.http import session

BASE = "https://docs.legis.wisconsin.gov"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "subjects"
MAX_PAGES = 800  # safety valve far above any real index size
FORMAT = 2  # archives before this keyed subjects by URL slug and misattributed

# heading and entry markup differs by era (qsSubject / qs_subject_), the path does not
BLOCK_RE = re.compile(
    r'<div class="[^"]*"\s+data-path="(/\d{4}/related/subject_index/index/[^"]+)"\s+'
    r"data-cites='([^']*)'>(.*?)</div>", re.S)
HEADING_RE = re.compile(r"/index/[^/]+/[^/]+$")
ENTRY_RE = re.compile(r"/index/[^/]+/[^/]+/_\d+$")
REFERENCE_RE = re.compile(r'<a class="reference"[^>]*>.*?</a>', re.S)
# bill identifiers print lowercase in older bienniums (ab224 vs SB553)
BILL_RE = re.compile(r'href="/document/session/(\d+)/([A-Za-z0-9]+)/([A-Za-z]+)(\d+)"')
DOWN_RE = re.compile(r"<a href='(/\d{4}/related/subject_index/[^']+\?down=1)'>\s*Down")


def blocks(page: str) -> dict[str, tuple[str, str]]:
    """data-path -> (cites, inner html) for every index block on one page."""
    return {m.group(1): (m.group(2), m.group(3)) for m in BLOCK_RE.finditer(page)}


def heading_text(inner: str) -> str:
    """The heading as printed, without its cross-references: "Police, see
    also Milwaukee — Police" is the subject "Police"."""
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", REFERENCE_RE.sub("", inner, count=1)))
    return re.split(r",\s+see\b", re.sub(r"\s+", " ", text).strip())[0].strip()


def build(index: dict[str, tuple[str, str]], year: int) -> dict[str, list[str]]:
    headings = {path: heading_text(inner) for path, (_, inner) in index.items()
                if HEADING_RE.search(path)}
    subjects: dict[str, list[str]] = {}
    for path, (_, inner) in index.items():
        if not ENTRY_RE.search(path):
            continue
        heading = headings.get(path.rsplit("/", 1)[0])
        if not heading:
            raise RuntimeError(f"subject index {year}: entry without a heading: {path}")
        for m in BILL_RE.finditer(inner):
            if int(m.group(1)) != year or m.group(2).upper() != "REG":
                continue
            bills = subjects.setdefault(heading, [])
            identifier = f"{m.group(3).upper()} {m.group(4)}"
            if identifier not in bills:
                bills.append(identifier)
    return subjects


def fetch_year(http: requests.Session, year: int) -> dict[str, list[str]]:
    index: dict[str, tuple[str, str]] = {}
    url: str | None = f"{BASE}/{year}/related/subject_index/index"
    seen = set()
    for _ in range(MAX_PAGES):
        if url is None or url in seen:
            break
        seen.add(url)
        response = http.get(url, timeout=60)
        response.raise_for_status()
        index.update(blocks(response.text))  # overlapping pages repeat blocks
        m = DOWN_RE.search(response.text)
        url = BASE + m.group(1) if m else None
    else:
        raise RuntimeError(f"subject index {year}: exceeded {MAX_PAGES} pages")
    subjects = build(index, year)
    if not subjects:
        raise RuntimeError(f"subject index {year}: no subjects parsed (markup changed?)")
    return subjects


def current_format(path: Path) -> bool:
    return path.exists() and json.loads(path.read_text(encoding="utf-8")).get("format") == FORMAT


def main(argv: list[str]) -> int:
    since = int(argv[argv.index("--since") + 1]) if "--since" in argv else 2009
    historical = int(argv[argv.index("--historical") + 1]) if "--historical" in argv else 2
    today = date.today()
    current_biennium = today.year if today.year % 2 else today.year - 1
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    http = session()
    for year in range(since, current_biennium + 1, 2):
        out = DATA_DIR / f"subjects-{year}.json"
        # historical bienniums are immutable; the current one refreshes
        if year != current_biennium and current_format(out):
            continue
        if year != current_biennium:
            if historical == 0:
                print(f"{year}: archive not yet replaced; later run", file=sys.stderr)
                continue
            historical -= 1
        subjects = fetch_year(http, year)
        out.write_text(json.dumps({"format": FORMAT, "subjects": subjects}, indent=0,
                                  sort_keys=True, ensure_ascii=False), encoding="utf-8")
        refs = sum(len(v) for v in subjects.values())
        print(f"{year}: {len(subjects)} subjects, {refs} bill references -> {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
