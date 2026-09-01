"""Official portraits and office contacts for council members, from each
city's own web pages.

Usage: python -m scraper.fetch_local_profiles [--delay S]

Legistar carries no photos, and Milwaukee's person records carry no
contacts, so these come from the pages the cities publish per district:
city.milwaukee.gov's Common Council district pages and westalliswi.gov's
district pages (both allow crawling in robots.txt; twenty small requests
a night). This fetcher only captures what each page shows, keyed by
district. The importer attributes a capture to a member under an exact
rule (the photo's own alt text names the district; the heading above a
West Allis portrait is the curated name), and anything that does not
match stays unattributed.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

import requests
from lxml import html as lxml_html

from scraper.http import session as http_session

DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "local"
OUT = DATA_DIR / "profiles.json"

MKE_BASE = "https://city.milwaukee.gov"
# the city uses both spellings across its district pages
MKE_PATHS = (
    "/CommonCouncil/Council-Members/District{n}",
    "/CommonCouncil/CouncilMembers/District{n}",
)
MKE_HEADSHOT_DIR = "/ImageLibrary/Groups/ccCouncil/"
WA_PAGES = {
    1: "https://www.westalliswi.gov/page/district-one",
    2: "https://www.westalliswi.gov/page/district-two",
    3: "https://www.westalliswi.gov/page/district-three",
    4: "https://www.westalliswi.gov/page/district-four",
    5: "https://www.westalliswi.gov/page/district-five",
}
PHONE_RE = re.compile(r"\(?\b414\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.gov")


def milwaukee_district(http: requests.Session, n: int, delay: float) -> dict | None:
    """What the city's page for district n shows: headshots with their alt
    text, and every mailto/tel link. Attribution happens in the importer."""
    for pattern in MKE_PATHS:
        url = MKE_BASE + pattern.format(n=n)
        response = http.get(url, timeout=60)
        time.sleep(delay)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        tree = lxml_html.fromstring(response.text)
        photos = [
            {"src": MKE_BASE + src.split("?")[0], "alt": alt.strip()}
            for img in tree.xpath("//img[@src and @alt]")
            for src, alt in [(img.get("src"), img.get("alt") or "")]
            if src.startswith(MKE_HEADSHOT_DIR) and alt.lower().startswith("photo of")
        ]
        # the city's CDN rewrites mailto hrefs for spam protection but leaves
        # the address in the link's own title attribute; read that, plainly
        mailto = sorted({
            a.get("href")[7:].split("?")[0]
            for a in tree.xpath("//a[starts-with(@href, 'mailto:')]")
        } | {
            a.get("title")[7:].strip()
            for a in tree.xpath("//a[starts-with(@title, 'mailto:')]")
        })
        tel = sorted({
            re.sub(r"[^\d]", "", a.get("href")[4:])[-10:]
            for a in tree.xpath("//a[starts-with(@href, 'tel:')]")
        })
        return {"page": url, "photos": photos, "mailto": mailto, "tel": tel}
    return None


def west_allis_district(http: requests.Session, n: int, delay: float) -> dict:
    """The page's content nodes in order: each name heading, then the image
    and text that follow it until the next heading."""
    url = WA_PAGES[n]
    response = http.get(url, timeout=60)
    time.sleep(delay)
    response.raise_for_status()
    s = response.text.replace("\\/", "/").replace('\\"', '"')
    parts = re.split(r'"type":"(CONTENT_NODE_[A-Z_]+)"', s)
    entries: list[dict] = []
    for kind, seg in zip(parts[1::2], parts[2::2], strict=False):
        if kind == "CONTENT_NODE_HEADING":
            m = re.search(r"<h[23]>(.*?)</h[23]>", seg)
            if m:
                name = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
                entries.append({"heading": name, "image": None, "emails": [], "phones": []})
        elif entries and kind == "CONTENT_NODE_IMAGE":
            m = re.search(r"https://cmsv2-assets\.apptegy\.net/uploads/[^\" ]+\.(?:jpe?g|png)", seg)
            if m and entries[-1]["image"] is None:
                entries[-1]["image"] = m.group(0)
        elif entries and kind == "CONTENT_NODE_TEXT":
            text = html.unescape(re.sub(r"<[^>]+>", " ", seg))
            entries[-1]["emails"] = sorted(set(entries[-1]["emails"]) | set(EMAIL_RE.findall(text)))
            entries[-1]["phones"] = sorted(
                set(entries[-1]["phones"])
                | {re.sub(r"[^\d]", "", p)[-10:] for p in PHONE_RE.findall(text)}
            )
    return {"page": url, "entries": entries}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay", type=float, default=0.5)
    ns = parser.parse_args(argv)
    http = http_session()
    profiles = {"milwaukee": {"seats": {}}, "westalliswi": {"districts": {}}}
    for n in range(1, 16):
        found = milwaukee_district(http, n, ns.delay)
        if found is None:
            print(f"milwaukee district {n}: no page at either path", file=sys.stderr)
            continue
        profiles["milwaukee"]["seats"][str(n)] = found
    for n in WA_PAGES:
        profiles["westalliswi"]["districts"][str(n)] = west_allis_district(http, n, ns.delay)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(profiles, indent=1), encoding="utf-8")
    mke = sum(len(s["photos"]) for s in profiles["milwaukee"]["seats"].values())
    wa = sum(1 for d in profiles["westalliswi"]["districts"].values()
             for e in d["entries"] if e["image"])
    print(f"profiles: {mke} Milwaukee headshots across"
          f" {len(profiles['milwaukee']['seats'])} district pages,"
          f" {wa} West Allis portraits -> {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
