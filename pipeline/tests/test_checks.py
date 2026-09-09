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
    conn.commit()
    conn.close()
    return path


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
