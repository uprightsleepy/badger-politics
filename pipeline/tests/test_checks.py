"""Integrity gates catch bad data and stay quiet on good data."""

import json
import sqlite3
from pathlib import Path

import pytest

from importer.checks import check_local, run_checks


@pytest.fixture()
def db_path(tmp_path: Path, make_db) -> Path:
    path = tmp_path / "wi.sqlite"
    conn = make_db(path)
    conn.execute("INSERT INTO sessions (id, identifier) VALUES ('2025', '2025')")
    conn.execute(
        "INSERT INTO bills (id, session_id, identifier, source)"
        " VALUES ('2025-ab1', '2025', 'AB 1', 'openstates')"
    )
    for pid, name in [("p1", "A"), ("p2", "B"), ("p3", "C")]:
        conn.execute("INSERT INTO people (id, name) VALUES (?, ?)", (pid, name))
    conn.execute(
        "INSERT INTO vote_events (id, bill_id, yes_count, no_count, nv_count)"
        " VALUES ('v1', '2025-ab1', 2, 0, 1)"
    )
    for pid, option in [("p1", "yes"), ("p2", "yes"), ("p3", "not voting")]:
        conn.execute(
            "INSERT INTO vote_records (vote_event_id, person_id, option) VALUES ('v1', ?, ?)",
            (pid, option),
        )
    conn.executemany(
        "INSERT INTO executive_orders (folder, governor, year, number, suffix, url)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [("2011_scott_walker", "Scott Walker", 2019, 319, "", f"{EO_ARCHIVE}/2019/319.pdf"),
         ("2019_tony_evers", "Tony Evers", 2019, 1, "", f"{EO_ARCHIVE}/2019/1.pdf"),
         ("2019_tony_evers", "Tony Evers", 2020, 72, "", f"{EO_ARCHIVE}/2020/72.pdf"),
         ("1965_warren_p_knowles", "Warren P. Knowles", 1969, 12, "A",
          f"{EO_ARCHIVE}/1969/12a.pdf")],
    )
    conn.commit()
    conn.close()
    return path


EO_ARCHIVE = "https://docs.legis.wisconsin.gov/document/executiveorders"


