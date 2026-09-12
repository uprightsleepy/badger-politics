"""Official portraits and office contacts for council members, from each
city's own web pages. Paused Milwaukee retrieval retains the complete archive
and records its freshness separately from the council's voting records.

Usage: python -m scraper.fetch_local_profiles

West Allis district pages and the Appleton/Waukesha council rosters refresh
normally. Retained Milwaukee profiles remain tied to archived member identities.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from lxml import html as lxml_html

from importer.civicclerk import name_key, portrait_url
from importer.import_local import milwaukee_profile_owners
from importer.local_registry import TENANTS
from scraper.http import session as http_session
from scraper.source_access import ACCESS

DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "local"
OUT = DATA_DIR / "profiles.json"

MKE_BASE = "https://city.milwaukee.gov"
MKE_DISTRICTS = range(1, 16)
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
PROFILE_SOURCES = [s for s in TENANTS if s.get("profile_url")]


def roster_profiles(page: str, spec: dict) -> dict:
    """One portrait per named district card, shared across municipal rosters."""
    tree = lxml_html.fromstring(page)
    base = urljoin(spec["profile_url"], next(iter(tree.xpath("//base/@href")), ""))
    directory = spec["profile_layout"] == "directory"
    cards = tree.xpath("//div[@class='row'][div/h2]" if directory
                       else "//div[@class='alderperson']")
    members = []
    for card in cards:
        heading = card.xpath(".//h2" if directory else "./h3")
        if len(heading) != 1:
            continue
        text = " ".join(heading[0].itertext()).strip()
        seat = re.search(r"\bDistrict\s+(\d+)\b", text)
        if not seat:
            continue
        name = text.split(", District")[0] if directory else card.xpath("string(./h4)").strip()
        name_key(name)
        if directory:
            images = [match[1] for style in card.xpath(".//div[@class='rz-block-img']/@style")
                      if (match := re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", style))]
        else:
            images = card.xpath("./img/@src")
        urls = {urljoin(base, src) for src in images}
        image = next(iter(urls)) if len(urls) == 1 else None
        if image and not portrait_url(image, spec["profile_url"]):
            image = None
        members.append({"name": name, "seat": int(seat[1]), "image": image})
    if (len(members) != spec["seats"]
            or {m["seat"] for m in members} != set(range(1, spec["seats"] + 1))):
        raise ValueError(f"{spec['tenant']}: incomplete profile roster")
    return {"page": spec["profile_url"], "members": members}


def milwaukee_district(http: requests.Session, n: int) -> dict | None:
    """What the city's page for district n shows: headshots with their alt
    text, and every mailto/tel link. Attribution happens in the importer."""
    for pattern in MKE_PATHS:
        url = MKE_BASE + pattern.format(n=n)
        response = http.get(url, timeout=60)
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


def west_allis_district(http: requests.Session, n: int) -> dict:
    """The page's content nodes in order: each name heading, then the image
    and text that follow it until the next heading."""
    url = WA_PAGES[n]
    response = http.get(url, timeout=60)
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


def retained_milwaukee(profiles: dict) -> dict:
    """A paused source needs every archived district; never substitute an empty profile."""
    archived = profiles.get("milwaukee")
    seats = archived.get("seats") if isinstance(archived, dict) else None
    if not isinstance(seats, dict) or not {str(n) for n in MKE_DISTRICTS} <= seats.keys():
        raise RuntimeError("Paused Milwaukee profiles require a complete existing archive")
    for n in MKE_DISTRICTS:
        page = seats[str(n)]
        if (not isinstance(page, dict)
                or page.get("page") not in {MKE_BASE + p.format(n=n) for p in MKE_PATHS}
                or not isinstance(page.get("photos"), list)
                or any(not isinstance(photo, dict)
                       or not all(isinstance(photo.get(k), str) for k in ("src", "alt"))
                       for photo in page["photos"])
                or any(not isinstance(page.get(k), list)
                       or not all(isinstance(value, str) for value in page[k])
                       for k in ("mailto", "tel"))):
            raise RuntimeError(f"Invalid archived Milwaukee profile for district {n}")
    return archived


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    profiles = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if not isinstance(profiles, dict) or not isinstance(profiles.get("_refresh", {}), dict):
        raise RuntimeError("Invalid local profile archive")
    refresh = profiles.setdefault("_refresh", {})
    http = http_session()
    if ACCESS.policies["city.milwaukee.gov"].get("paused"):
        profiles["milwaukee"] = retained_milwaukee(profiles)
        previous = refresh.get("milwaukee", {})
        refresh["milwaukee"] = {
            "state": "retained",
            "last_success_at": previous.get("last_success_at"),
            "person_ids": previous["person_ids"] if previous.get("state") == "retained"
                else milwaukee_profile_owners(DATA_DIR),
        }
        print("Milwaukee profiles paused; retained all archived districts", file=sys.stderr)
    else:
        profiles["milwaukee"] = {"seats": {}}
        for n in MKE_DISTRICTS:
            found = milwaukee_district(http, n)
            if found is None:
                print(f"milwaukee district {n}: no page at either path", file=sys.stderr)
                continue
            profiles["milwaukee"]["seats"][str(n)] = found
        refresh["milwaukee"] = {
            "state": "refreshed", "last_success_at": datetime.now(UTC).isoformat(),
        }
    profiles["westalliswi"] = {"districts": {}}
    for n in WA_PAGES:
        profiles["westalliswi"]["districts"][str(n)] = west_allis_district(http, n)
    refresh["westalliswi"] = {
        "state": "refreshed", "last_success_at": datetime.now(UTC).isoformat(),
    }
    for spec in PROFILE_SOURCES:
        response = http.get(spec["profile_url"], timeout=60)
        response.raise_for_status()
        profiles[spec["tenant"]] = roster_profiles(response.text, spec)
        refresh[spec["tenant"]] = {
            "state": "refreshed", "last_success_at": datetime.now(UTC).isoformat(),
        }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pending = OUT.with_suffix(".json.tmp")
    pending.write_text(json.dumps(profiles, indent=1), encoding="utf-8")
    pending.replace(OUT)
    mke = sum(len(s["photos"]) for s in profiles["milwaukee"]["seats"].values())
    wa = sum(1 for d in profiles["westalliswi"]["districts"].values()
             for e in d["entries"] if e["image"])
    print(f"profiles: {mke} Milwaukee headshots across"
          f" {len(profiles['milwaukee']['seats'])} district pages,"
          f" {wa} West Allis portraits -> {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
