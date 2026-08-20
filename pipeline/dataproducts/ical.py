"""iCal artifacts: showing up to testify is the highest-leverage thing a
voter can do, so every hearing gets an "Add to calendar" file.

  /calendar/hearings.ics             all hearings, one VCALENDAR
  /calendar/hearings/{id}.ics        single hearing (the per-row button)
  /calendar/election-days.ics        statewide election dates for the cycle

Times are local America/Chicago with an embedded VTIMEZONE so Google/Apple/
Outlook import them correctly. Every event embeds "confirm against the
official hearing notice" plus the source link (plan §11).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dataproducts import queries

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/Chicago
BEGIN:DAYLIGHT
TZOFFSETFROM:-0600
TZOFFSETTO:-0500
TZNAME:CDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0600
TZNAME:CST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""

# WI 2026 statewide election days (WEC calendar)
ELECTION_DAYS_2026 = [
    ("2026-02-17", "Wisconsin Spring Primary"),
    ("2026-04-07", "Wisconsin Spring Election"),
    ("2026-08-11", "Wisconsin Partisan Primary"),
    ("2026-11-03", "Wisconsin General Election"),
]

DISCLAIMER = (
    "Confirm against the official hearing notice before attending. "
    "Badger Politics is an independent project, not affiliated with the "
    "State of Wisconsin."
)


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """RFC 5545 75-octet line folding."""
    out = []
    while len(line.encode("utf-8")) > 73:
        cut = 73
        while len(line[:cut].encode("utf-8")) > 73:
            cut -= 1
        out.append(line[:cut])
        line = " " + line[cut:]
    out.append(line)
    return "\r\n".join(out)


def _calendar(name: str, events: list[list[str]]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Badger Politics//badgerpolitics.org//EN",
        f"X-WR-CALNAME:{_escape(name)}",
        *VTIMEZONE.splitlines(),
    ]
    for event in events:
        lines.extend(event)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _hearing_event(hearing: dict) -> list[str] | None:
    if not hearing["date"]:
        return None
    date = hearing["date"].replace("-", "")
    time = (hearing["time"] or "09:00").replace(":", "") + "00"
    committee = hearing["committee_name"] or hearing.get("title") or "Committee"
    summary = f"Hearing: {committee}"
    bills_text = ", ".join(hearing["agenda_bills"])
    description = DISCLAIMER
    if bills_text:
        description = f"Bills: {bills_text}. {DISCLAIMER}"
    if hearing["source_url"]:
        description += f" Official notice: {hearing['source_url']}"
    uid = hearing["id"].rsplit("/", 1)[-1].replace(" ", "-")
    event = [
        "BEGIN:VEVENT",
        f"UID:{uid}@badgerpolitics.org",
        f"DTSTAMP:{date}T000000Z",
        f"DTSTART;TZID=America/Chicago:{date}T{time}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
    ]
    if hearing["location"]:
        event.append(f"LOCATION:{_escape(hearing['location'])}")
    if hearing["source_url"]:
        event.append(f"URL:{hearing['source_url']}")
    event.append("END:VEVENT")
    return event


def build_ical(conn: sqlite3.Connection, out: Path) -> int:
    calendar_dir = out / "calendar"
    (calendar_dir / "hearings").mkdir(parents=True, exist_ok=True)
    files = 0

    events = []
    for hearing in queries.hearings(conn):
        event = _hearing_event(hearing)
        if event is None:
            continue
        events.append(event)
        single = _calendar("Badger Politics — Hearing", [event])
        uid = hearing["id"].rsplit("/", 1)[-1].replace(" ", "-")
        (calendar_dir / "hearings" / f"{uid}.ics").write_text(
            single, encoding="utf-8", newline=""
        )
        files += 1

    (calendar_dir / "hearings.ics").write_text(
        _calendar("Wisconsin Legislature — Committee Hearings", events),
        encoding="utf-8",
        newline="",
    )
    files += 1

    election_events = []
    for date, name in ELECTION_DAYS_2026:
        compact = date.replace("-", "")
        election_events.append(
            [
                "BEGIN:VEVENT",
                f"UID:election-{date}@badgerpolitics.org",
                f"DTSTAMP:{compact}T000000Z",
                f"DTSTART;VALUE=DATE:{compact}",
                f"SUMMARY:{_escape(name)}",
                "DESCRIPTION:Polls are open 7am-8pm. Find your polling place at "
                "myvote.wi.gov.",
                "END:VEVENT",
            ]
        )
    (calendar_dir / "election-days.ics").write_text(
        _calendar("Wisconsin Election Days 2026", election_events),
        encoding="utf-8",
        newline="",
    )
    return files + 1
