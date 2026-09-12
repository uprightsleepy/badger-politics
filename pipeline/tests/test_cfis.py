"""CFIS committee matching never guesses; archive import stays referential."""

import json
from pathlib import Path

import pytest

from importer.import_cfis import run as import_run
from scraper.fetch_cfis import match_committees


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


def test_import_rejects_unknown_person(tmp_path: Path, make_db) -> None:
    db = tmp_path / "wi.sqlite"
    conn = make_db(db)
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


def test_month_windows_run_to_each_month_last_instant() -> None:
    from scraper.cfis_api import month_windows

    windows = month_windows("2025-11", "2026-01")
    assert [w[0] for w in windows] == ["2025-11", "2025-12", "2026-01"]
    # a bare date bound parses as midnight and drops the last day's rows
    assert windows[0][1:] == ("2025-11-01", "2025-11-30T23:59:59")
    assert windows[1][2] == "2025-12-31T23:59:59"


def test_retained_filers_ride_along_with_the_curated_one(tmp_path, make_db, monkeypatch):
    from scraper import fetch_cfis

    db = tmp_path / "wi.sqlite"
    conn = make_db(db)
    conn.execute("INSERT INTO people (id, name, current_role)"
                 " VALUES ('p1', 'Example Member', 'Representative')")
    conn.commit()
    conn.close()
    mapping = tmp_path / "committee_map.json"
    curated = tmp_path / "curated.json"
    curated.write_text(json.dumps({"p1": {
        "entity_id": 20, "committee": "Verified filing committee",
    }}))
    retained = tmp_path / "retained.json"
    retained.write_text(json.dumps({"p1": [
        {"entity_id": 10, "committee": "Friends of Example Member", "matched": "auto"},
        {"entity_id": 20, "committee": "Verified filing committee", "matched": "auto"},
    ]}))
    monkeypatch.setattr(fetch_cfis, "MAP_PATH", mapping)
    monkeypatch.setattr(fetch_cfis, "CURATED_PATH", curated)
    monkeypatch.setattr(fetch_cfis, "RETAINED_PATH", retained)
    monkeypatch.setattr(fetch_cfis, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fetch_cfis, "load_person_details", lambda: {})
    monkeypatch.setattr(fetch_cfis, "session", lambda: None)
    fetch_cfis.build_map(db)
    rows = json.loads(mapping.read_text())
    # the retained filer once, the curated filer once, nothing carried from any old map
    assert [(r["entity_id"], r["matched"]) for r in rows] == [(10, "retained"), (20, "curated")]


def test_retained_filer_failing_the_name_rules_stops_the_run(tmp_path, make_db, monkeypatch):
    from scraper import fetch_cfis

    db = tmp_path / "wi.sqlite"
    conn = make_db(db)
    conn.execute("INSERT INTO people (id, name, current_role)"
                 " VALUES ('p1', 'Example Member', 'Representative')")
    conn.commit()
    conn.close()
    mapping = tmp_path / "committee_map.json"
    mapping.write_text("[]")
    curated = tmp_path / "curated.json"
    curated.write_text(json.dumps({"p1": {"entity_id": 20, "committee": "Verified filer"}}))
    retained = tmp_path / "retained.json"
    retained.write_text(json.dumps({"p1": [
        {"entity_id": 10, "committee": "Someone Else for Senate", "matched": "auto"},
    ]}))
    monkeypatch.setattr(fetch_cfis, "MAP_PATH", mapping)
    monkeypatch.setattr(fetch_cfis, "CURATED_PATH", curated)
    monkeypatch.setattr(fetch_cfis, "RETAINED_PATH", retained)
    monkeypatch.setattr(fetch_cfis, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fetch_cfis, "load_person_details", lambda: {})
    monkeypatch.setattr(fetch_cfis, "session", lambda: None)
    with pytest.raises(ValueError, match="no longer passes the name rules"):
        fetch_cfis.build_map(db)
    assert mapping.read_text() == "[]"


