"""Council votes from the Legistar Web API, tenant by tenant.

Usage: python -m scraper.fetch_local_votes [--max-new N] [--delay S]

For each registry tenant (importer/local_registry.py): the body's vote
vocabulary and office records refresh every run; each council meeting is
one cached JSON file holding the event, its agenda items, the
per-member votes for every acted item, each item's own InSite link read
from the meeting's page (InSite's ids are not the API's), and the
per-member attendance of every roll-call item. A meeting refetches only while
its minutes are not settled under the tenant's reviewed status vocabulary.
Meetings are fetched newest first after any reviewed bootstrap meeting.

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
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote, urlencode

import requests

from importer.local_registry import TENANTS
from scraper.http import session

BASE = "https://webapi.legistar.com/v1"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "local"
PAGE = 1000


def save_json(path: Path, value) -> None:
    pending = path.with_suffix(".json.tmp")
    pending.write_text(json.dumps(value, indent=0), encoding="utf-8")
    pending.replace(path)


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
LEG_LINK = re.compile(
    r'href="LegislationDetail\.aspx\?ID=(\d+)&amp;GUID=([0-9A-Fa-f-]+)[^"]*"[^>]*>(.*?)</a>', re.S
)


def grid_pages(http, url: str, delay: float):
    """Every page of an InSite grid. The grid shows a fixed number of rows
    a page; later pages come through the plain form postback each page
    link carries for browsers without JS."""
    response = http.get(url, timeout=90)
    response.raise_for_status()
    time.sleep(delay)
    page = 1
    while True:
        text = response.text
        yield text
        page += 1
        target = {int(n): t for t, n in PAGE_LINK.findall(text)}.get(page)
        if target is None:
            return
        form = dict(HIDDEN.findall(text))
        form.update({"__EVENTTARGET": target, "__EVENTARGUMENT": ""})
        response = http.post(url, data=form, timeout=90)
        response.raise_for_status()
        time.sleep(delay)


def fetch_departments(http, insite: str, delay: float) -> list[dict]:
    """InSite's public listing of every body, name and page url. Its page
    ids and GUIDs differ from the API's, so this is the only way to link a
    body."""
    return [
        {"name": html.unescape(re.sub(r"<[^>]+>", "", label)).strip(),
         "url": f"{insite}/DepartmentDetail.aspx?ID={dept_id}&GUID={guid}"}
        for text in grid_pages(http, f"{insite}/Departments.aspx", delay)
        for dept_id, guid, label in DEPT_ROW.findall(text)
    ]


def parse_links(page: str, insite: str, found: dict | None = None) -> dict[str, str]:
    """File number -> the item's own InSite page, read from the meeting's
    page. InSite's legislation ids are not the API's matter ids, and the
    meeting page is where the clerk publishes them. A file number shown
    with two different links maps to none."""
    found = {} if found is None else found
    for leg_id, guid, label in LEG_LINK.findall(page):
        name = html.unescape(re.sub(r"<[^>]+>", "", label)).strip()
        if name:
            found.setdefault(name, set()).add(
                f"{insite}/LegislationDetail.aspx?ID={leg_id}&GUID={guid}"
            )
    return {name: next(iter(urls)) for name, urls in found.items() if len(urls) == 1}


def fetch_links(http, event: dict, insite: str, delay: float) -> dict[str, str]:
    """Item links from every page of the meeting's item grid (200 rows a
    page on Milwaukee's long agendas)."""
    url = event.get("EventInSiteURL")
    if not url:
        return {}
    found: dict[str, set[str]] = {}
    links: dict[str, str] = {}
    for text in grid_pages(http, url, delay):
        links = parse_links(text, insite, found)
    return links


def fetch_rollcalls(http, tenant: str, items: list[dict], delay: float) -> dict[str, list]:
    """Per-member attendance for each roll-call item of a meeting."""
    return {
        str(i["EventItemId"]): call(
            http, tenant, f"EventItems/{i['EventItemId']}/RollCalls", delay
        )
        for i in items if i.get("EventItemRollCallFlag")
    }