def test_executive_orders_must_be_listed(db_path: Path, tmp_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM executive_orders")
    assert run_checks(db_path, tmp_path / "c.json") == ["executive_orders: no orders imported"]


@pytest.mark.parametrize(("year", "number", "suffix", "url"), [
    (2020, 73, "", "http://docs.legis.wisconsin.gov/document/executiveorders/2020/73.pdf"),
    (2020, 73, "", f"{EO_ARCHIVE}/2020/74.pdf"),
    (2020, 73, "", f"{EO_ARCHIVE}/2021/73.pdf"),
    (2020, 73, "", "https://docs.legis.wisconsin.gov/code/executive_orders/2019_tony_evers/2020-73"),
    (2020, 73, "", "https://evers.wi.gov/eo/2020_73.pdf"),
    (2020, 73, "a", f"{EO_ARCHIVE}/2020/73a.pdf"),
    (2020, 7, "3", f"{EO_ARCHIVE}/2020/73.pdf"),
])
def test_executive_order_links_are_their_own_archive_pdf(
    db_path: Path, tmp_path: Path, year: int, number: int, suffix: str, url: str
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO executive_orders (folder, governor, year, number, suffix, url)"
            " VALUES ('2019_tony_evers', 'Tony Evers', ?, ?, ?, ?)", (year, number, suffix, url))
    assert run_checks(db_path, tmp_path / "c.json") == [
        "executive_orders: 1 links outside the official archive"]


@pytest.mark.parametrize(("folder", "year"), [
    ("2019_tony_evers", 2018), ("2011_scott_walker", 2020), ("2011_scott_walker", 2010)])
def test_executive_orders_fall_in_their_governors_tenure(
    db_path: Path, tmp_path: Path, folder: str, year: int
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO executive_orders (folder, governor, year, number, url)"
            " VALUES (?, 'Governor', ?, 900, ?)", (folder, year, f"{EO_ARCHIVE}/{year}/900.pdf"))
    assert run_checks(db_path, tmp_path / "c.json") == [
        "executive_orders: 1 orders outside their governor's tenure"]


def test_consistent_db_passes(db_path: Path, tmp_path: Path) -> None:
    assert run_checks(db_path, tmp_path / "counts.json") == []


def test_count_mismatch_fails(db_path: Path, tmp_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE vote_events SET yes_count = 3 WHERE id = 'v1'")
    conn.commit()
    conn.close()
    failures = run_checks(db_path, tmp_path / "counts.json")
    assert any("stored counts" in f for f in failures)


def test_bill_count_regression_fails(db_path: Path, tmp_path: Path) -> None:
    counts_file = tmp_path / "counts.json"
    counts_file.write_text(json.dumps({"2025": 500}), encoding="utf-8")
    failures = run_checks(db_path, counts_file)
    assert any("bill count fell" in f for f in failures)


def test_bill_count_state_written_on_success(db_path: Path, tmp_path: Path) -> None:
    counts_file = tmp_path / "counts.json"
    assert run_checks(db_path, counts_file) == []
    assert json.loads(counts_file.read_text(encoding="utf-8")) == {"2025": 1}


def test_bill_count_state_kept_when_another_check_fails(db_path: Path, tmp_path: Path) -> None:
    counts_file = tmp_path / "counts.json"
    counts_file.write_text(json.dumps({"2025": 1}), encoding="utf-8")
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE vote_events SET yes_count = 3 WHERE id = 'v1'")
    conn.execute(
        "INSERT INTO bills (id, session_id, identifier, source)"
        " VALUES ('2025-ab2', '2025', 'AB 2', 'openstates')"
    )
    conn.commit()
    conn.close()
    assert run_checks(db_path, counts_file)
    assert json.loads(counts_file.read_text(encoding="utf-8")) == {"2025": 1}


def test_nv_all_or_none(db_path: Path, tmp_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    # page-omitted NV list: count says 2, zero NV records -> allowed
    conn.execute(
        "INSERT INTO vote_events (id, bill_id, yes_count, no_count, nv_count)"
        " VALUES ('v2', '2025-ab1', 1, 0, 2)"
    )
    conn.execute(
        "INSERT INTO vote_records (vote_event_id, person_id, option)"
        " VALUES ('v2', 'p1', 'yes')"
    )
    conn.commit()
    assert run_checks(db_path, tmp_path / "c.json") == []
    # partial NV parse: 1 of 2 -> still fails
    conn.execute(
        "INSERT INTO vote_records (vote_event_id, person_id, option)"
        " VALUES ('v2', 'p2', 'not voting')"
    )
    conn.commit()
    conn.close()
    failures = run_checks(db_path, tmp_path / "c.json")
    assert any("v2" in f for f in failures)


@pytest.mark.parametrize("office,district,passes", [
    ("Supreme Court", None, True),                          # the usual shape
    ("Circuit Court", "Marathon County Circuit Court", True),
    (None, "State Senate, District No. 23", True),          # the race is in the district field
    (None, None, False),                                    # no race named at all
])
def test_advocacy_race_may_be_named_in_either_field(
    db_path: Path, tmp_path: Path, office, district, passes,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO cf_committees (entity_id, name, committee_type)"
        " VALUES (30614, 'Example IE Committee', 'Independent Expenditure Committee')"
    )
    conn.execute(
        "INSERT INTO cf_transactions (id, filer_entity_id, filer_type, direction, date,"
        " amount, stance, related_name, related_office, related_district)"
        " VALUES (1, 30614, 'Independent Expenditure Committee', 'OUTGOING', '2026-09-08',"
        " 100.0, 'FOR', 'Quinn for Senate', ?, ?)",
        (office, district),
    )
    conn.commit()
    conn.close()
    failures = run_checks(db_path, tmp_path / "c.json")
    named = [f for f in failures if "advocacy naming a candidate" in f]
    assert (named == []) is passes, failures


def test_orphan_vote_record_fails(db_path: Path, tmp_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM people WHERE id = 'p3'")
    conn.commit()
    conn.close()
    failures = run_checks(db_path, tmp_path / "counts.json")
    assert any("vote_records -> people" in f for f in failures)


@pytest.fixture()
def local_db(make_db):
    conn = make_db(":memory:")
    conn.execute("INSERT INTO local_bodies VALUES ('city', 'city', 'City', 'Council',"
                 " 'https://example.invalid', 1)")
    conn.execute("INSERT INTO local_members"
                 " (tenant, person_id, name, slug, seat, member_type, is_current)"
                 " VALUES ('city', 1, 'Member', 'member', 1, 'Member', 1)")
    conn.execute("INSERT INTO local_events VALUES"
                 " ('city', 1, '2026-01-01', 'Final', 'https://example.invalid/meeting')")
    conn.execute("INSERT INTO local_actions (tenant, event_item_id, event_id, action)"
                 " VALUES ('city', 1, 1, 'Adopted')")
    conn.executemany("INSERT INTO local_vote_types VALUES ('city', ?)",
                     [(value,) for value in ('Aye', 'No', 'Nay', 'Abstain')])
    conn.execute("INSERT INTO local_votes VALUES ('city', 1, 1, 'Nay')")
    yield conn
    conn.close()


@pytest.mark.parametrize("value,passes", [
    ("No", True), ("Nay", True), ("Aye", False), ("Abstain", False),
])
def test_local_dissent_uses_only_recorded_negative_votes(local_db, value, passes):
    local_db.execute("UPDATE local_votes SET value=?", (value,))
    failures = check_local(local_db)
    expected = [] if passes else ["local tenants with no dissenting vote on record: 1 rows"]
    assert failures == expected


def test_nay_must_still_belong_to_the_tenants_vocabulary(local_db):
    local_db.execute("DELETE FROM local_vote_types WHERE value='Nay'")
    assert check_local(local_db) == ["local vote values outside the tenant's vocabulary: 1 rows"]


@pytest.mark.parametrize("title,start,end,passes", [
    ("Mayor", "2000-01-01", "9999-12-31", True),
    ("Mayor", "2000-01-01", "2001-01-01", False),
    ("Mayor", "9998-01-01", "9999-12-31", False),
    ("Mayor", "2000-01-01", None, False),
    ("Alderperson", "2000-01-01", "9999-12-31", False),
])
def test_unseated_member_requires_a_proven_active_mayor_term(local_db, title, start, end, passes):
    local_db.execute("UPDATE local_members SET seat=NULL")
    local_db.execute("INSERT INTO local_member_terms VALUES ('city', 1, ?, ?, ?)",
                     (title, start, end))
    failures = check_local(local_db)
    assert failures == ([] if passes else ["sitting council members missing a seat: 1 rows"])
