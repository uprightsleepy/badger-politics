"""Adapt published CivicClerk records to the shared council import contract."""

from __future__ import annotations

import re
from datetime import date, datetime

from lxml import html

VOTE_FIELDS = {"yesVotes": "Yes", "noVotes": "No", "abstainVotes": "Abstain"}
MOTION_RADIX = 1000


def positive_id(value) -> int:
    if type(value) is not int or not 0 < value < 2**53 // MOTION_RADIX:
        raise ValueError("Invalid CivicClerk identifier")
    return value


def name_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing CivicClerk member name")
    return " ".join(value.split()).casefold()


def identity_index(curated: dict) -> dict[str, int]:
    """Only full names and individually verified aliases may identify a person."""
    found = {}
    for pid, entry in curated.items():
        person_id = positive_id(int(pid))
        for name in [entry["name"], *entry.get("aliases", [])]:
            key = name_key(name)
            if key in found and found[key] != person_id:
                raise ValueError("Ambiguous CivicClerk identity curation")
            found[key] = person_id
    return found


def resolve_name(name: str, identities: dict) -> int:
    try:
        return identities[name_key(name)]
    except KeyError:
        raise ValueError(f"Unreviewed CivicClerk member: {name!r}") from None


def parse_roster(page: str) -> list[dict]:
    """Read named district headings, excluding navigation and contact details."""
    found = []
    for heading in html.fromstring(page).xpath("//h3"):
        match = re.fullmatch(r"(.+),\s*District\s+(\d+)", heading.text_content().strip())
        if match:
            found.append({"name": match[1].strip(), "seat": int(match[2])})
    return found


def roster_members(snapshot: dict, spec: dict, curated: dict) -> tuple[list[dict], set[int]]:
    stamp = datetime.fromisoformat(snapshot["checked_at"])
    if stamp.tzinfo is None or snapshot["source_url"] != spec["roster_url"]:
        raise ValueError("Invalid CivicClerk roster provenance")
    identities = identity_index(curated)
    office, current, seats = [], set(), set()
    for member in snapshot["members"]:
        pid = resolve_name(member["name"], identities)
        seat = member["seat"]
        if (type(seat) is not int or curated[str(pid)]["seat"] != seat
                or pid in current or seat in seats):
            raise ValueError("CivicClerk roster changed; review district attribution")
        current.add(pid)
        seats.add(seat)
        office.append({"OfficeRecordPersonId": pid, "OfficeRecordFullName": member["name"],
                       "OfficeRecordMemberType": "Member"})
    if seats != set(range(1, spec["seats"] + 1)):
        raise ValueError("Incomplete CivicClerk district roster")
    return office, current


def event_record(event: dict, spec: dict) -> dict:
    event_id = positive_id(event["id"])
    day = date.fromisoformat(event["eventDate"][:10]).isoformat()
    if (event["eventCategoryId"] != spec["category_id"] or day < spec["start_date"]
            or event.get("isDeleted") or event["isPublished"] != "Published"):
        raise ValueError("CivicClerk event is outside the reviewed council scope")
    location = event.get("eventLocation") or {}
    return {
        "EventId": event_id, "EventDate": day,
        "EventInSiteURL": f"{spec['insite']}/event/{event_id}/files",
        "EventMinutesStatusName": "Published" if minutes_files(event) else None,
        "EventLocation": ", ".join(location[k] for k in ("address1", "address2", "city")
                                   if location.get(k)),
    }


def minutes_files(record: dict) -> list[tuple]:
    return sorted((positive_id(f["fileId"]), f["publishOn"])
                  for f in record["publishedFiles"] if f["type"] == "Minutes")


def walk_items(items: list[dict]):
    if not isinstance(items, list):
        raise ValueError("Invalid CivicClerk item list")
    for item in items:
        yield item
        yield from walk_items(item["childItems"])


def adapt_meeting(data: dict, spec: dict, curated: dict) -> dict:
    """Keep every nested motion, even when the source's hasVote flag is false."""
    if data.get("provider") != "civicclerk" or data.get("version") != 1:
        raise ValueError("Unrecognized CivicClerk archive")
    event, meeting = data["event"], data["meeting"]
    normalized = event_record(event, spec)
    agenda_id = positive_id(event["agendaId"])
    if positive_id(meeting["id"]) != agenda_id:
        raise ValueError("CivicClerk meeting does not match its event")
    identities = identity_index(curated)
    items, votes, seen = [], {}, set()
    for source in walk_items(meeting["items"]):
        source_id = positive_id(source["id"])
        if (source_id in seen or source["agendaObjectId"] not in (0, agenda_id)
                or source["eventId"] not in (0, event["id"])):
            raise ValueError("Duplicate or mismatched CivicClerk agenda item")
        seen.add(source_id)
        motions = source["minutesItemVotes"]
        if not isinstance(motions, list) or len(motions) >= MOTION_RADIX:
            raise ValueError("Invalid CivicClerk motion list")
        for ordinal, motion in enumerate(motions, 1):
            if {k for k in motion if k.lower().endswith("votes")} - VOTE_FIELDS.keys():
                raise ValueError("Unreviewed CivicClerk vote arrays")
            # A reversible (source item, motion ordinal) key; never collapse motions.
            item_id = source_id * MOTION_RADIX + ordinal
            action = motion["motionName"]
            if not isinstance(action, str) or not action.strip():
                raise ValueError("Missing CivicClerk motion text")
            outcome = motion["passFail"]
            if type(outcome) is not int or outcome not in (0, 1):
                raise ValueError("Unreviewed CivicClerk motion outcome")
            people, positions = set(), []
            for field, value in VOTE_FIELDS.items():
                if not isinstance(motion[field], list):
                    raise ValueError("Invalid CivicClerk vote array")
                for name in motion[field]:
                    pid = resolve_name(name, identities)
                    if pid in people:
                        raise ValueError("Duplicate or conflicting CivicClerk vote")
                    people.add(pid)
                    positions.append({"VotePersonId": pid, "VotePersonName": name,
                                      "VoteValueName": value})
            items.append({
                "EventItemId": item_id, "EventItemMatterId": source_id,
                "EventItemTitle": source["agendaObjectItemName"],
                "EventItemActionName": action, "EventItemPassedFlag": outcome,
                "EventItemAgendaNumber": source.get("agendaObjectItemOutlineNumber"),
                "EventItemMoverId": resolve_name(motion["initiatedBy"], identities)
                if motion.get("initiatedBy") else None,
                "EventItemSeconderId": resolve_name(motion["secondedBy"], identities)
                if motion.get("secondedBy") else None,
            })
            votes[str(item_id)] = positions
    return {"event": normalized, "items": items, "votes": votes, "rollcalls": {}, "links": {}}
