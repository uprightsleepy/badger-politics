"""Integrity gates catch bad data and stay quiet on good data."""

import json
import sqlite3
from pathlib import Path

import pytest

from importer.checks import run_checks

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "importer" / "schema.sql"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "wi.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
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


def test_orphan_vote_record_fails(db_path: Path, tmp_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM people WHERE id = 'p3'")
    conn.commit()
    conn.close()
    failures = run_checks(db_path, tmp_path / "counts.json")
    assert any("vote_records -> people" in f for f in failures)
