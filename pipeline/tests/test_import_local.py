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


def event_file(event_id: int, date: str, items: list[dict], votes: dict) -> dict:
    return {
        "event": {
            "EventId": event_id, "EventDate": f"{date}T09:00:00",
            "EventMinutesStatusName": "Final",
            "EventInSiteURL": f"https://x.legistar.com/MeetingDetail.aspx?ID={event_id}",
        },
        "items": items,
        "votes": votes,
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
                    ("Aye", "No", "Abstain", "Excused", "Non-Voting")]),
        encoding="utf-8",
    )
    for e in events:
        (d / f"event_{e['event']['EventId']}.json").write_text(
            json.dumps(e), encoding="utf-8"
        )


def build(tmp_path: Path, make_db, milwaukee_events=(), westallis_events=(),
          milwaukee_office=(), westallis_office=()):
    db = tmp_path / "wi.sqlite"
    make_db(db).close()
    local = tmp_path / "local"
    write_tenant(local, "milwaukee", list(milwaukee_office), list(milwaukee_events))
    write_tenant(local, "westalliswi", list(westallis_office), list(westallis_events))
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
    ev = event_file(100, "2026-07-31",
                    [item(7, "PASSED", EventItemMatterId=55,
                          EventItemMatterGuid="ABC", EventItemMatterFile="26-1"),
                     {"EventItemId": 8, "EventItemActionName": None}],
                    {"7": [vote(9, "ALD. TEST", "Aye"), vote(10, "ALD. OTHER", "No")]})
    conn = build(tmp_path, make_db,
                 milwaukee_office=[office(9, "ALD. TEST", "1st District")],
                 milwaukee_events=[ev])
    votes = conn.execute(
        "SELECT person_id, value FROM local_votes ORDER BY person_id").fetchall()
    assert votes == [(9, "Aye"), (10, "No")]
    # person 10 was known only from the vote record: kept, invented nothing
    name, seat, current = conn.execute(
        "SELECT name, seat, is_current FROM local_members WHERE person_id=10").fetchone()
    assert (name, seat, current) == ("ALD. OTHER", None, 0)
    # unactioned items carry no action row; the matter link is the clerk's page
    assert conn.execute("SELECT COUNT(*) FROM local_actions").fetchone()[0] == 1
    url = conn.execute("SELECT matter_url FROM local_actions").fetchone()[0]
    assert url == "https://milwaukee.legistar.com/LegislationDetail.aspx?ID=55&GUID=ABC"


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
