"""Local council import: seats, slugs, and votes keyed by the tenant's ids."""

import json
from pathlib import Path

from importer.import_local import run

TODAY_END = "2028-04-11T00:00:00"


def office(person_id: int, name: str, title: str, member_type: str = "Member",
           start: str = "2024-04-16T00:00:00", end: str = TODAY_END) -> dict:
    return {
        "OfficeRecordPersonId": person_id, "OfficeRecordFullName": name,
        "OfficeRecordTitle": title, "OfficeRecordMemberType": member_type,
        "OfficeRecordStartDate": start, "OfficeRecordEndDate": end,
    }


def event_file(event_id: int, date: str, items: list[dict], votes: dict,
               links: dict | None = None, rollcalls: dict | None = None) -> dict:
    return {
        "event": {
            "EventId": event_id, "EventDate": f"{date}T09:00:00",
            "EventMinutesStatusName": "Final",
            "EventInSiteURL": f"https://x.legistar.com/MeetingDetail.aspx?ID={event_id}",
        },
        "items": items,
        "votes": votes,
        "links": links or {},
        "rollcalls": rollcalls or {},
    }


def item(item_id: int, action: str = "PASSED", **extra) -> dict:
    return {"EventItemId": item_id, "EventItemActionName": action,
            "EventItemTitle": "A test item", **extra}


def vote(person_id: int, name: str, value: str = "Aye") -> dict:
    return {"VotePersonId": person_id, "VotePersonName": name, "VoteValueName": value}


def write_tenant(root: Path, tenant: str, officerecords, events) -> None:
    d = root / tenant
    d.mkdir(parents=True)
    (d / "officerecords.json").write_text(json.dumps(officerecords), encoding="utf-8")
    (d / "votetypes.json").write_text(
        json.dumps([{"VoteTypeName": v} for v in
                    ("Aye", "No", "Abstain", "Excused", "Non-Voting", "Present")]),
        encoding="utf-8",
    )
    for e in events:
        (d / f"event_{e['event']['EventId']}.json").write_text(
            json.dumps(e), encoding="utf-8"
        )


def build(tmp_path: Path, make_db, milwaukee_events=(), westallis_events=(),
          milwaukee_office=(), westallis_office=(), profiles=None, persons=None,
          memberships=None, bodies=None, upcoming=None, api_bodies=None):
    db = tmp_path / "wi.sqlite"
    make_db(db).close()
    local = tmp_path / "local"
    write_tenant(local, "milwaukee", list(milwaukee_office), list(milwaukee_events))
    write_tenant(local, "westalliswi", list(westallis_office), list(westallis_events))
    if profiles is not None:
        (local / "profiles.json").write_text(json.dumps(profiles), encoding="utf-8")
    for tenant, data in (persons or {}).items():
        (local / tenant / "persons.json").write_text(json.dumps(data), encoding="utf-8")
    for tenant, data in (memberships or {}).items():
        (local / tenant / "memberships.json").write_text(json.dumps(data), encoding="utf-8")
    for tenant, data in (bodies or {}).items():
        (local / tenant / "departments.json").write_text(json.dumps(data), encoding="utf-8")
    for tenant, data in (upcoming or {}).items():
        (local / tenant / "upcoming.json").write_text(json.dumps(data), encoding="utf-8")
    for tenant, data in (api_bodies or {}).items():
        (local / tenant / "bodies.json").write_text(json.dumps(data), encoding="utf-8")
    run(local, db)
    import sqlite3
    return sqlite3.connect(db)


def test_milwaukee_seat_parses_from_the_title(tmp_path, make_db) -> None:
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(9, "ALD. TEST", "3rd District")])
    row = conn.execute(
        "SELECT seat, member_type, is_current, slug FROM local_members"
        " WHERE tenant='milwaukee' AND person_id=9").fetchone()
    assert row == (3, "Member", 1, "ald-test")


def test_west_allis_seat_comes_from_the_curated_table(tmp_path, make_db) -> None:
    # person 117 is Kevin Haass, District 5 per importer/local_seats.json
    conn = build(tmp_path, make_db,
                 westallis_office=[office(117, "Kevin Haass", "Ald.")])
    seat, basis = conn.execute(
        "SELECT seat, seat_basis FROM local_members"
        " WHERE tenant='westalliswi' AND person_id=117").fetchone()
    assert seat == 5
    assert "westalliswi.gov" in basis


def test_presiding_officer_keeps_no_seat(tmp_path, make_db) -> None:
    conn = build(tmp_path, make_db,
                 westallis_office=[office(103, "Dan Devine", "Mayor", "Chair")])
    row = conn.execute(
        "SELECT seat, member_type FROM local_members WHERE person_id=103").fetchone()
    assert row == (None, "Chair")


