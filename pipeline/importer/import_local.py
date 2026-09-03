"""Import council votes from the local Legistar cache into SQLite.

Usage: python -m importer.import_local <local_data_dir> <sqlite_path>

Attribution is the tenant's own person id on every vote row; there is no
name matching. Seats come from office-record titles where the tenant
records them (Milwaukee's "3rd District") and from the human-verified
importer/local_seats.json where it does not (West Allis prints "Ald.").
A member who appears only in vote records (no office record) is kept
with the tenant's own id and name and no term dates; the import reports
how many, and never invents dates for them.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

from importer.local_registry import TENANTS
from importer.person_slugs import slugify
from importer.roster import load_curation

SEATS_PATH = Path(__file__).resolve().parent / "local_seats.json"
MERGES_PATH = Path(__file__).resolve().parent / "local_person_merges.json"
COURTESY = {"ms.", "mr.", "mrs.", "dr."}
# Milwaukee office-record titles carry the seat: '3rd District'
TITLE_SEAT_RE = re.compile(r"^(\d+)(?:st|nd|rd|th) District$")
NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv"}

TABLES = (
    "local_upcoming", "local_rollcalls", "local_votes", "local_actions", "local_events",
    "local_memberships", "local_member_terms", "local_members", "local_vote_types",
    "local_bodies",
)


def _letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def surname(name: str) -> str:
    """'ALD. CHAMBERS JR.' -> 'chambers'; 'Daniel J. Roadt' -> 'roadt'."""
    words = name.split()
    while words and words[-1].lower().strip(".") in NAME_SUFFIXES:
        words.pop()
    return _letters(words[-1]) if words else ""


def fmt_phone(digits: str) -> str | None:
    d = re.sub(r"[^\d]", "", digits or "")[-10:]
    return f"{d[:3]}-{d[3:6]}-{d[6:]}" if len(d) == 10 else None


def strip_template_phones(seats: dict) -> dict:
    """A number on every district page is the site template's (Milwaukee's
    Unified Call Center), not any member's; only numbers particular to a
    page can be attributed."""
    if len(seats) < 2:
        return seats
    common = set.intersection(*(set(page["tel"]) for page in seats.values()))
    return {
        seat: {**page, "tel": [t for t in page["tel"] if t not in common]}
        for seat, page in seats.items()
    }


def attribute_profile(
    spec: dict, name: str, seat: int | None, curated_name: str | None,
    profiles: dict, person: dict | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """(image_url, image_basis, email, phone) for one sitting member, each
    attributed only under an exact rule; None otherwise.

    The tenant's own person record comes first for contacts. The city's
    district page then fills gaps: a Milwaukee headshot counts only when
    its alt text names this seat's district; a West Allis portrait only
    when the heading above it is the curated name; a mailto only when
    the member's surname is in the address; a phone only when the page
    shows exactly one for the seat."""
    email = (person or {}).get("PersonEmail", "").strip() or None
    phone = fmt_phone((person or {}).get("PersonPhone", "")) if person else None
    image = basis = None
    sn = surname(name)
    found = profiles.get(spec["tenant"], {})
    if seat is None:
        return image, basis, email, phone
    if spec["tenant"] == "milwaukee":
        page = (found.get("seats") or {}).get(str(seat))
        if page:
            hits = [x for x in page["photos"]
                    if re.search(rf"\bDistrict\s*{seat}\b", x["alt"], re.I)]
            if len(hits) == 1:
                image, basis = hits[0]["src"], page["page"]
            mails = [m for m in page["mailto"] if sn and sn in _letters(m.split("@")[0])]
            if email is None and len(mails) == 1:
                email = mails[0]
            if phone is None and len(page["tel"]) == 1:
                phone = fmt_phone(page["tel"][0])
    elif spec["tenant"] == "westalliswi" and curated_name:
        page = (found.get("districts") or {}).get(str(seat))
        if page:
            key = _letters(curated_name)
            hits = [e for e in page["entries"]
                    if _letters(e["heading"].split(" - ")[0]) == key]
            if len(hits) == 1:
                entry = hits[0]
                if entry.get("image"):
                    image, basis = entry["image"], page["page"]
                mails = [m for m in entry["emails"] if sn and sn in _letters(m.split("@")[0])]
                if email is None and len(mails) == 1:
                    email = mails[0]
                if phone is None and len(entry["phones"]) == 1:
                    phone = fmt_phone(entry["phones"][0])
    return image, basis, email, phone


def matter_url(links: dict, item: dict) -> str | None:
    """The item's own InSite page as the meeting's page lists it for the
    file number. The API's matter id is not InSite's, so none is built."""
    file = item.get("EventItemMatterFile")
    return links.get(file.strip()) if file else None


def title_case(text: str) -> str:
    """'ALD. CHAMBERS JR.' -> 'Ald. Chambers Jr.'; numerals stay as they are."""
    return " ".join(
        w if w.strip(".") in {"II", "III", "IV"}
        else re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), w)
        for w in text.split()
    )


def display_name(record: str, person: dict | None) -> str:
    """The name shown. A record name that already reads as a name stays
    ("Martin J. Weigel"); an abbreviated one ("ALD. A. PRATT") gives way to
    the same record's first and last name, and where the tenant holds no
    person record, to the abbreviation in title case ("Ald. A. Pratt")."""
    record = " ".join(record.split())
    words = record.split()
    if words and words[0].lower() in COURTESY:  # "Ms. Sandra Hoeh-Lyon"
        record = " ".join(words[1:])
    if record != record.upper():
        return record
    first = " ".join(((person or {}).get("PersonFirstName") or "").split())
    last = " ".join(((person or {}).get("PersonLastName") or "").split())
    if first and last:
        full = f"{first} {last}"
        return title_case(full) if full == full.upper() else full
    return title_case(record)


def is_placeholder(record_name: str | None) -> bool:
    """The clerk lists an empty seat as a person named VACANCY."""
    return (record_name or "").strip().upper() == "VACANCY"


def load_merges(tenant: str) -> dict[int, int]:
    """Curated from-id -> into-id for one person the clerk carries under
    two ids; every entry states its basis in local_person_merges.json."""
    if not MERGES_PATH.exists():
        return {}
    entries = json.loads(MERGES_PATH.read_text(encoding="utf-8")).get(tenant, [])
    return {int(e["from"]): int(e["into"]) for e in entries}


def ensure_member(
    conn: sqlite3.Connection, tenant: str, names: dict[int, str], person_id: int,
    record_name: str, record_only: set[int],
) -> None:
    """A person in the votes or roll calls but not the body's office
    records: keep the tenant's own id and name, invent nothing."""
    if person_id in names:
        return
    record_only.add(person_id)
    names[person_id] = display_name(record_name, None)
    conn.execute(
        "INSERT INTO local_members (tenant, person_id, name, record_name,"
        " slug, seat, seat_basis, member_type, is_current)"
        " VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, 0)",
        (tenant, person_id, names[person_id], record_name,
         f"{slugify(names[person_id]) or 'member'}-{person_id}"),
    )


