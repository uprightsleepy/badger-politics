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
        INSERT INTO people (id, name, party, current_role, chamber, district)
          VALUES ('ocd-person/p1', 'Ann Example', 'Independent', 'Representative',
                  'lower', 15);
        INSERT INTO bills (id, session_id, identifier, title, status,
                           died_without_hearing, source)
          VALUES ('2025-ab656', '2025', 'AB 656', 'Child marriage ban',
                  'failed_sjr1', 1, 'openstates');
        INSERT INTO bills (id, session_id, identifier, title, source)
          VALUES ('2025-ab9999', '2025', 'AB 9999', 'SECRET LEGISCAN BILL', 'legiscan');
        INSERT INTO lobbying_interests (bill_id, principal_id, principal, source_url)
          VALUES ('2025-ab656', 999, 'WITHHELD_LOBBYING_ORGANIZATION',
                  'https://lobbying.wi.gov/What/BillInformation/2025REG/Information/25090');
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
        INSERT INTO bill_companions (bill_id, companion_bill_id, source_url)
          VALUES ('2025-ab656', '2025-ab9999', 'https://example.gov/ab656'),
                 ('2025-ab9999', '2025-ab656', 'https://example.gov/ab9999');
        INSERT INTO bill_subjects (bill_id, subject) VALUES ('2025-ab9999', 'LEGISCAN SUBJECT');
        INSERT INTO bill_documents (bill_id, note, url)
          VALUES ('2025-ab9999', 'LEGISCAN FISCAL ESTIMATE', 'https://example.gov/fe'),
                 ('2025-ab656', 'AB 656: Assembly Amendment 1',
                  'https://docs.legis.wisconsin.gov/2025/related/amendments/ab656/aa1_ab656');
        INSERT INTO bill_versions (bill_id, note, date, url, media_type)
          VALUES ('2025-ab656', 'Bill Text',  NULL,
                  'https://docs.legis.wisconsin.gov/document/proposaltext/2025/REG/AB656',
                  'text/html'),
                 ('2025-ab9999', 'LEGISCAN BILL TEXT', NULL, 'https://example.gov/t', 'text/html');
        -- an openstates roll call on the legiscan bill is withheld with it
        INSERT INTO vote_events (id, bill_id, date, chamber, motion, result, source)
          VALUES ('2025-v8', '2025-ab9999', '2025-06-02', 'lower', 'Concurrence',
                  'pass', 'openstates');
        INSERT INTO vote_records (vote_event_id, person_id, option)
          VALUES ('2025-v8', 'ocd-person/p1', 'no');
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
        INSERT INTO bills (id, session_id, identifier, title, status, source)
          VALUES ('2025-ab7', '2025', 'AB 7', 'State budget', 'enacted', 'openstates');
        INSERT INTO actions (id, bill_id, date, description, classification)
          VALUES ('a3', '2025-ab7', '2025-04-01',
                  'Approved by the Governor with partial veto on 4-1-2025;'
                  || ' 2025 Wisconsin Act 7', 'executive-signature');
        INSERT INTO committee_members (committee_id, person_id, role)
          VALUES ('c1', 'ocd-person/p1', 'chair');
        INSERT INTO bill_subjects (bill_id, subject)
          VALUES ('2025-ab656', 'Marriage — Minimum age');
        INSERT INTO election_history (year, chamber, district, candidate, party, votes,
                                      total_cast)
          VALUES (2024, 'lower', 15, 'Ann Example', 'IND', 15000, 25010),
                 (2024, 'lower', 15, 'Bob Rival', 'REP', 10000, 25010),
                 (2020, 'lower', 15, 'Ann Example', 'IND', 9000, 9000);
        INSERT INTO judicial_history VALUES (2025, 'spring',
          'JUSTICE OF THE SUPREME COURT', NULL, 'Susan Crawford', 1301137, 2364887, 'u');
        INSERT INTO referendum_history VALUES (2025, 'spring', 1,
          'State of Wisconsin Referendum', 1437317, 851851, 2289168, 'u');
        INSERT INTO congressional_races (district, incumbent, incumbent_noncandidacy,
                                         candidate, party, ballot_status, source)
          VALUES (2, 'Mark Pocan', 0, 'Mark Pocan', 'Democratic', 'Approve', 'wec');
        INSERT INTO federal_members (bioguide, lis_id, name, slug, party, chamber,
                                     term_start, term_end)
          VALUES ('B001230', 'S354', 'Tammy Baldwin', 'tammy-baldwin', 'Democratic',
                  'senate', '2025-01-03', '2031-01-03');
        INSERT INTO federal_votes (id, congress, session, chamber, number, date, question,
                                   result, yeas, nays, source_url)
          VALUES ('s119-1-1', 119, 1, 'senate', 1, '2025-01-09', 'On the Motion',
                  'Agreed to', 60, 40, 'https://www.senate.gov/vote1');
        INSERT INTO federal_vote_records (vote_id, member_id, last_name, party, state,
                                          vote_cast)
          VALUES ('s119-1-1', 'S354', 'Baldwin', 'D', 'WI', 'Yea');
        INSERT INTO cf_committees (entity_id, name, committee_type, assigned_id)
          VALUES (77, 'Realtors PAC', 'Political Action Committee', '0100'),
                 (88, 'Outside Group', 'Independent Expenditure Committee', '0200');
        INSERT INTO contributions (id, person_id, committee_entity_id, date, amount,
                                   from_entity_id, from_name, from_type, occupation)
          VALUES (1, 'ocd-person/p1', 500, '2025-05-01', 100, 9001,
                  'PRIVATE INDIVIDUAL DONOR', 'Individual', 'Teacher'),
                 (2, 'ocd-person/p1', 500, '2025-05-02', 1000, 77,
                  'Realtors PAC', 'Registrant', NULL);
        INSERT INTO cf_transactions (id, filer_entity_id, filer_type, direction, date,
                                     amount, other_entity_id, other_name, other_type,
                                     stance, related_name, related_office,
                                     related_district, purpose, report_id, report_name)
          VALUES (10, 77, 'Political Action Committee', 'INCOMING', '2025-04-01', 50,
                  9002, 'PRIVATE PAC DONOR', 'Individual',
                  NULL, NULL, NULL, NULL, NULL, NULL, NULL),
                 (11, 77, 'Political Action Committee', 'INCOMING', '2025-04-02', 300,
                  66, 'Union Committee', 'Registrant',
                  NULL, NULL, NULL, NULL, NULL, NULL, NULL),
                 (12, 88, 'Independent Expenditure Committee', 'OUTGOING', '2025-09-01',
                  5000, NULL, 'Ad Vendor LLC', 'Business', 'AGAINST', 'Ann Example',
                  'State Assembly', '15', 'TV ad', 4242, 'Fall Report');
        INSERT INTO executive_orders (folder, governor, year, number, suffix, url)
          VALUES ('2019_tony_evers', 'Tony Evers', 2020, 72, '',
                  'https://docs.legis.wisconsin.gov/document/executiveorders/2020/72.pdf'),
                 ('2019_tony_evers', 'Tony Evers', 2019, 1, '',
                  'https://docs.legis.wisconsin.gov/document/executiveorders/2019/1.pdf'),
                 ('2011_scott_walker', 'Scott Walker', 2019, 319, '',
                  'https://docs.legis.wisconsin.gov/document/executiveorders/2019/319.pdf');
        INSERT INTO statewide_races (office, incumbent, incumbent_noncandidacy,
                                     candidate, party, ballot_status, source)
          VALUES ('GOVERNOR', 'Tony Evers', 1, 'Sara Rodriguez', 'Democratic',
                  'Approve', 'wec');
        INSERT INTO statewide_history (year, office, candidate, party, votes)
          VALUES (2022, 'GOVERNOR / LIEUTENANT GOVERNOR',
                  'Tony Evers / Sara Rodriguez', 'DEM', 1358774);
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
    assert payload["versions"] == [{
        "note": "Bill Text", "date": None, "media_type": "text/html",
        "url": "https://docs.legis.wisconsin.gov/document/proposaltext/2025/REG/AB656"}]
    assert payload["documents"][0]["note"] == "AB 656: Assembly Amendment 1"


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