def test_curated_conflicting_owner_leaves_previous_map_intact(tmp_path, make_db, monkeypatch):
    from scraper import fetch_cfis

    db = tmp_path / "wi.sqlite"
    conn = make_db(db)
    conn.executemany("INSERT INTO people (id, name, current_role)"
                     " VALUES (?, ?, 'Representative')", [("p1", "First"), ("p2", "Second")])
    conn.commit()
    conn.close()
    mapping = tmp_path / "committee_map.json"
    mapping.write_text("[]")
    curated = tmp_path / "curated.json"
    curated.write_text(json.dumps({person: {"entity_id": 20, "committee": "Conflicting filer"}
                                   for person in ["p1", "p2"]}))
    monkeypatch.setattr(fetch_cfis, "MAP_PATH", mapping)
    monkeypatch.setattr(fetch_cfis, "CURATED_PATH", curated)
    monkeypatch.setattr(fetch_cfis, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fetch_cfis, "load_person_details", lambda: {})
    monkeypatch.setattr(fetch_cfis, "session", lambda: None)
    with pytest.raises(ValueError, match="multiple legislators"):
        fetch_cfis.build_map(db)
    assert mapping.read_text() == "[]"


def test_search_hits_cached_a_week_while_the_map_is_rederived_nightly(
        tmp_path, make_db, monkeypatch):
    from datetime import date as real_date

    from scraper import fetch_cfis

    db = tmp_path / "wi.sqlite"
    conn = make_db(db)
    conn.executemany("INSERT INTO people (id, name, current_role)"
                     " VALUES (?, ?, 'Representative')",
                     [("p1", "Alex Example"), ("p2", "Blake Sample")])
    conn.commit()
    conn.close()
    # surname queries are normalized to lowercase before the search
    hits = {"Alex Example": [{"id": 10, "name": "Friends of Alex Example"}], "example": [],
            "Blake Sample": [], "sample": [{"id": 11, "name": "Blake Sample for Assembly"}]}
    calls = []

    def search(http, proc, payload):
        calls.append(payload["searchQuery"])
        return hits[payload["searchQuery"]]

    class Day(real_date):
        current = real_date(2026, 9, 14)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(fetch_cfis, "call", search)
    monkeypatch.setattr(fetch_cfis, "date", Day)
    monkeypatch.setattr(fetch_cfis.time, "sleep", lambda _: None)
    monkeypatch.setattr(fetch_cfis, "MAP_PATH", tmp_path / "committee_map.json")
    monkeypatch.setattr(fetch_cfis, "CURATED_PATH", tmp_path / "curated.json")
    monkeypatch.setattr(fetch_cfis, "RETAINED_PATH", tmp_path / "retained.json")
    monkeypatch.setattr(fetch_cfis, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fetch_cfis, "load_person_details", lambda: {})
    monkeypatch.setattr(fetch_cfis, "session", lambda: None)

    def mapped():
        return [(r["person_id"], r["entity_id"]) for r in
                json.loads((tmp_path / "committee_map.json").read_text())]

    fetch_cfis.build_map(db)
    assert len(calls) == 4 and mapped() == [("p1", 10), ("p2", 11)]
    # the next nights read the cached hits; one member's queries are due each week
    refetched = []
    for offset in range(1, 8):
        Day.current = real_date(2026, 9, 14 + offset)
        calls.clear()
        fetch_cfis.build_map(db)
        refetched.extend(calls)
    assert sorted(refetched) == sorted(hits), "every query is re-read exactly once a week"
    # a cached hit that stops matching leaves the map on the next derivation
    cache = json.loads((tmp_path / "search_cache.json").read_text())
    cache["sample"]["hits"] = [{"id": 11, "name": "Someone Else for Assembly"}]
    (tmp_path / "search_cache.json").write_text(json.dumps(cache))
    Day.current = real_date(2026, 9, 22)
    fetch_cfis.build_map(db)
    assert mapped() == [("p1", 10)]
