"""Service terms: what the importer persists for each member.

Dated terms are stored as recorded; synthetic (guessed) ones are replaced
by a biennium-bounded supplement when the session roster seats the member;
curated departure events relabel the ends they match, and one that matches
nothing aborts the run rather than silently going unused.
"""

import json
from pathlib import Path

import pytest

from importer import import_openstates
from importer.committees import CommitteeIndex
from importer.import_openstates import Importer
from importer.roster import Member, Person, Roster, Term

WINDOWS = {"2025": ("2025-01-06", "2027-01-04")}


def person(pid: str, name: str, *terms: Term) -> Person:
    return Person(
        id=pid, name=name, family_name=name.split()[-1], party="Test",
        image_url=None, terms=list(terms),
    )


@pytest.fixture()
def curation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point both curation files at scratch copies; returns a writer."""
    events, terms = tmp_path / "term_events.json", tmp_path / "person_terms.json"
    events.write_text("{}", encoding="utf-8")
    terms.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(import_openstates, "TERM_EVENTS_PATH", events)
    monkeypatch.setattr(import_openstates, "TERMS_PATH", terms)

    def write(*, events_json: dict | None = None, terms_json: dict | None = None) -> None:
        if events_json is not None:
            events.write_text(json.dumps(events_json), encoding="utf-8")
        if terms_json is not None:
            terms.write_text(json.dumps(terms_json), encoding="utf-8")

    return write


def run(make_db, people: list[Person]) -> list[tuple]:
    conn = make_db(":memory:")
    roster = Roster(
        [Member.from_person(p, p.terms[0].chamber, p.terms[0].district) for p in people]
    )
    importer = Importer(conn, {"2025": roster}, CommitteeIndex([]), {"2025"})
    importer.import_people()
    importer.import_terms(people, WINDOWS)
    return conn.execute(
        "SELECT person_id, chamber, start, end, end_label, end_url"
        " FROM person_terms ORDER BY person_id, start"
    ).fetchall()


def test_dated_term_is_stored_as_recorded(make_db, curation) -> None:
    rows = run(make_db, [person("p1", "Ann Able", Term("lower", 5, "2025-01-06", None))])
    assert rows == [("p1", "lower", "2025-01-06", None, None, None)]


def test_synthetic_term_becomes_a_biennium_supplement(make_db, curation) -> None:
    guessed = Term("upper", 9, "2023-01-05", "2027-01-03", synthetic=True)
    rows = run(make_db, [person("p2", "Bo Baker", guessed)])
    # the guess is never persisted; the roster seat gets exact biennium bounds
    assert rows == [("p2", "upper", "2025-01-01", "2027-01-01", None, None)]


def test_exclusive_curation_blocks_the_supplement(make_db, curation) -> None:
    curation(terms_json={"p2": [{"chamber": "upper", "exclusive": True}]})
    guessed = Term("upper", 9, "2023-01-05", "2027-01-03", synthetic=True)
    assert run(make_db, [person("p2", "Bo Baker", guessed)]) == []


def test_departure_event_relabels_the_matching_end(make_db, curation) -> None:
    curation(events_json={"p1": [
        {"end": "2025-06-30", "label": "Resigned", "url": "https://example.test/r"},
    ]})
    rows = run(make_db, [person("p1", "Ann Able", Term("lower", 5, "2025-01-06", "2025-06-30"))])
    assert rows == [
        ("p1", "lower", "2025-01-06", "2025-06-30", "Resigned", "https://example.test/r"),
    ]


def test_event_for_the_other_chamber_is_ignored(make_db, curation) -> None:
    curation(events_json={"p1": [{"end": "2025-06-30", "chamber": "upper", "label": "Resigned"}]})
    with pytest.raises(RuntimeError, match="match no imported term"):
        run(make_db, [person("p1", "Ann Able", Term("lower", 5, "2025-01-06", "2025-06-30"))])


def test_unmatched_event_aborts_the_import(make_db, curation) -> None:
    curation(events_json={"p1": [{"end": "2030-01-01", "label": "Resigned"}]})
    with pytest.raises(RuntimeError, match="match no imported term"):
        run(make_db, [person("p1", "Ann Able", Term("lower", 5, "2025-01-06", None))])