def test_votes_join_on_the_tenants_person_id(tmp_path, make_db) -> None:
    page = "https://milwaukee.legistar.com/LegislationDetail.aspx?ID=4913721&GUID=C91F"
    ev = event_file(100, "2026-07-31",
                    [item(7, "PASSED", EventItemMatterId=55,
                          EventItemMatterGuid="ABC", EventItemMatterFile="26-1"),
                     item(9, "PASSED", EventItemMatterId=56,
                          EventItemMatterGuid="DEF", EventItemMatterFile="26-2"),
                     {"EventItemId": 8, "EventItemActionName": None}],
                    {"7": [vote(9, "ALD. TEST", "Aye"), vote(10, "ALD. OTHER", "No")],
                     "9": [vote(9, "ALD. TEST", "Aye")]},
                    links={"26-1": page})
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(9, "ALD. TEST", "1st District")],
                 milwaukee_events=[ev])
    votes = conn.execute(
        "SELECT person_id, value FROM local_votes WHERE event_item_id=7 ORDER BY person_id"
    ).fetchall()
    assert votes == [(9, "Aye"), (10, "No")]
    # person 10 was known only from the vote record: kept, invented nothing
    name, seat, current = conn.execute(
        "SELECT name, seat, is_current FROM local_members WHERE person_id=10").fetchone()
    assert (name, seat, current) == ("Ald. Other", None, 0)
    # unactioned items carry no action row; an item links only to the page
    # the meeting's own page lists for its file number (the API's matter
    # id is not InSite's), and an unlisted file links nowhere
    assert conn.execute(
        "SELECT event_item_id, matter_url FROM local_actions ORDER BY event_item_id"
    ).fetchall() == [(7, page), (9, None)]


def test_a_voter_with_no_recorded_value_is_not_a_vote(tmp_path, make_db) -> None:
    ev = event_file(100, "2026-07-31", [item(7)],
                    {"7": [vote(9, "A", "Aye"), {"VotePersonId": 9, "VotePersonName": "A",
                                                 "VoteValueName": None}]})
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(9, "A", "1st District")],
                 milwaukee_events=[ev])
    assert conn.execute("SELECT COUNT(*) FROM local_votes").fetchone()[0] == 1


def test_repeated_rows_keep_one_and_contradictions_keep_none(tmp_path, make_db) -> None:
    ev = event_file(100, "2026-07-31", [item(7)], {"7": [
        vote(9, "A", "Aye"), vote(9, "A", "Aye"),          # one fact, twice
        vote(10, "B", "Aye"), vote(10, "B", "Excused"),    # the record disagrees
        vote(11, "C", "No"),
    ]})
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(9, "A", "1st District"),
                                   office(10, "B", "2nd District"),
                                   office(11, "C", "3rd District")],
                 milwaukee_events=[ev])
    rows = conn.execute(
        "SELECT person_id, value FROM local_votes ORDER BY person_id").fetchall()
    assert rows == [(9, "Aye"), (11, "No")]


def test_shared_names_get_distinct_slugs(tmp_path, make_db) -> None:
    conn = build(tmp_path, make_db, milwaukee_office=[
        office(1, "Pat Jones", "1st District"),
        office(2, "Pat Jones", "2nd District"),
    ])
    slugs = {s for (s,) in conn.execute("SELECT slug FROM local_members")}
    assert slugs == {"pat-jones", "pat-jones-2"}


def test_meta_carries_the_local_data_edge(tmp_path, make_db) -> None:
    ev = event_file(100, "2026-07-31", [item(7)], {"7": [vote(9, "A", "Aye")]})
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(9, "A", "1st District")],
                 milwaukee_events=[ev])
    assert conn.execute(
        "SELECT value FROM meta WHERE key='local_votes_through'").fetchone()[0] == "2026-07-31"


def test_milwaukee_portrait_and_contacts_attach_only_by_exact_rule(tmp_path, make_db) -> None:
    profiles = {"milwaukee": {"seats": {"3": {
        "page": "https://city.milwaukee.gov/CommonCouncil/Council-Members/District3",
        "photos": [
            {"src": "https://city.milwaukee.gov/x/Brower.jpg",
             "alt": "Photo of Alex Brower District 3 Alderman"},
            {"src": "https://city.milwaukee.gov/x/Other.jpg",
             "alt": "Photo of District 4 Alderman"},
        ],
        "mailto": ["Alex.Brower@milwaukee.gov", "staffer@milwaukee.gov"],
        "tel": ["4142862489"],
    }}}}
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(3906, "ALD. BROWER", "3rd District")],
                 profiles=profiles)
    row = conn.execute(
        "SELECT image_url, email, phone FROM local_members WHERE person_id=3906").fetchone()
    assert row == ("https://city.milwaukee.gov/x/Brower.jpg", "Alex.Brower@milwaukee.gov",
                   "414-286-2489")