def import_members(
    conn: sqlite3.Connection, spec: dict, office: list[dict], curated: dict,
    profiles: dict, persons: dict,
) -> tuple[dict[int, str], dict[str, int]]:
    """Insert members and terms; returns (person_id -> name, profile counts)."""
    tenant = spec["tenant"]
    today = date.today().isoformat()
    by_person: dict[int, list[dict]] = {}
    for r in office:
        by_person.setdefault(r["OfficeRecordPersonId"], []).append(r)

    names: dict[int, str] = {}
    used_slugs: set[str] = set()
    counts = {"photos": 0, "emails": 0, "phones": 0}
    for person_id, records in sorted(by_person.items()):
        records.sort(key=lambda r: r.get("OfficeRecordStartDate") or "")
        latest = records[-1]
        record_name = latest["OfficeRecordFullName"].strip()
        name = display_name(record_name, persons.get(str(person_id)))
        is_current = any((r.get("OfficeRecordEndDate") or "")[:10] >= today for r in records)
        # the seat: the tenant's own title, else the curated table
        seat = seat_basis = None
        for r in reversed(records):
            m = TITLE_SEAT_RE.match(r.get("OfficeRecordTitle") or "")
            if m:
                seat = int(m.group(1))
                break
        if seat is None and str(person_id) in curated:
            entry = curated[str(person_id)]
            seat, seat_basis = entry["seat"], entry["basis"]
        if seat is not None and not 1 <= seat <= spec["seats"]:
            raise RuntimeError(f"{tenant} person {person_id}: seat {seat} out of range")
        slug = slugify(name) or str(person_id)
        if slug in used_slugs:  # two members sharing a name: id, never a guess
            slug = f"{slug}-{person_id}"
        used_slugs.add(slug)
        image = basis = email = phone = None
        if is_current:
            image, basis, email, phone = attribute_profile(
                spec, name, seat, curated.get(str(person_id), {}).get("name"),
                profiles, persons.get(str(person_id)),
            )
            counts["photos"] += image is not None
            counts["emails"] += email is not None
            counts["phones"] += phone is not None
        conn.execute(
            "INSERT INTO local_members (tenant, person_id, name, record_name, slug, seat,"
            " seat_basis, member_type, is_current, image_url, image_basis, email, phone)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (tenant, person_id, name, record_name, slug, seat, seat_basis,
             latest.get("OfficeRecordMemberType"), int(is_current),
             image, basis, email, phone),
        )
        names[person_id] = name
        for r in records:
            conn.execute(
                "INSERT INTO local_member_terms (tenant, person_id, title, start, end)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    tenant, person_id, r.get("OfficeRecordTitle"),
                    (r.get("OfficeRecordStartDate") or "")[:10],
                    (r.get("OfficeRecordEndDate") or "")[:10] or None,
                ),
            )
    return names, counts