def test_statewide_json_shape(built: Path) -> None:
    payload = json.loads(
        (built / "public" / "api" / "v1" / "elections" / "statewide.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["races"][0]["office"] == "GOVERNOR"
    assert payload["races"][0]["incumbent_noncandidacy"] == 1
    assert payload["history"][0]["votes"] == 1358774


def test_wider_api_shapes(built: Path) -> None:
    api = built / "public" / "api" / "v1"

    def load(path: str):
        return json.loads((api / path).read_text(encoding="utf-8"))

    committee = load("committees/c1.json")
    assert committee["chair"] == {"id": "p1", "name": "Ann Example"}
    assert committee["members"][0]["role"] == "chair"
    assert [h["id"] for h in committee["past_hearings"]] == ["h1"]
    assert committee["upcoming_hearings"] == []
    assert load("hearings.json")[0]["agenda_bills"] == ["AB 656"]
    subjects = load("subjects/index.json")
    assert subjects == [{"slug": "marriage-minimum-age", "title": "Marriage: Minimum age",
                         "headings": ["Marriage — Minimum age"], "bills": 1}]
    assert load("subjects/marriage-minimum-age.json")["bills"][0]["id"] == "2025-ab656"
    seat = load("elections/seats/assembly-15.json")
    assert seat["holder"]["id"] == "p1" and seat["election"]["cycle_year"] == 2026
    assert seat["results"][0]["candidates"][0] == {
        "candidate": "Ann Example", "party": "IND", "votes": 15000}
    # each result names the map it was held under, never the current lines by default
    assert [(r["year"], r["maps"]) for r in seat["results"]] == [(2024, "2024"), (2020, "2011")]
    assert load("elections/judicial.json")["races"][0]["candidate"] == "Susan Crawford"
    assert load("elections/referenda.json")["questions"][0]["yes"] == 1437317
    assert load("elections/seats/senate-33.json")["holder"] is None
    assert load("elections/us-house.json")["races"][0]["candidate"] == "Mark Pocan"
    assert load("federal/tammy-baldwin.json")["votes"][0]["vote_cast"] == "Yea"
    # money: never beside votes, individuals only in totals
    money = load("money/legislators/p1.json")
    assert "votes" not in money and money["total"] == 1100
    assert money["individual_total"] == 100
    assert money["top_committees"][0]["entity_id"] == 77
    assert money["top_occupations"][0]["occupation"] == "Teacher"
    pac = load("money/committees/77.json")
    assert pac["recipients"][0]["id"] == "p1"
    donors = pac["own_money"]["itemized_donors"]
    assert [d["name"] for d in donors["largest"]] == ["Union Committee"]
    assert donors["individuals"] == {"total": 50, "transactions": 1}
    filing = load("money/independent.json")["filings"][0]
    assert filing["transaction_id"] == 12 and filing["report_id"] == 4242


def test_no_legiscan_anywhere(built: Path) -> None:
    hits = []
    for path in built.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".xml", ".ics", ".csv"):
            text = path.read_text(encoding="utf-8", errors="replace").upper()
            if any(m in text for m in ("LEGISCAN", "AB 9999", "AB9999", "2025-V8")):
                hits.append(str(path))
    assert hits == [], f"legiscan content escaped into: {hits}"
    assert not (built / "public" / "api" / "v1" / "bills" / "2025" / "ab9999.json").exists()
    assert not (built / "public" / "api" / "v1" / "votes" / "2025-v9.json").exists()
    assert not (built / "public" / "api" / "v1" / "votes" / "2025-v8.json").exists()


def test_filtered_sqlite_has_no_legiscan_rows(built: Path) -> None:
    conn = sqlite3.connect(built / "exports" / "wi-filtered.sqlite")
    for table in ("bills", "vote_events"):
        count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE source = 'legiscan'"  # noqa: S608
        ).fetchone()[0]
        assert count == 0, table
    # the exportable bills are still there, and nothing points at the withheld one
    assert conn.execute("SELECT COUNT(*) FROM bills").fetchone()[0] == 2
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    for table in ("bill_companions", "bill_subjects", "bill_documents", "bill_versions",
                  "vote_events"):
        assert conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE bill_id = '2025-ab9999'"  # noqa: S608
        ).fetchone()[0] == 0, table
    assert conn.execute(
        "SELECT COUNT(*) FROM vote_records WHERE vote_event_id = '2025-v8'"
    ).fetchone()[0] == 0
    conn.close()


