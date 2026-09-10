"""Bounded CivicClerk collection through its published OData API."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from importer.civicclerk import (
    adapt_meeting,
    event_record,
    minutes_files,
    parse_roster,
    roster_members,
)
from importer.import_local import SEATS_PATH
from importer.roster import load_curation
from scraper.http import save_json

PAGE = 100
REFRESH_AFTER = timedelta(days=7)


def call(http, url: str, delay: float, **params):
    response = http.get(url, params=params, timeout=90)
    response.raise_for_status()
    time.sleep(delay)
    return response


def retain_revision(path: Path, value) -> None:
    """Retain native inputs, including candidates that fail attribution checks."""
    content = {key: field for key, field in value.items() if key != "checked_at"}
    digest = hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()
    revisions = path.parent / "revisions" / path.stem
    revisions.mkdir(parents=True, exist_ok=True)
    destination = revisions / f"{digest}.json"
    if not destination.exists():
        save_json(destination, value)


def fetch_events(http, spec: dict, delay: float) -> list[dict]:
    events, seen, skip = [], set(), 0
    while True:
        page = call(http, f"{spec['api_base']}/Events", delay, **{
            "$top": PAGE, "$skip": skip, "$orderby": "eventDate desc,id desc",
            "$filter": f"eventCategoryId eq {spec['category_id']}"
                       f" and eventDate ge {spec['start_date']}T00:00:00Z",
        }).json()
        rows = page["value"]
        if not isinstance(rows, list) or len(rows) > PAGE:
            raise ValueError("Invalid CivicClerk event page")
        for event in rows:
            if event["id"] in seen:
                raise ValueError("Repeated CivicClerk event while paging")
            seen.add(event["id"])
            if event.get("isDeleted") or event["isPublished"] != "Published":
                continue
            event_record(event, spec)
            events.append(event)
        if not rows:
            if page.get("@odata.nextLink"):
                raise ValueError("Empty CivicClerk page with continuation")
            return events
        if len(rows) < PAGE and not page.get("@odata.nextLink"):
            return events
        # Keep paging on the reviewed endpoint; never follow an arbitrary nextLink.
        skip += len(rows)


def fetch_tenant(http, spec: dict, budget: list[int], delay: float, data_dir: Path):
    out = data_dir / spec["tenant"]
    out.mkdir(parents=True, exist_ok=True)
    curated = load_curation(SEATS_PATH)[spec["tenant"]]
    now = datetime.now(UTC)
    roster = {"source_url": spec["roster_url"], "checked_at": now.isoformat(),
              "members": parse_roster(call(http, spec["roster_url"], delay).text,
                                      spec["roster_url"])}
    retain_revision(out / "roster.json", roster)
    roster_members(roster, spec, curated)
    save_json(out / "roster.json", roster)
    events = fetch_events(http, spec, delay)
    save_json(out / "events.json", events)
    today = date.today().isoformat()
    upcoming = [e for e in events if e["eventDate"][:10] >= today]
    past = [e for e in events if e["eventDate"][:10] < today]
    anchor = spec.get("bootstrap_event_id")
    if (anchor is not None and not (out / f"event_{anchor}.json").exists()
            and not any(e["id"] == anchor for e in past)):
        raise ValueError("Reviewed CivicClerk bootstrap meeting missing from listing")
    # New records first; stale published records refresh within the same request cap.
    past.sort(key=lambda e: (out / f"event_{e['id']}.json").exists())
    if anchor is not None and not (out / f"event_{anchor}.json").exists():
        past.sort(key=lambda e: e["id"] != anchor)
    fetched = cached = pending = 0
    for event in past:
        dest = out / f"event_{event['id']}.json"
        held = json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else None
        if held:
            stamp = datetime.fromisoformat(held["checked_at"])
            if stamp.tzinfo is None:
                raise ValueError("CivicClerk archive needs a dated collection record")
            refresh_after = REFRESH_AFTER if minutes_files(event) else timedelta(days=1)
            if (timedelta(0) <= now - stamp < refresh_after
                    and held["event"] == event):
                cached += 1
                continue
        if (budget[0] == 0 or fetched >= spec["max_new_per_run"]
                or not event.get("hasAgenda") or not event.get("agendaId")):
            pending += 1
            continue
        meeting = call(http, f"{spec['api_base']}/Meetings/{event['agendaId']}", delay).json()
        data = {"provider": "civicclerk", "version": 1, "checked_at": now.isoformat(),
                "event": event, "meeting": meeting}
        retain_revision(dest, data)
        normalized = adapt_meeting(data, spec, curated)
        if held:
            previous = adapt_meeting(held, spec, curated)
            old_positions = {(item, v["VotePersonId"]) for item, rows in previous["votes"].items()
                             for v in rows}
            new_positions = {(item, v["VotePersonId"]) for item, rows in normalized["votes"].items()
                             for v in rows}
            old_actions = {i["EventItemId"] for i in previous["items"]}
            new_actions = {i["EventItemId"] for i in normalized["items"]}
            if (not old_positions <= new_positions or not old_actions <= new_actions
                    or (minutes_files(held["event"]) and not minutes_files(event))):
                raise ValueError(
                    "CivicClerk refresh removed recorded data; review retained revision"
                )
            retain_revision(dest, held)
        save_json(dest, data)
        budget[0] -= 1
        fetched += 1
    save_json(out / "upcoming.json", upcoming)
    save_json(out / "coverage.json", {
        "since": spec["since"], "start_date": spec["start_date"],
        "listed_meetings": len(past), "pending_meetings": pending,
        "checked_at": now.isoformat(),
    })
    return fetched, cached
