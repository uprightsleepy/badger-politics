"""Wisconsin governors' executive orders, as the docs.legis archive lists them.

Usage: python -m scraper.fetch_executive_orders

The archive index (/code/executive_orders, where the records site's
/document/executiveorders/top menu entry redirects) links one folder per
governor's tenure, labelled "2019- Tony Evers". Each folder page lists that
governor's orders as "2020 Executive Order 72", linking the official PDF at
/document/executiveorders/2020/72.pdf; a few older orders carry a letter
("1969 Executive Order 12A" -> 12a.pdf). The listing states no title or
date, so none is recorded. Raw pages are archived under pages/ and parsed
into orders.json. A former governor's folder is closed and fetched once; the
index and the newest folder (the sitting governor) refresh every run.
Parsing always reruns over the archived pages.

Links only: no order or PDF is ever downloaded. The archive lives inside
the community stage's subjects bundle (both are docs.legis index archives),
so adding it needs no new checkpoint bundle.

Nothing is guessed: an order link whose label disagrees with its address,
an order without a printed label, a folder without orders, or a governor
without a printed name fails the fetch.
"""

from __future__ import annotations

import html as html_lib
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from scraper.http import save_json, session

BASE = "https://docs.legis.wisconsin.gov"
INDEX_URL = f"{BASE}/code/executive_orders"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "subjects" / "executive_orders"
FORMAT = 2

ANCHOR_RE = re.compile(r"<a\s[^>]*?href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S | re.I)
FOLDER_RE = re.compile(r"/code/executive_orders/((\d{4})_[a-z]+(?:_[a-z]+)+)")
ORDER_RE = re.compile(r"/document/executiveorders/(\d{4})/(\d+)([a-z]?)\.pdf")
LABEL_RE = re.compile(r"(\d{4}) Executive Order (\d+)([A-Z]?)")


def _text(fragment: str) -> str:
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def _anchors(page: str, page_url: str):
    """(absolute https URL, path, link text) for every docs.legis link."""
    for m in ANCHOR_RE.finditer(page):
        url = urljoin(page_url, html_lib.unescape(m.group(1).strip()))
        parts = urlsplit(url)
        if parts.hostname != urlsplit(BASE).hostname:
            continue
        yield f"{BASE}{parts.path}", parts.path, _text(m.group(2))


def parse_index(page: str) -> list[dict]:
    """[{folder, start_year, governor}] for each governor's folder, as listed."""
    folders: dict[str, dict] = {}
    for _, path, text in _anchors(page, INDEX_URL):
        m = FOLDER_RE.fullmatch(path)
        if not m or m.group(1) in folders:
            continue
        # "1965-1970 Warren P. Knowles" / "2019- Tony Evers": the name as printed
        name = re.sub(r"\s+", " ", re.sub(r"[\d()\-–—,]", " ", text)).strip()
        if not name:
            raise RuntimeError(f"executive orders index: no governor name for {m.group(1)}")
        folders[m.group(1)] = {"folder": m.group(1), "start_year": int(m.group(2)),
                               "governor": name}
    if not folders:
        raise RuntimeError("executive orders index: no governor folders (markup changed?)")
    return sorted(folders.values(), key=lambda f: f["start_year"])


def parse_folder(page: str, folder: dict) -> list[dict]:
    """Every order the folder page lists, with its official PDF link. Each
    order has a labelled link and an unlabelled PDF icon to the same file."""
    orders: dict[str, dict] = {}
    unlabelled: set[str] = set()
    for url, path, text in _anchors(page, f"{INDEX_URL}/{folder['folder']}"):
        if not (m := ORDER_RE.fullmatch(path)):
            continue
        if not text:
            unlabelled.add(url)
            continue
        year, number, suffix = int(m.group(1)), int(m.group(2)), m.group(3).upper()
        label = LABEL_RE.fullmatch(text)
        if not label or (int(label.group(1)), int(label.group(2)), label.group(3)) \
                != (year, number, suffix):
            raise RuntimeError(f"{folder['folder']}: label {text!r} disagrees with {url}")
        orders.setdefault(url, {"folder": folder["folder"], "governor": folder["governor"],
                                "year": year, "number": number, "suffix": suffix,
                                "url": url})
    if missing := unlabelled - orders.keys():
        raise RuntimeError(f"{folder['folder']}: no printed label for {sorted(missing)[0]}")
    if not orders:
        raise RuntimeError(f"{folder['folder']}: no executive orders listed (markup changed?)")
    return sorted(orders.values(), key=lambda o: (o["year"], o["number"], o["suffix"]))


def main(argv: list[str]) -> int:
    pages = DATA_DIR / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    http = session()

    def fetch(url: str, path: Path) -> None:
        response = http.get(url, timeout=60)
        response.raise_for_status()
        pending = path.with_suffix(".html.tmp")
        pending.write_text(response.text, encoding="utf-8")
        pending.replace(path)

    fetch(INDEX_URL, pages / "index.html")
    folders = parse_index((pages / "index.html").read_text(encoding="utf-8"))
    newest = folders[-1]["folder"]
    orders = []
    for folder in folders:
        page = pages / f"{folder['folder']}.html"
        if folder["folder"] == newest or not page.exists():
            fetch(f"{INDEX_URL}/{folder['folder']}", page)
        orders += parse_folder(page.read_text(encoding="utf-8"), folder)
    save_json(DATA_DIR / "orders.json", {"format": FORMAT, "orders": orders})
    print(f"executive orders: {len(orders)} across {len(folders)} governors -> orders.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
