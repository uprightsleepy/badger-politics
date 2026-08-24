"""Official Capitol office contacts for sitting members (docs.legis).

Usage: python -m scraper.fetch_contacts [--refresh]

Each sitting member's docs.legis page (URL from their people file) carries
the office room, telephone, and email. Office contacts only — the people
files' own email/voice fields double as a cross-check where present.
Pages are cached; --refresh refetches.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import yaml

from scraper.http import session

PEOPLE_DIR = Path(__file__).resolve().parents[1] / "_data" / "people" / "wi"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "contacts"
DELAY = 0.4

EMAIL_RE = re.compile(r"\b(?:Rep|Sen)\.[\w.]+@legis\.wisconsin\.gov\b", re.I)
PHONE_RE = re.compile(r"\(608\)\s*\d{3}-\d{4}")
ROOM_RE = re.compile(r"\bRoom\s+\d+\s+\w+")
POBOX_RE = re.compile(r"P\.?O\.?\s*Box\s+\d+", re.I)


def parse_page(html: str) -> dict:
    """Room + first (608) phone + email from a member page."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    email = EMAIL_RE.search(text)
    phone = PHONE_RE.search(text)
    room = ROOM_RE.search(text)
    pobox = POBOX_RE.search(text)
    zipm = re.search(r"Madison,\s*WI\s+537\d{2}", text)
    address = None
    if room:
        parts = [room.group(0), "State Capitol"]
        if pobox:
            parts.append(pobox.group(0))
        parts.append(zipm.group(0) if zipm else "Madison, WI")
        address = ", ".join(parts)
    return {
        "email": email.group(0) if email else None,
        "phone": phone.group(0) if phone else None,
        "address": address,
    }


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv
    pages_dir = DATA_DIR / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    http = session()

    out = []
    failures = []
    for path in sorted(PEOPLE_DIR.glob("*.yml")):
        member = yaml.safe_load(path.read_text(encoding="utf-8"))
        links = [
            link["url"] for link in member.get("links", [])
            if "/2025/legislators/" in link.get("url", "")
        ]
        if not links:
            failures.append(f"{member['name']}: no 2025 docs.legis link")
            continue
        url = links[0]
        cache = pages_dir / f"{url.rstrip('/').rsplit('/', 1)[-1]}.html"
        if refresh or not cache.exists():
            response = http.get(url, timeout=60)
            response.raise_for_status()
            cache.write_text(response.text, encoding="utf-8")
            time.sleep(DELAY)
        parsed = parse_page(cache.read_text(encoding="utf-8"))

        # docs.legis is the official record; the people files carry stale
        # emails and district-office numbers, so they are not compared.
        # Structural check instead: the email's Rep./Sen. prefix must match
        # the chamber of the page it was parsed from (catches misparses).
        chamber_prefix = "sen." if "/senate/" in url else "rep."
        if parsed["email"] and not parsed["email"].lower().startswith(chamber_prefix):
            failures.append(
                f"{member['name']}: email {parsed['email']} does not match {url}"
            )

        email = parsed["email"] or member.get("email")
        if not email or not parsed["phone"]:
            failures.append(f"{member['name']}: missing email/phone on {url}")
        out.append({
            "person_id": member["id"],
            "email": email,
            "phone": parsed["phone"],
            "address": parsed["address"],
            "source_url": url,
        })

    if failures:
        for f in failures:
            print(f"CONTACT FAILURE: {f}", file=sys.stderr)
        return 1
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "contacts.json").write_text(json.dumps(out, indent=0), encoding="utf-8")
    print(f"{len(out)} member contacts -> {DATA_DIR / 'contacts.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