def fetch_tenant(
    http, spec: dict, budget: list[int], delay: float, data_dir: Path | None = None,
) -> tuple[int, int]:
    tenant = spec["tenant"]
    out = (data_dir if data_dir is not None else DATA_DIR) / tenant
    out.mkdir(parents=True, exist_ok=True)

    vote_types = call(http, tenant, "VoteTypes", delay)
    save_json(out / "votetypes.json", vote_types)
    office = call(
        http, tenant, "OfficeRecords", delay,
        **{"$top": PAGE, "$filter": f"OfficeRecordBodyName eq '{spec['body_name']}'"},
    )
    if len(office) >= PAGE:
        raise RuntimeError(f"{tenant}: office records hit the page cap; add paging")
    save_json(out / "officerecords.json", office)

    today = date.today().isoformat()
    # for sitting members: their person record (contacts where the tenant
    # fills them in) and every body they sit on, for committee lists
    bodies = call(http, tenant, "Bodies", delay, **{"$top": PAGE})
    if len(bodies) >= PAGE:
        raise RuntimeError(f"{tenant}: bodies hit the page cap; add paging")
    save_json(out / "bodies.json", bodies)
    sitting = sorted({
        r["OfficeRecordPersonId"] for r in office
        if (r.get("OfficeRecordEndDate") or "")[:10] >= today
    })
    # every member's person record: the full name where the office record
    # abbreviates it, and contacts for sitting members
    people = sorted({r["OfficeRecordPersonId"] for r in office})
    persons = {str(pid): call(http, tenant, f"Persons/{pid}", delay) for pid in people}
    save_json(out / "persons.json", persons)
    memberships = {
        str(pid): call(
            http, tenant, "OfficeRecords", delay,
            **{"$top": PAGE, "$filter": f"OfficeRecordPersonId eq {pid}"},
        )
        for pid in sitting
    }
    if any(len(rows) >= PAGE for rows in memberships.values()):
        raise RuntimeError(f"{tenant}: memberships hit the page cap; add paging")
    save_json(out / "memberships.json", memberships)
    departments = fetch_departments(http, spec["insite"], delay)
    save_json(out / "departments.json", departments)
    fetched = cached = pending_count = past_count = newly_fetched = 0
    limit = spec.get("max_new_per_run")
    final_minutes = spec.get("final_minutes", ("Final",))
    upcoming = []
    events = fetch_events(http, tenant, spec["body_name"], spec["since"], delay)
    anchor = spec.get("bootstrap_event_id")
    if anchor is not None and not (out / f"event_{anchor}.json").exists():
        if not any(e["EventId"] == anchor for e in events):
            raise RuntimeError(f"{tenant}: reviewed bootstrap meeting missing from event listing")
        # Include a verified individual roll call in the first bounded batch.
        events = sorted(events, key=lambda e: e["EventId"] != anchor)
    for event in events:
        if (event.get("EventDate") or "")[:10] >= today:
            upcoming.append(event)  # agenda for a meeting not held yet
            continue
        past_count += 1
        dest = out / f"event_{event['EventId']}.json"
        is_new = not dest.exists()
        if not is_new:
            held = json.loads(dest.read_text(encoding="utf-8"))
            if held["event"].get("EventMinutesStatusName") in final_minutes:
                # cached before item links or attendance were kept: filled once
                changed = False
                if "links" not in held:
                    held["links"] = fetch_links(http, held["event"], spec["insite"], delay)
                    changed = True
                if "rollcalls" not in held:
                    held["rollcalls"] = fetch_rollcalls(http, tenant, held["items"], delay)
                    changed = True
                if changed:
                    save_json(dest, held)
                cached += 1
                continue  # minutes final: the record is settled
        if budget[0] == 0 or (is_new and limit is not None and newly_fetched >= limit):
            pending_count += 1
            continue  # --max-new exhausted; the rest stays for the next run
        budget[0] -= 1
        items = call(http, tenant, f"Events/{event['EventId']}/EventItems", delay)
        if len(items) >= PAGE:
            raise RuntimeError(f"{tenant}: meeting items hit the page cap; add paging")
        votes: dict[str, list] = {}
        for item in items:
            if item.get("EventItemActionName"):
                votes[str(item["EventItemId"])] = call(
                    http, tenant, f"EventItems/{item['EventItemId']}/Votes", delay
                )
        links = fetch_links(http, event, spec["insite"], delay)
        rollcalls = fetch_rollcalls(http, tenant, items, delay)
        save_json(dest, {"event": event, "items": items, "votes": votes, "links": links,
                         "rollcalls": rollcalls})
        fetched += 1
        newly_fetched += int(is_new)
        if fetched % 25 == 0:
            print(f"{tenant}: {fetched} meetings fetched, at {event['EventDate'][:10]}",
                  flush=True)
    # the meetings not held yet, for the calendar; refreshed every run
    save_json(out / "upcoming.json", upcoming)
    save_json(out / "coverage.json", {
        "since": spec["since"], "listed_meetings": past_count,
        "pending_meetings": pending_count, "checked_at": datetime.now(UTC).isoformat(),
    })
    return fetched, cached


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-new", type=int, help="fetch at most N meetings per run")
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--tenant", action="append", choices=[s["tenant"] for s in TENANTS],
                        help="collect only these tenants (repeatable); default: all")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR,
                        help="council archive root; use a separate directory for dev")
    ns = parser.parse_args(argv)

    http = session()
    budget = [ns.max_new if ns.max_new is not None else -1]
    for spec in TENANTS:
        if ns.tenant and spec["tenant"] not in ns.tenant:
            continue
        fetched, cached = fetch_tenant(http, spec, budget, ns.delay, ns.data_dir)
        print(f"{spec['tenant']}: {fetched} meetings fetched, {cached} already final")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