def test_lobbying_is_private_even_in_downloadable_database(built: Path, db_path: Path) -> None:
    marker = b"WITHHELD_LOBBYING_ORGANIZATION"
    # The local source is preserved for a future approved import.
    with sqlite3.connect(db_path) as source:
        assert source.execute("SELECT COUNT(*) FROM lobbying_interests").fetchone()[0] == 1
    snapshot = built / "exports" / "wi-filtered.sqlite"
    with sqlite3.connect(snapshot) as public:
        assert public.execute("SELECT COUNT(*) FROM lobbying_interests").fetchone()[0] == 0
        assert public.execute("PRAGMA foreign_key_check").fetchall() == []
    # VACUUM must remove deleted values, not just hide them from SQL queries.
    assert marker not in snapshot.read_bytes()
    assert b"lobbying.wi.gov/What/BillInformation" not in snapshot.read_bytes()
    for directory in (built / "public", built / "exports"):
        for path in directory.rglob("*"):
            if path.is_file():
                assert marker not in path.read_bytes(), path


def test_individual_donors_only_in_aggregate(built: Path, db_path: Path) -> None:
    markers = (b"PRIVATE INDIVIDUAL DONOR", b"PRIVATE PAC DONOR")
    with sqlite3.connect(db_path) as source:
        assert source.execute("SELECT COUNT(*) FROM contributions"
                              " WHERE from_name IS NOT NULL").fetchone()[0] == 2
    snapshot = built / "exports" / "wi-filtered.sqlite"
    with sqlite3.connect(snapshot) as public:
        # the receipts stay, so totals still add up; committees stay named
        assert public.execute("SELECT SUM(amount) FROM contributions").fetchone()[0] == 1100
        assert public.execute("SELECT from_name, from_entity_id, occupation FROM contributions"
                              " WHERE id = 1").fetchone() == (None, None, None)
        assert public.execute("SELECT other_name FROM cf_transactions"
                              " WHERE id = 11").fetchone() == ("Union Committee",)
    for directory in (built / "public", built / "exports"):
        for path in directory.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                assert not any(m in data for m in markers), path


