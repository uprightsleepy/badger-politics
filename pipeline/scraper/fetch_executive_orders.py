"""Wisconsin governors' executive orders, as the docs.legis archive lists them.

Usage: python -m scraper.fetch_executive_orders

The archive index (/code/executive_orders) links one folder per governor's
tenure; each folder page lists that governor's orders and links each one's
official document. Raw pages are archived under pages/ and parsed into
orders.json. A former governor's folder is closed and fetched once; the
index and the newest folder (the sitting governor) refresh every run.
Parsing always reruns over the archived pages.

Links only: no order or PDF is ever downloaded. The archive lives inside
the community stage's subjects bundle (both are docs.legis index archives),
so adding it needs no new checkpoint bundle.

Nothing is guessed: an order whose number or year the official listing
doesn't state, a folder without orders, or a governor without a printed
name fails the fetch.
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
FORMAT = 1

ANCHOR_RE = re.compile(r"<a\s[^>]*?href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.S | re.I)
FOLDER_RE = re.compile(r"/code/executive_orders/((\d{4})_[a-z0-9_]+)/?")
# one listing entry ends at its line/row/item; the next order starts a new one
ENTRY_END_RE = re.compile(r"</(?:li|tr|p|div|dd)>|<br\s*/?>", re.I)
FILE_NUMBER_RE = re.compile(r"(?:^|[_-])(\d{4})[_-]0*(\d+)$")
TEXT_NUMBER_RE = re.compile(r"Executive\s+Order\s*(?:No\.?|Number|#)?\s*0*(\d+)\b", re.I)
LEAD_RE = re.compile(r"^\s*Executive\s+Order\s*(?:No\.?|Number|#)?\s*\d+\s*[-–—:,.]?\s*", re.I)
# a format link's label and a closing "(March 12, 2020)" are not title
LABEL_RE = re.compile(r"(?:\s+(?:PDF|HTML))+\s*$")
PAREN_TAIL_RE = re.compile(r"\s*\(([^()]*)\)\s*$")
MONTHS = ("January February March April May June July August September October"
          " November December").split()
LONG_DATE_RE = re.compile(rf"\b({'|'.join(MONTHS)})\s+(\d{{1,2}}),\s+(\d{{4}})\b")
SHORT_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def _text(fragment: str) -> str:
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment))
    return re.sub(r"\s+", " ", text).strip()


def _anchors(page: str, page_url: str):
    """(absolute https URL, path, link text, start, end) for every link."""
    for m in ANCHOR_RE.finditer(page):
        url = urljoin(page_url, html_lib.unescape(m.group(1).strip()))
        parts = urlsplit(url)
        if parts.hostname != urlsplit(BASE).hostname:
            continue
        url = f"{BASE}{parts.path}"
        yield url, parts.path, _text(m.group(2)), m.start(), m.end()


def parse_index(page: str) -> list[dict]:
    """[{folder, start_year, governor}] for each governor's folder, as listed."""
    folders: dict[str, dict] = {}
    for _, path, text, _, _ in _anchors(page, INDEX_URL):
        m = FOLDER_RE.fullmatch(path)
        if not m or m.group(1) in folders:
            continue
        # "2019 - Tony Evers" / "Tony Evers (2019-)": the name as printed
        name = re.sub(r"\s+", " ", re.sub(r"[\d()\-–—,]|\bGovernor\b", " ", text)).strip()
        if not name:
            raise RuntimeError(f"executive orders index: no governor name for {m.group(1)}")
        folders[m.group(1)] = {"folder": m.group(1), "start_year": int(m.group(2)),
                               "governor": name}
    if not folders:
        raise RuntimeError("executive orders index: no governor folders (markup changed?)")
    return sorted(folders.values(), key=lambda f: f["start_year"])


def _date(text: str) -> str | None:
    if m := LONG_DATE_RE.search(text):
        return f"{m.group(3)}-{MONTHS.index(m.group(1)) + 1:02d}-{int(m.group(2)):02d}"
    if m := SHORT_DATE_RE.search(text):
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def parse_folder(page: str, folder: dict) -> list[dict]:
    """Every order the folder page lists, with its official link."""
    page_url = f"{INDEX_URL}/{folder['folder']}"
    order_re = re.compile(rf"/code/executive_orders/{re.escape(folder['folder'])}/([^/]+)")
    orders: dict[tuple[int, int], dict] = {}
    for url, path, _, start, end in _anchors(page, page_url):
        m = order_re.fullmatch(path)
        if not m:
            continue
        close = ENTRY_END_RE.search(page, end)
        entry = _text(page[start:close.start() if close else len(page)])
        stem = re.sub(r"\.pdf$", "", m.group(1), flags=re.I)
        date = _date(entry)
        if fm := FILE_NUMBER_RE.search(stem):
            year, number = int(fm.group(1)), int(fm.group(2))
        elif (tm := TEXT_NUMBER_RE.search(entry)) and date:
            year, number = int(date[:4]), int(tm.group(1))
        else:
            raise RuntimeError(f"{folder['folder']}: no order number/year for {url}")
        order = orders.setdefault((year, number), {
            "folder": folder["folder"], "governor": folder["governor"], "year": year,
            "number": number, "title": None, "date": None, "url": url})
        title = LABEL_RE.sub("", " " + LEAD_RE.sub("", entry))
        if (tail := PAREN_TAIL_RE.search(title)) and _date(tail.group(1)):
            title = title[:tail.start()]
        title = title.strip(" -–—:,") or None
        if title and (order["title"] is None or len(title) > len(order["title"])):
            order["title"] = title
        order["date"] = order["date"] or date
        if url.lower().endswith(".pdf"):  # the official document over its page
            order["url"] = url
    if not orders:
        raise RuntimeError(f"{folder['folder']}: no executive orders listed (markup changed?)")
    return sorted(orders.values(), key=lambda o: (o["year"], o["number"]))


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
