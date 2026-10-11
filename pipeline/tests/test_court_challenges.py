"""Curated court challenges resolve exactly, or the run stops."""

import json
import sqlite3
from pathlib import Path

import pytest

from importer import court_challenges
from importer.checks import check_court_challenges
from scraper import fetch_court_dockets
from scraper.source_access import SourceAccess, SourceAccessError

RAW = {
    "id": 4242, "court_id": "wiwd", "case_name": "Doe v. Evers", "docket_number": "3:25-cv-1",
    "date_filed": "2025-02-03", "date_terminated": None,
    "date_last_filing": "2026-09-30T14:00:00-05:00", "absolute_url": "/docket/4242/doe-v-evers/",
}
ENTRY = {"docket": 4242, "bills": ["2025-ab1"], "basis": "https://example.org/complaint.pdf",
         "verified": "2026-10-11"}


@pytest.fixture()
def setup(tmp_path: Path, make_db):
    db = tmp_path / "wi.sqlite"
    conn = make_db(db)
    conn.execute("INSERT INTO sessions (id, identifier) VALUES ('2025', '2025')")
    conn.executemany("INSERT INTO bills (id, session_id, identifier, status) VALUES (?, ?, ?, ?)",
                     [("2025-ab1", "2025", "AB 1", "enacted"),
                      ("2025-ab2", "2025", "AB 2", "vetoed")])
    conn.commit()
    conn.close()
    curation = tmp_path / "curation.json"
    dockets = tmp_path / "court-dockets.json"
    dockets.write_text(json.dumps({"dockets": [court_challenges.docket_record(RAW, 4242)]}))

    def write(*entries):
        curation.write_text(json.dumps({"challenges": list(entries)}))
    return db, curation, dockets, write


def test_curated_challenge_imports_and_passes_the_gate(setup):
    db, curation, dockets, write = setup
    write(ENTRY)
    court_challenges.run(dockets, db, curation)
    with sqlite3.connect(db) as wi:
        row = wi.execute("SELECT court, case_name, date_last_filing, url FROM court_challenges"
                         ).fetchone()
        assert row == ("U.S. District Court, Western District of Wisconsin", "Doe v. Evers",
                       "2026-09-30", "https://www.courtlistener.com/docket/4242/doe-v-evers/")
        assert check_court_challenges(wi, curation) == []
        write()  # an uncurated row fails the gate
        assert check_court_challenges(wi, curation)


@pytest.mark.parametrize("entry, message", [
    ({**ENTRY, "docket": 9}, "missing from the archive"),
    ({**ENTRY, "bills": ["2025-ab9"]}, "not an enacted bill"),
    ({**ENTRY, "bills": ["2025-ab2"]}, "not an enacted bill"),
    ({**ENTRY, "basis": ""}, "basis"),
])
def test_unresolved_curation_fails_the_import(setup, entry, message):
    db, curation, dockets, write = setup
    write(entry)
    with pytest.raises(ValueError, match=message):
        court_challenges.run(dockets, db, curation)


def test_gate_fails_when_a_curated_docket_was_not_imported(setup):
    db, curation, _, write = setup
    write(ENTRY)
    with sqlite3.connect(db) as wi:
        assert check_court_challenges(wi, curation) == [
            "court challenge docket 4242 on 2025-ab1 did not resolve"]


@pytest.mark.parametrize("change", [
    {"id": 1}, {"court_id": "wisc"}, {"case_name": " "}, {"absolute_url": "https://x/docket/1/"},
])
def test_unexpected_docket_records_stop(change):
    with pytest.raises(ValueError):
        court_challenges.docket_record({**RAW, **change}, 4242)


def test_shipped_curation_is_valid():
    court_challenges.curated()


def test_empty_curation_writes_an_archive_without_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_court_dockets, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fetch_court_dockets, "curated", lambda: [])
    monkeypatch.setattr(fetch_court_dockets, "session", lambda: pytest.fail("no request"))
    monkeypatch.delenv("COURTLISTENER_TOKEN", raising=False)
    assert fetch_court_dockets.main() == 0
    assert json.loads((tmp_path / "court-dockets.json").read_text())["dockets"] == []


def test_curated_dockets_without_a_token_fail_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_court_dockets, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fetch_court_dockets, "curated", lambda: [ENTRY])
    monkeypatch.delenv("COURTLISTENER_TOKEN", raising=False)
    with pytest.raises(SystemExit, match="COURTLISTENER_TOKEN"):
        fetch_court_dockets.main()
    assert not (tmp_path / "court-dockets.json").exists()


def test_courtlistener_stays_paused_until_reviewed():
    with pytest.raises(SourceAccessError, match="paused"):
        SourceAccess().source(court_challenges.API.format(4242))