def import_memberships(
    conn: sqlite3.Connection, spec: dict, memberships: dict, departments: list[dict],
    bodies: list[dict],
) -> int:
    """Every body a sitting member currently serves on besides the council
    itself, linked to the tenant's public page for the body. InSite's page
    ids are not the API's body ids, so the link is by exact name against
    the tenant's own Departments listing; a name listed twice links nowhere.
    Bodies of a legislative-body type are the council itself and the
    clerk's notice pseudo-body (West Allis files "Notice of Informal
    Gathering" as one); neither is an assignment."""
    tenant = spec["tenant"]
    today = date.today().isoformat()
    seen: dict[str, str | None] = {}
    for d in departments:
        key = d["name"].strip().lower()
        seen[key] = None if key in seen else d["url"]
    legislative = {
        b["BodyId"] for b in bodies if "Legislative Body" in (b.get("BodyTypeName") or "")
    }
    n = 0
    for pid, records in memberships.items():
        for r in records:
            if (r.get("OfficeRecordBodyName") == spec["body_name"]
                    or r.get("OfficeRecordBodyId") in legislative):
                continue
            if (r.get("OfficeRecordEndDate") or "")[:10] < today:
                continue
            body_name = r["OfficeRecordBodyName"]
            conn.execute(
                "INSERT INTO local_memberships (tenant, person_id, body_id, body_name,"
                " role, start, end, body_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant, int(pid), r["OfficeRecordBodyId"], body_name,
                    r.get("OfficeRecordTitle") or r.get("OfficeRecordMemberType"),
                    (r.get("OfficeRecordStartDate") or "")[:10] or None,
                    (r.get("OfficeRecordEndDate") or "")[:10] or None,
                    seen.get(body_name.strip().lower()),
                ),
            )
            n += 1
    return n