def test_a_phone_on_every_district_page_is_the_templates(tmp_path, make_db) -> None:
    page = {"page": "p", "mailto": [], "photos": []}
    profiles = {"milwaukee": {"seats": {
        "3": page | {"tel": ["4142862489"]},
        "5": page | {"tel": ["4142862489", "4143012195"]},
    }}}
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(3906, "ALD. BROWER", "3rd District"),
                                   office(3693, "ALD. WESTMORELAND", "5th District")],
                 profiles=profiles)
    phones = dict(conn.execute("SELECT person_id, phone FROM local_members").fetchall())
    assert phones == {3906: None, 3693: "414-301-2195"}


def test_two_matching_headshots_attach_none(tmp_path, make_db) -> None:
    profiles = {"milwaukee": {"seats": {"3": {
        "page": "p", "mailto": [], "tel": ["4142862489", "4142860000"],
        "photos": [{"src": "a.jpg", "alt": "Photo of District 3 A"},
                   {"src": "b.jpg", "alt": "Photo of District 3 B"}],
    }}}}
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(3906, "ALD. BROWER", "3rd District")],
                 profiles=profiles)
    row = conn.execute(
        "SELECT image_url, phone FROM local_members WHERE person_id=3906").fetchone()
    assert row == (None, None)


def test_west_allis_portrait_by_heading_and_email_from_the_record(tmp_path, make_db) -> None:
    profiles = {"westalliswi": {"districts": {"5": {
        "page": "https://www.westalliswi.gov/page/district-five",
        "entries": [
            {"heading": "Kevin Haass - Council President", "image": "https://cdn/haass.jpg",
             "emails": [], "phones": ["4143028220"]},
            {"heading": "Martin J. Weigel", "image": "https://cdn/weigel.jpg",
             "emails": [], "phones": []},
        ],
    }}}}
    persons = {"westalliswi": {"117": {"PersonEmail": "khaass@westalliswi.gov", "PersonPhone": ""}}}
    conn = build(tmp_path, make_db,
                 westallis_office=[office(117, "Kevin Haass", "Ald.")],
                 profiles=profiles, persons=persons)
    assert conn.execute(
        "SELECT image_url, email, phone FROM local_members WHERE person_id=117").fetchone() == (
        "https://cdn/haass.jpg", "khaass@westalliswi.gov", "414-302-8220")


def test_memberships_skip_the_council_and_past_seats(tmp_path, make_db) -> None:
    memberships = {"milwaukee": {"3906": [
        office(3906, "ALD. BROWER", "3rd District")
        | {"OfficeRecordBodyName": "COMMON COUNCIL", "OfficeRecordBodyId": 1},
        office(3906, "ALD. BROWER", "Member")
        | {"OfficeRecordBodyName": "LICENSES COMMITTEE", "OfficeRecordBodyId": 10},
        office(3906, "ALD. BROWER", "Member", end="2020-01-01T00:00:00")
        | {"OfficeRecordBodyName": "OLD BOARD", "OfficeRecordBodyId": 99},
    ]}}
    # InSite's page ids differ from the API's; the link is by exact body name
    bodies = {"milwaukee": [
        {"name": "LICENSES COMMITTEE",
         "url": "https://milwaukee.legistar.com/DepartmentDetail.aspx?ID=12345&GUID=G10"},
    ]}
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(3906, "ALD. BROWER", "3rd District")],
                 memberships=memberships, bodies=bodies)
    rows = conn.execute("SELECT body_name, role, body_url FROM local_memberships").fetchall()
    assert rows == [("LICENSES COMMITTEE", "Member",
                     "https://milwaukee.legistar.com/DepartmentDetail.aspx?ID=12345&GUID=G10")]


def test_names_come_from_the_person_record_where_the_office_record_abbreviates(
    tmp_path, make_db,
) -> None:
    conn = build(
        tmp_path, make_db,
        milwaukee_office=[office(9, "ALD. CHAMBERS JR.", "2nd District"),
                          office(10, "ALD. O'DONNELL", "3rd District")],
        westallis_office=[office(117, "Kevin Haass", "Ald.")],
        persons={"milwaukee": {"9": {"PersonFirstName": "Mark",
                                     "PersonLastName": "Chambers Jr."}}},
    )
    rows = dict(conn.execute(
        "SELECT person_id, name || '|' || slug || '|' || record_name FROM local_members"
    ).fetchall())
    assert rows[9] == "Mark Chambers Jr.|mark-chambers-jr|ALD. CHAMBERS JR."
    # no person record: the abbreviation itself, cased, never a guessed first name
    assert rows[10] == "Ald. O'Donnell|ald-o-donnell|ALD. O'DONNELL"
    # a record name that already reads as a name is kept as the tenant wrote it
    assert rows[117] == "Kevin Haass|kevin-haass|Kevin Haass"


