"""Council votes from the Legistar Web API, tenant by tenant.

Usage: python -m scraper.fetch_local_votes [--max-new N] [--delay S]

For each registry tenant (importer/local_registry.py): the body's vote
vocabulary and office records refresh every run; each council meeting is
one cached JSON file holding the event, its agenda items, and the
per-member votes for every acted item. A meeting refetches only while
its minutes are not Final, so the one-time backfill is exactly that.
Meetings are fetched newest first, so an interrupted backfill still
leaves the recent record complete.

The API is Granicus's public, documented endpoint (no token for these
tenants, robots.txt absent, OData paging); we identify ourselves and
throttle. See "Do the sources permit API calls and crawling?" in
docs/research/local-votes-2026-08.md.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlencode

import requests

from importer.local_registry import TENANTS
from scraper.http import session

BASE = "https://webapi.legistar.com/v1"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "local"
PAGE = 1000


def call(http: requests.Session, tenant: str, path: str, delay: float, **params):
    qs = urlencode(params, quote_via=quote)
    url = f"{BASE}/{tenant}/{path}" + ("?" + qs if qs else "")
    response = http.get(url, timeout=90)
    response.raise_for_status()
    time.sleep(delay)
    return response.json()


def fetch_events(http, tenant: str, body: str, since: int, delay: float) -> list[dict]:
    """Every council meeting since Jan 1 of `since`, newest first."""
    events, skip = [], 0
    while True:
        page = call(
            http, tenant, "Events", delay,
            **{
                "$top": PAGE, "$skip": skip, "$orderby": "EventDate desc",
                "$filter": f"EventBodyName eq '{body}'"
                           f" and EventDate ge datetime'{since}-01-01'",
            },
        )
        events.extend(page)
        if len(page) < PAGE:
            return events
        skip += PAGE


DEPT_ROW = re.compile(
    r'href="DepartmentDetail\.aspx\?ID=(\d+)&amp;GUID=([0-9A-Fa-f-]+)[^"]*"[^>]*>(.*?)</a>', re.S
)
PAGE_LINK = re.compile(r"__doPostBack\(&#39;([^&]+)&#39;,&#39;&#39;\)\"><span>(\d+)</span></a>")
HIDDEN = re.compile(r'<input type="hidden" name="([^"]+)"[^>]*?value="([^"]*)"')


def fetch_departments(http, insite: str, delay: float) -> list[dict]:
    """InSite's public listing of every body, name and page url. Its page
    ids and GUIDs differ from the API's, so this is the only way to link a
    body. The grid shows 100 rows a page; later pages come through the
    plain form postback each page link carries for browsers without JS."""
    url = f"{insite}/Departments.aspx"
    response = http.get(url, timeout=60)
    response.raise_for_status()
    time.sleep(delay)
    rows, page = [], 1
    while True:
        text = response.text
        rows += [
            {"name": html.unescape(re.sub(r"<[^>]+>", "", label)).strip(),
             "url": f"{insite}/DepartmentDetail.aspx?ID={dept_id}&GUID={guid}"}
            for dept_id, guid, label in DEPT_ROW.findall(text)
        ]
        page += 1
        target = {int(n): t for t, n in PAGE_LINK.findall(text)}.get(page)
        if target is None:
            return rows
        form = dict(HIDDEN.findall(text))
        form.update({"__EVENTTARGET": target, "__EVENTARGUMENT": ""})
        response = http.post(url, data=form, timeout=60)
        response.raise_for_status()
        time.sleep(delay)


def fetch_tenant(http, spec: dict, budget: list[int], delay: float) -> tuple[int, int]:
    tenant = spec["tenant"]
    out = DATA_DIR / tenant
    out.mkdir(parents=True, exist_ok=True)

    vote_types = call(http, tenant, "VoteTypes", delay)
    (out / "votetypes.json").write_text(json.dumps(vote_types, indent=0), encoding="utf-8")
    office = call(
        http, tenant, "OfficeRecords", delay,
        **{"$top": PAGE, "$filter": f"OfficeRecordBodyName eq '{spec['body_name']}'"},
    )
    if len(office) >= PAGE:
        raise RuntimeError(f"{tenant}: office records hit the page cap; add paging")
    (out / "officerecords.json").write_text(json.dumps(office, indent=0), encoding="utf-8")

    today = date.today().isoformat()
    # for sitting members: their person record (contacts where the tenant
    # fills them in) and every body they sit on, for committee lists
    bodies = call(http, tenant, "Bodies", delay, **{"$top": PAGE})
    (out / "bodies.json").write_text(json.dumps(bodies, indent=0), encoding="utf-8")
    sitting = sorted({
        r["OfficeRecordPersonId"] for r in office
        if (r.get("OfficeRecordEndDate") or "")[:10] >= today
    })
    persons = {str(pid): call(http, tenant, f"Persons/{pid}", delay) for pid in sitting}
    (out / "persons.json").write_text(json.dumps(persons, indent=0), encoding="utf-8")
    memberships = {
        str(pid): call(
            http, tenant, "OfficeRecords", delay,
            **{"$top": PAGE, "$filter": f"OfficeRecordPersonId eq {pid}"},
        )
        for pid in sitting
    }
    (out / "memberships.json").write_text(json.dumps(memberships, indent=0), encoding="utf-8")
    departments = fetch_departments(http, spec["insite"], delay)
    (out / "departments.json").write_text(json.dumps(departments, indent=0), encoding="utf-8")
    fetched = cached = 0
    for event in fetch_events(http, tenant, spec["body_name"], spec["since"], delay):
        if (event.get("EventDate") or "")[:10] >= today:
            continue  # agenda for a meeting not held yet
        dest = out / f"event_{event['EventId']}.json"
        if dest.exists():
            held = json.loads(dest.read_text(encoding="utf-8"))
            if held["event"].get("EventMinutesStatusName") == "Final":
                cached += 1
                continue  # minutes final: the record is settled
        if budget[0] == 0:
            continue  # --max-new exhausted; the rest stays for the next run
        budget[0] -= 1
        items = call(http, tenant, f"Events/{event['EventId']}/EventItems", delay)
        votes: dict[str, list] = {}
        for item in items:
            if item.get("EventItemActionName"):
                votes[str(item["EventItemId"])] = call(
                    http, tenant, f"EventItems/{item['EventItemId']}/Votes", delay
                )
        dest.write_text(
            json.dumps({"event": event, "items": items, "votes": votes}, indent=0),
            encoding="utf-8",
        )
        fetched += 1
        if fetched % 25 == 0:
            print(f"{tenant}: {fetched} meetings fetched, at {event['EventDate'][:10]}",
                  flush=True)
    return fetched, cached


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-new", type=int, help="fetch at most N meetings per run")
    parser.add_argument("--delay", type=float, default=0.3)
    ns = parser.parse_args(argv)

    http = session()
    budget = [ns.max_new if ns.max_new is not None else -1]
    for spec in TENANTS:
        fetched, cached = fetch_tenant(http, spec, budget, ns.delay)
        print(f"{spec['tenant']}: {fetched} meetings fetched, {cached} already final")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