def _optional_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def import_tenant(conn: sqlite3.Connection, spec: dict, local_dir: Path) -> dict:
    tenant = spec["tenant"]
    src = local_dir / tenant
    office = json.loads((src / "officerecords.json").read_text(encoding="utf-8"))
    vote_types = json.loads((src / "votetypes.json").read_text(encoding="utf-8"))
    merges = load_merges(tenant)
    canon = lambda pid: merges.get(pid, pid)  # noqa: E731 - one-liner by design
    # a placeholder "member" the clerk uses for an empty seat is no person
    office = [
        {**r, "OfficeRecordPersonId": canon(r["OfficeRecordPersonId"])}
        for r in office if not is_placeholder(r.get("OfficeRecordFullName"))
    ]
    curated = load_curation(SEATS_PATH).get(tenant, {})
    profiles = _optional_json(local_dir / "profiles.json", {})
    if profiles.get(tenant, {}).get("seats"):
        profiles[tenant]["seats"] = strip_template_phones(profiles[tenant]["seats"])
    persons = _optional_json(src / "persons.json", {})
    memberships = _optional_json(src / "memberships.json", {})
    for old_id, new_id in merges.items():
        persons.setdefault(str(new_id), persons.pop(str(old_id), None))
        memberships.setdefault(str(new_id), []).extend(memberships.pop(str(old_id), []))
    departments = _optional_json(src / "departments.json", [])
    api_bodies = _optional_json(src / "bodies.json", [])

    conn.execute(
        "INSERT INTO local_bodies (tenant, slug, city, name, insite_url, seats)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (tenant, spec["slug"], spec["city"], spec["body_display"],
         spec["insite"], spec["seats"]),
    )
    for vt in vote_types:
        conn.execute(
            "INSERT INTO local_vote_types (tenant, value) VALUES (?, ?)",
            (tenant, vt["VoteTypeName"]),
        )
    names, profile_counts = import_members(conn, spec, office, curated, profiles, persons)
    membership_rows = import_memberships(conn, spec, memberships, departments, api_bodies)
    # meetings not held yet: date, time and place for the calendar
    n_upcoming = 0
    for e in _optional_json(src / "upcoming.json", []):
        if not e.get("EventInSiteURL"):
            continue
        if "INFORMAL GATHERING" in (e.get("EventComment") or "").upper():
            continue  # the clerk's open-meetings notice, not a sitting
        conn.execute(
            "INSERT OR REPLACE INTO local_upcoming (tenant, event_id, date, time,"
            " location, insite_url) VALUES (?, ?, ?, ?, ?, ?)",
            (tenant, e["EventId"], e["EventDate"][:10], e.get("EventTime"),
             " ".join((e.get("EventLocation") or "").split()) or None,
             e["EventInSiteURL"]),
        )
        n_upcoming += 1

    events = actions = votes = unvalued = duplicated = conflicting = 0
    rollcalls = unvalued_rollcalls = notices = 0
    vote_only_members: set[int] = set()
    voter_names: dict[int, str] = {}
    for path in sorted(src.glob("event_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        event, items, links = data["event"], data["items"], data.get("links", {})
        if not items:
            continue  # duplicate or empty event records carry nothing
        if (not any(i.get("EventItemActionName") for i in items)
                and not data.get("rollcalls")):
            # nothing acted and no roll called: the clerk's notice of an
            # informal gathering, or a sitting that never happened
            notices += 1
            continue
        if not event.get("EventInSiteURL"):
            raise RuntimeError(f"{tenant} event {event['EventId']}: no InSite URL")
        conn.execute(
            "INSERT INTO local_events (tenant, event_id, date, minutes_status,"
            " insite_url) VALUES (?, ?, ?, ?, ?)",
            (tenant, event["EventId"], event["EventDate"][:10],
             event.get("EventMinutesStatusName"), event["EventInSiteURL"]),
        )
        events += 1
        for item in items:
            if not item.get("EventItemActionName"):
                continue
            conn.execute(
                "INSERT INTO local_actions (tenant, event_item_id, event_id,"
                " matter_id, matter_file, matter_type, matter_status, title,"
                " action, passed, agenda_number, matter_url, mover_id, seconder_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    tenant, item["EventItemId"], event["EventId"],
                    item.get("EventItemMatterId"), item.get("EventItemMatterFile"),
                    item.get("EventItemMatterType"), item.get("EventItemMatterStatus"),
                    item.get("EventItemTitle"), item["EventItemActionName"],
                    item.get("EventItemPassedFlag"), item.get("EventItemAgendaNumber"),
                    matter_url(links, item),
                    item.get("EventItemMoverId"), item.get("EventItemSeconderId"),
                ),
            )
            actions += 1
            # One row per (item, person). The source occasionally lists a
            # voter twice: the same value twice is one fact, kept once; two
            # different values is the record disagreeing with itself, and no
            # position is attributed. Both are counted, neither is guessed.
            positions: dict[int, str] = {}
            conflicted: set[int] = set()
            for v in data["votes"].get(str(item["EventItemId"]), []):
                if not v.get("VoteValueName"):
                    # the clerk listed the voter but recorded no position:
                    # not a vote, so nothing to attribute; counted, never guessed
                    unvalued += 1
                    continue
                pid, value = canon(v["VotePersonId"]), v["VoteValueName"]
                if is_placeholder(v.get("VotePersonName")) or value == "VACANCY":
                    continue  # an empty seat casts nothing
                if pid in positions:
                    if positions[pid] == value:
                        duplicated += 1
                    else:
                        conflicted.add(pid)
                    continue
                positions[pid] = value
                voter_names[pid] = v["VotePersonName"].strip()
            if conflicted & set(merges.values()):
                raise RuntimeError(
                    f"{tenant} item {item['EventItemId']}: a merged person voted under"
                    " both ids; revisit local_person_merges.json"
                )
            conflicting += len(conflicted)
            for person_id, value in positions.items():
                if person_id in conflicted:
                    continue
                ensure_member(conn, tenant, names, person_id, voter_names[person_id],
                              vote_only_members)
                conn.execute(
                    "INSERT INTO local_votes (tenant, event_item_id, person_id, value)"
                    " VALUES (?, ?, ?, ?)",
                    (tenant, item["EventItemId"], person_id, value),
                )
                votes += 1
        # attendance, under the same rules as votes: a row with no value is
        # not a fact, a person listed twice with one value is one fact, and
        # two values is the record disagreeing with itself
        for item_id, rows in data.get("rollcalls", {}).items():
            attendance: dict[int, str] = {}
            disputed: set[int] = set()
            for r in rows:
                value = r.get("RollCallValueName")
                if not value:
                    unvalued_rollcalls += 1
                    continue
                pid = canon(r["RollCallPersonId"])
                if is_placeholder(r.get("RollCallPersonName")) or value == "VACANCY":
                    continue  # an empty seat is not anyone's attendance
                if pid in attendance and attendance[pid] != value:
                    disputed.add(pid)
                attendance.setdefault(pid, value)
                voter_names.setdefault(pid, (r.get("RollCallPersonName") or "").strip()
                                       or str(pid))
            for pid, value in attendance.items():
                if pid in disputed:
                    continue
                ensure_member(conn, tenant, names, pid, voter_names[pid], vote_only_members)
                conn.execute(
                    "INSERT INTO local_rollcalls (tenant, event_item_id, event_id,"
                    " person_id, value) VALUES (?, ?, ?, ?, ?)",
                    (tenant, int(item_id), event["EventId"], pid, value),
                )
                rollcalls += 1
    # Office records are incomplete for earlier years (Milwaukee's carry no
    # dates for several long-serving members), so a vote outside its
    # member's recorded dates is reported, not gated: the vote itself is
    # the tenant's record, the term table is the weaker of the two.
    outside = conn.execute(
        """SELECT COUNT(*) FROM local_votes v
           JOIN local_actions a ON a.tenant = v.tenant AND a.event_item_id = v.event_item_id
           JOIN local_events e ON e.tenant = a.tenant AND e.event_id = a.event_id
           WHERE v.tenant = ? AND NOT EXISTS (
             SELECT 1 FROM local_member_terms t WHERE t.tenant = v.tenant
             AND t.person_id = v.person_id AND e.date >= t.start
             AND e.date <= COALESCE(t.end, '9999'))""",
        (tenant,),
    ).fetchone()[0]
    return {
        "events": events, "actions": actions, "votes": votes,
        "rollcalls": rollcalls, "unvalued_rollcalls": unvalued_rollcalls,
        "upcoming": n_upcoming, "notices": notices,
        "members": len(names), "vote_only": len(vote_only_members),
        "unvalued": unvalued, "outside_terms": outside,
        "duplicated": duplicated, "conflicting": conflicting,
        "memberships": membership_rows, **profile_counts,
    }


def run(local_dir: Path, db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    with conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")  # noqa: S608 - fixed list above
        conn.execute("DELETE FROM meta WHERE key LIKE 'local_%'")
        for spec in TENANTS:
            stats = import_tenant(conn, spec, local_dir)
            print(
                f"{spec['tenant']}: {stats['events']} meetings, {stats['actions']}"
                f" actions, {stats['votes']} votes, {stats['members']} members"
                + (f" ({stats['vote_only']} known only from vote records)"
                   if stats["vote_only"] else "")
            )
            print(f"  sitting members: {stats['photos']} portraits, {stats['emails']} emails,"
                  f" {stats['phones']} phones attributed; {stats['memberships']} committee seats")
            print(f"  {stats['upcoming']} upcoming meetings kept for the calendar")
            if stats["notices"]:
                print(f"  {stats['notices']} notice or never-held records skipped"
                      " (no action, no roll call)")
            print(f"  {stats['rollcalls']} attendance rows from the clerk's roll calls"
                  + (f"; {stats['unvalued_rollcalls']} listed no value: skipped"
                     if stats["unvalued_rollcalls"] else ""))
            if stats["unvalued"]:
                print(f"  {stats['unvalued']} vote rows carried no recorded value: skipped")
            if stats["duplicated"]:
                print(f"  {stats['duplicated']} rows repeated a member's recorded value: kept once")
            if stats["conflicting"]:
                print(f"  {stats['conflicting']} member positions recorded two ways on one item:"
                      " no position attributed")
            if stats["outside_terms"]:
                print(f"  {stats['outside_terms']} votes fall outside the member's recorded"
                      " office dates (term records incomplete; reported, not gated)")
        through = conn.execute("SELECT MAX(date) FROM local_events").fetchone()[0]
        if through:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('local_votes_through', ?)",
                (through,),
            )
    conn.close()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("local_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    run(ns.local_dir, ns.db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