def test_roll_calls_record_attendance_and_movers_are_kept(tmp_path, make_db) -> None:
    ev = event_file(
        100, "2026-07-31",
        [item(7, "PASSED", EventItemMoverId=9, EventItemSeconderId=12),
         {"EventItemId": 5, "EventItemActionName": None, "EventItemRollCallFlag": 1}],
        {"7": [vote(9, "A", "Aye")]},
        rollcalls={"5": [
            {"RollCallPersonId": 9, "RollCallPersonName": "A", "RollCallValueName": "Present"},
            {"RollCallPersonId": 12, "RollCallPersonName": "ALD. LATE",
             "RollCallValueName": "Excused"},
            {"RollCallPersonId": 13, "RollCallPersonName": "C", "RollCallValueName": None},
        ]},
    )
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(9, "A", "1st District")], milwaukee_events=[ev])
    assert conn.execute(
        "SELECT person_id, value FROM local_rollcalls ORDER BY person_id"
    ).fetchall() == [(9, "Present"), (12, "Excused")]
    # known only from the roll call: the tenant's own id and name, not sitting
    assert conn.execute(
        "SELECT name, record_name, is_current FROM local_members WHERE person_id=12"
    ).fetchone() == ("Ald. Late", "ALD. LATE", 0)
    assert conn.execute(
        "SELECT mover_id, seconder_id FROM local_actions WHERE event_item_id=7"
    ).fetchone() == (9, 12)


def test_upcoming_meetings_land_on_the_calendar_table(tmp_path, make_db) -> None:
    conn = build(tmp_path, make_db, upcoming={"westalliswi": [
        {"EventId": 900, "EventDate": "2026-09-15T00:00:00", "EventTime": "7:00 PM",
         "EventLocation": "City Hall,  Common Council Chambers\r\n7525 W. Greenfield Ave.",
         "EventInSiteURL": "https://westalliswi.legistar.com/MeetingDetail.aspx?ID=900"},
        # no public page listed: not shown rather than linked nowhere
        {"EventId": 901, "EventDate": "2026-10-06T00:00:00", "EventInSiteURL": None},
    ]})
    assert conn.execute(
        "SELECT event_id, date, time, location FROM local_upcoming"
    ).fetchall() == [(900, "2026-09-15", "7:00 PM",
                      "City Hall, Common Council Chambers 7525 W. Greenfield Ave.")]


def test_notice_records_are_not_meetings_or_committees(tmp_path, make_db) -> None:
    notice = event_file(300, "2026-05-04", [{"EventItemId": 9, "EventItemActionName": None}], {})
    held = event_file(301, "2026-05-05", [item(7)], {"7": [vote(9, "A", "Aye")]})
    conn = build(
        tmp_path, make_db,
        westallis_office=[office(117, "Kevin Haass", "Ald.")],
        westallis_events=[notice, held],
        memberships={"westalliswi": {"117": [
            office(117, "Kevin Haass", "Ald.") | {"OfficeRecordBodyName": "Common Council",
                                                  "OfficeRecordBodyId": 1},
            office(117, "Kevin Haass", "Ald.") | {"OfficeRecordBodyName":
                                                  "Notice of Informal Gathering",
                                                  "OfficeRecordBodyId": 77},
            office(117, "Kevin Haass", "Member") | {"OfficeRecordBodyName":
                                                    "Events Committee",
                                                    "OfficeRecordBodyId": 78},
        ]}},
        api_bodies={"westalliswi": [
            {"BodyId": 1, "BodyName": "Common Council",
             "BodyTypeName": "Primary Legislative Body"},
            {"BodyId": 77, "BodyName": "Notice of Informal Gathering",
             "BodyTypeName": "Primary Legislative Body"},
            {"BodyId": 78, "BodyName": "Events Committee",
             "BodyTypeName": "Standing Committee"},
        ]},
        upcoming={"westalliswi": [
            {"EventId": 900, "EventDate": "2026-10-06T00:00:00",
             "EventComment": "NOTICE OF INFORMAL GATHERING",
             "EventInSiteURL": "https://x.legistar.com/MeetingDetail.aspx?ID=900"},
        ]},
    )
    # the notice event is not a meeting; the held one is
    assert [r[0] for r in conn.execute(
        "SELECT event_id FROM local_events WHERE tenant='westalliswi'").fetchall()] == [301]
    # the notice pseudo-body is not an assignment; the committee is
    assert conn.execute(
        "SELECT body_name FROM local_memberships WHERE tenant='westalliswi'"
    ).fetchall() == [("Events Committee",)]
    # a future notice is not an upcoming meeting
    assert conn.execute("SELECT COUNT(*) FROM local_upcoming").fetchone()[0] == 0
