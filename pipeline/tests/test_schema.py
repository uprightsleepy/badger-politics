"""Phase 0: the schema applies cleanly and its constraints hold."""

import sqlite3

import pytest

EXPECTED_TABLES = {
    "sessions",
    "people",
    "bills",
    "sponsorships",
    "actions",
    "vote_events",
    "vote_records",
    "committees",
    "hearings",
    "elections",
    "election_history",
    "meta",
}


@pytest.fixture()
def db(make_db) -> sqlite3.Connection:
    conn = make_db(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_schema_creates_all_tables(db: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert EXPECTED_TABLES <= tables


def test_bill_source_is_constrained(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO sessions (id, identifier) VALUES ('s1', '2025')")
    db.execute(
        "INSERT INTO bills (id, session_id, identifier, source)"
        " VALUES ('b1', 's1', 'AB 656', 'openstates')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO bills (id, session_id, identifier, source)"
            " VALUES ('b2', 's1', 'AB 657', 'wikipedia')"
        )


def test_vote_option_is_constrained(db: sqlite3.Connection) -> None:
    db.execute("INSERT INTO sessions (id, identifier) VALUES ('s1', '2025')")
    db.execute(
        "INSERT INTO bills (id, session_id, identifier) VALUES ('b1', 's1', 'AB 656')"
    )
    db.execute("INSERT INTO people (id, name) VALUES ('p1', 'Rep. Example')")
    db.execute("INSERT INTO vote_events (id, bill_id) VALUES ('v1', 'b1')")
    db.execute(
        "INSERT INTO vote_records (vote_event_id, person_id, option)"
        " VALUES ('v1', 'p1', 'excused')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO vote_records (vote_event_id, person_id, option)"
            " VALUES ('v1', 'p1', 'maybe')"
        )


def test_session_data_quality_is_constrained(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO sessions (id, identifier, data_quality) VALUES ('s1', '2023', 'partial')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO sessions (id, identifier, data_quality) VALUES ('s2', '2021', 'great')"
        )