def test_release_package(built: Path) -> None:
    import gzip
    import hashlib
    import zipfile

    from dataproducts.bulk import package

    release = built / "release"
    assets = package(built / "exports", release)
    assert [p.name for p in assets] == [
        "badger-politics-csv.zip", "wi-filtered.sqlite.gz", "README.txt", "SHA256SUMS",
    ]
    names = zipfile.ZipFile(release / "badger-politics-csv.zip").namelist()
    assert "2025/bills.csv" in names and "people.csv" in names
    assert gzip.decompress((release / "wi-filtered.sqlite.gz").read_bytes()) == (
        built / "exports" / "wi-filtered.sqlite").read_bytes()
    for line in (release / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((release / name).read_bytes()).hexdigest() == digest


def test_feeds_are_valid_atom(built: Path) -> None:
    feed = built / "public" / "feeds" / "bills" / "2025-ab656.xml"
    root = ET.parse(feed).getroot()
    assert root.tag == "{http://www.w3.org/2005/Atom}feed"
    ns = {"a": "http://www.w3.org/2005/Atom"}
    assert root.find("a:id", ns) is not None
    assert root.find("a:updated", ns) is not None
    entries = root.findall("a:entry", ns)
    assert entries and entries[0].find("a:id", ns) is not None
    weekly = ET.parse(built / "public" / "feeds" / "weekly.xml").getroot()
    # entry ids are the actions' own ids, stable as the week's list shifts
    ids = [e.find("a:id", ns).text for e in weekly.findall("a:entry", ns)]
    assert ids == ["https://badgerpolitics.org/feeds/weekly.xml#a1"]


def test_executive_orders_json_is_newest_first(built: Path) -> None:
    payload = json.loads(
        (built / "public" / "api" / "v1" / "executive-orders.json").read_text(encoding="utf-8"))
    # within a year, the later governor's orders come first
    assert [(o["governor"], o["year"], o["number"]) for o in payload] == [
        ("Tony Evers", 2020, 72), ("Tony Evers", 2019, 1), ("Scott Walker", 2019, 319)]
    assert payload[0] == {"governor": "Tony Evers", "year": 2020, "number": 72, "suffix": "",
                          "url": "https://docs.legis.wisconsin.gov/document/executiveorders/2020/72.pdf"}


@pytest.mark.parametrize(("feed", "entry_ids"), [
    ("districts/assembly-15.xml", ["2025-v1"]),
    ("subjects/marriage-minimum-age.xml", ["a1"]),
    ("laws.xml", ["a3"]),
    ("vetoes.xml", ["a3"]),
    ("money/independent.xml", ["t12"]),
])
def test_new_feeds_use_record_ids(built: Path, feed: str, entry_ids: list[str]) -> None:
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.parse(built / "public" / "feeds" / feed).getroot()
    assert root.find("a:updated", ns).text.endswith("T00:00:00Z")
    ids = [e.find("a:id", ns).text for e in root.findall("a:entry", ns)]
    assert ids == [f"https://badgerpolitics.org/feeds/{feed}#{i}" for i in entry_ids]


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


def test_same_day_actions_keep_their_order(tmp_path: Path, make_db) -> None:
    conn = make_db(tmp_path / "order.sqlite")
    conn.execute(
        "INSERT INTO sessions (id, identifier, name) VALUES ('2025', '2025', '2025-26')"
    )
    conn.execute(
        "INSERT INTO bills (id, session_id, identifier, source)"
        " VALUES ('2025-ab1', '2025', 'AB 1', 'openstates')"
    )
    for i in range(12):
        conn.execute(
            "INSERT INTO actions (id, bill_id, date, description) VALUES (?, ?, ?, ?)",
            (f"2025-ab1-a{i}", "2025-ab1", "2025-06-01", f"step {i}"),
        )
    conn.commit()
    conn.row_factory = sqlite3.Row
    expected = [f"step {i}" for i in range(12)]
    assert [a["description"] for a in queries.actions_for(conn, "2025-ab1")] == expected
    (_, grouped), = queries.actions_grouped(conn)
    assert [a["description"] for a in grouped] == expected
    by_session = queries.actions_for_session(conn, "2025")["2025-ab1"]
    assert [a["description"] for a in by_session] == expected


def test_builds_from_a_snapshot_older_than_the_newest_tables(
    db_path: Path, tmp_path: Path
) -> None:
    # Releases build from the newest snapshot, which can predate a new table.
    conn = sqlite3.connect(db_path)
    for table in ("bill_versions", "court_challenges", "executive_orders",
                  "judicial_history", "referendum_history"):
        conn.execute(f"DROP TABLE {table}")  # noqa: S608 - fixed names
    conn.commit()
    conn.row_factory = sqlite3.Row
    out = tmp_path / "public"
    build_api(conn, out)
    build_feeds(conn, out)
    build_bulk(conn, db_path, tmp_path / "exports")
    bill = json.loads((out / "api/v1/bills/2025/ab656.json").read_text(encoding="utf-8"))
    assert bill["versions"] == []
    judicial = (out / "api/v1/elections/judicial.json").read_text(encoding="utf-8")
    assert json.loads(judicial) == {"races": []}
