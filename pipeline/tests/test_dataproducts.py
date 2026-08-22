"""Data products: correct shapes, and legiscan rows never escape."""

import json
import sqlite3
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from dataproducts import queries
from dataproducts.api import build_api
from dataproducts.bulk import build_bulk
from dataproducts.feeds import build_feeds
from dataproducts.ical import build_ical


@pytest.fixture()
def db_path(tmp_path: Path, make_db) -> Path:
    path = tmp_path / "wi.sqlite"
    conn = make_db(path)
    conn.executescript(
        """
        INSERT INTO sessions (id, identifier, name) VALUES ('2025', '2025', '2025-26');
        INSERT INTO people (id, name, party, chamber, district)
          VALUES ('ocd-person/p1', 'Ann Example', 'Independent', 'lower', 15);
        INSERT INTO bills (id, session_id, identifier, title, status,
                           died_without_hearing, source)
          VALUES ('2025-ab656', '2025', 'AB 656', 'Child marriage ban',
                  'failed_sjr1', 1, 'openstates');
        INSERT INTO bills (id, session_id, identifier, title, source)
          VALUES ('2025-ab9999', '2025', 'AB 9999', 'SECRET LEGISCAN BILL', 'legiscan');
        INSERT INTO actions (id, bill_id, date, description, classification)
          VALUES ('a1', '2025-ab656', '2025-06-01', 'Introduced', 'introduction');
        INSERT INTO actions (id, bill_id, date, description, classification)
          VALUES ('a2', '2025-ab9999', '2025-06-01', 'legiscan action', '');
        INSERT INTO sponsorships (bill_id, person_id, name, classification, is_primary)
          VALUES ('2025-ab656', 'ocd-person/p1', 'Example', 'primary', 1);
        INSERT INTO vote_events (id, bill_id, date, chamber, motion, result,
                                 yes_count, no_count, nv_count, source)
          VALUES ('2025-v1', '2025-ab656', '2025-06-02', 'lower', 'Passage',
                  'pass', 1, 0, 0, 'openstates');
        INSERT INTO vote_events (id, bill_id, date, motion, source)
          VALUES ('2025-v9', '2025-ab9999', '2025-06-02', 'legiscan vote', 'legiscan');
        INSERT INTO vote_records (vote_event_id, person_id, option)
          VALUES ('2025-v1', 'ocd-person/p1', 'yes');
        INSERT INTO vote_records (vote_event_id, person_id, option)
          VALUES ('2025-v9', 'ocd-person/p1', 'yes');
        INSERT INTO committees (id, chamber, name, chair_person_id)
          VALUES ('c1', 'lower', 'Children and Families', 'ocd-person/p1');
        INSERT INTO hearings (id, committee_id, date, time, location,
                              agenda_bill_ids_json, source_url)
          VALUES ('h1', 'c1', '2025-06-03', '10:00', '417 North',
                  '["AB 656"]', 'https://example.gov/notice');
        INSERT INTO elections (person_id, cycle_year, office, district, on_ballot,
                               is_incumbent, opponents_json, source)
          VALUES ('ocd-person/p1', 2026, 'State Assembly', 15, 1, 1,
                  '[{"name": "Bob Rival", "party": "Test", "ballot_status": "Approve"}]',
                  'wec');
        INSERT INTO meta (key, value) VALUES ('data_through', '2025-06-03');
        """
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def built(db_path: Path, tmp_path: Path) -> Path:
    out = tmp_path / "public"
    conn = queries.connect(db_path)
    build_api(conn, out)
    build_feeds(conn, out)
    build_ical(conn, out)
    build_bulk(conn, db_path, tmp_path / "exports")
    conn.close()
    return tmp_path


def test_bill_json_full_shape(built: Path) -> None:
    payload = json.loads(
        (built / "public" / "api" / "v1" / "bills" / "2025" / "ab656.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["identifier"] == "AB 656"
    assert payload["died_without_hearing"] == 1
    assert payload["sponsors"][0]["person_id"] == "ocd-person/p1"
    assert payload["actions"][0]["description"] == "Introduced"
    assert payload["votes"][0]["records"][0]["option"] == "yes"


def test_legislator_json_shape(built: Path) -> None:
    payload = json.loads(
        (built / "public" / "api" / "v1" / "legislators" / "p1.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["election"]["cycle_year"] == 2026
    assert payload["election"]["opponents"][0]["name"] == "Bob Rival"
    assert payload["votes"][0]["option"] == "yes"
    assert payload["sponsorships"][0]["bill_id"] == "2025-ab656"


def test_no_legiscan_anywhere(built: Path) -> None:
    hits = []
    for path in built.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".xml", ".ics", ".csv"):
            if "LEGISCAN" in path.read_text(encoding="utf-8", errors="replace").upper():
                hits.append(str(path))
    assert hits == [], f"legiscan content escaped into: {hits}"
    assert not (built / "public" / "api" / "v1" / "bills" / "2025" / "ab9999.json").exists()
    assert not (built / "public" / "api" / "v1" / "votes" / "2025-v9.json").exists()


def test_filtered_sqlite_has_no_legiscan_rows(built: Path) -> None:
    conn = sqlite3.connect(built / "exports" / "wi-filtered.sqlite")
    for table in ("bills", "vote_events"):
        count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE source = 'legiscan'"  # noqa: S608
        ).fetchone()[0]
        assert count == 0, table
    # the exportable bill is still there
    assert conn.execute("SELECT COUNT(*) FROM bills").fetchone()[0] == 1
    conn.close()


def test_feeds_are_valid_atom(built: Path) -> None:
    feed = built / "public" / "feeds" / "bills" / "2025-ab656.xml"
    root = ET.parse(feed).getroot()
    assert root.tag == "{http://www.w3.org/2005/Atom}feed"
    ns = {"a": "http://www.w3.org/2005/Atom"}
    assert root.find("a:id", ns) is not None
    assert root.find("a:updated", ns) is not None
    entries = root.findall("a:entry", ns)
    assert entries and entries[0].find("a:id", ns) is not None
    assert (built / "public" / "feeds" / "weekly.xml").exists()


def test_ical_structure(built: Path) -> None:
    text = (built / "public" / "calendar" / "hearings.ics").read_text(encoding="utf-8")
    assert text.startswith("BEGIN:VCALENDAR")
    assert "BEGIN:VTIMEZONE" in text
    assert "DTSTART;TZID=America/Chicago:20250603T100000" in text
    assert "confirm against the official hearing notice" in text.lower()
    assert all(len(line.encode()) <= 75 for line in text.splitlines())
    single = built / "public" / "calendar" / "hearings" / "h1.ics"
    assert single.exists()


def test_session_csvs_written(built: Path) -> None:
    bills_csv = (built / "exports" / "2025" / "bills.csv").read_text(encoding="utf-8")
    assert "AB 656" in bills_csv
    assert "9999" not in bills_csv
