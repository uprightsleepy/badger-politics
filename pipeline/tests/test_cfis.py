"""CFIS committee matching never guesses; archive import stays referential."""

import json
import sqlite3
from pathlib import Path

import pytest

from importer.import_cfis import run as import_run
from scraper.fetch_cfis import match_committees

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "importer" / "schema.sql"


def hit(name: str, committee_type: str = "State Candidate", entity_id: int = 1) -> dict:
    return {"id": entity_id, "name": name,
            "committee": {"committeeType": {"name": committee_type}}}


def test_all_own_committees_match() -> None:
    hits = [hit("Friends of Shae Sortwell", entity_id=1),
            hit("Shae Sortwell for Assembly", entity_id=2),
            hit("Citizens for Growth", entity_id=3)]
    assert [m["id"] for m in match_committees("Shae Sortwell", hits)] == [1, 2]


def test_non_candidate_committees_ignored() -> None:
    hits = [hit("Vos Victory PAC", committee_type="Political Action Committee")]
    assert match_committees("Robin Vos", hits) == []


def test_nickname_prefix_matches() -> None:
    hits = [hit("William Penterman for Assembly")]
    assert len(match_committees("Will Penterman", hits)) == 1


def test_other_persons_committee_never_matches() -> None:
    # same surname, different first name: every-word rule rejects
    hits = [hit("Brent Jacobson for Assembly"), hit("Citizens for Lothian", entity_id=2)]
    assert match_committees("Jenna Jacobson", hits) == []
    assert match_committees("Tyler August", hits) == []


def test_middle_initial_never_satisfies_a_name_word() -> None:
    # regression: 'John R. Wagner for Judge' must not match 'Rivera Wagner'
    hits = [hit("John R. Wagner for Judge", committee_type="Unregistered")]
    assert match_committees("Rivera Wagner", hits) == []


def test_other_office_committees_excluded() -> None:
    hits = [hit("Jane Smith for Judge"), hit("Jane Smith for County Clerk", entity_id=2),
            hit("Jane Smith for Governor", entity_id=3)]
    assert match_committees("Jane Smith", hits) == []


def test_bare_surname_alias_carries_no_identity() -> None:
    from scraper.fetch_cfis import name_variants

    variants = name_variants(
        "Amaad Rivera-Wagner", "Rivera-Wagner", ["RIVERA WAGNER", "A.I. Rivera-Wagner"]
    )
    assert variants == ["Amaad Rivera-Wagner"]
    # but a real formal-name alias survives
    assert "Robert Wittke" in name_variants("Bob Wittke", "Wittke", ["Robert Wittke"])


def test_import_rejects_unknown_person(tmp_path: Path) -> None:
    db = tmp_path / "wi.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("INSERT INTO people (id, name) VALUES ('p1', 'A')")
    conn.commit()
    conn.close()
    archive = tmp_path / "cfis"
    archive.mkdir()
    good = {"id": 1, "person_id": "p1", "committee_entity_id": 9, "date": "2026-01-05",
            "amount": 50, "from_name": "Jane Donor", "from_type": "Individual",
            "occupation": "Teacher", "category": "Monetary"}
    (archive / "tx-2026-01.json").write_text(json.dumps([good]), encoding="utf-8")
    assert import_run(archive, db) == 0

    bad = dict(good, id=2, person_id="ghost")
    (archive / "tx-2026-02.json").write_text(json.dumps([bad]), encoding="utf-8")
    with pytest.raises(RuntimeError, match="unknown person"):
        import_run(archive, db)
