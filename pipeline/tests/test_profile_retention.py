"""Paused profile retrieval preserves source records and discloses their freshness."""

import copy
import json
from datetime import datetime

import pytest
from test_import_local import build, event_file, item, office, vote

from dataproducts.queries import meta
from importer.import_local import milwaukee_profile_owners, run
from importer.local_registry import TENANTS
from nightly.stages import commands
from scraper import fetch_local_profiles as collector
from scraper.source_access import SourceAccess, SourceAccessError


def archived_profiles():
    return {"milwaukee": {"seats": {
        str(n): {"page": f"{collector.MKE_BASE}/CommonCouncil/Council-Members/District{n}",
                 "photos": [{"src": f"{collector.MKE_BASE}/ImageLibrary/Groups/ccCouncil/{n}.jpg",
                             "alt": f"Photo of District {n}"}],
                 "mailto": [f"example{n}@milwaukee.gov"], "tel": ["4145550100"]}
        for n in collector.MKE_DISTRICTS
    }}, "westalliswi": {"districts": {"1": {"page": "old", "entries": []}}},
        "extra_provenance": {"keep": True}}


OWNERS = {str(n): n for n in range(1, 16)}


@pytest.fixture
def archive(tmp_path, monkeypatch):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(archived_profiles()), encoding="utf-8")
    (tmp_path / "milwaukee").mkdir()
    (tmp_path / "milwaukee/officerecords.json").write_text(json.dumps([
        office(n, f"Example {n}", f"{n}th District") for n in collector.MKE_DISTRICTS
    ]))
    access = SourceAccess()
    assert access.policies["city.milwaukee.gov"].get("paused")
    monkeypatch.setattr(collector, "ACCESS", access)
    monkeypatch.setattr(collector, "DATA_DIR", tmp_path)
    monkeypatch.setattr(collector, "OUT", path)
    monkeypatch.setattr(collector, "http_session", lambda: object())
    monkeypatch.setattr(collector, "PROFILE_SOURCES", [])
    monkeypatch.setattr(collector, "milwaukee_district",
                        lambda *args: pytest.fail("paused request"))
    monkeypatch.setattr(collector, "west_allis_district", lambda http, n, delay: {
        "page": collector.WA_PAGES[n], "entries": [{"heading": f"Example {n}", "image": None,
                                                  "emails": [], "phones": []}],
    })
    return path


def test_paused_source_preserves_all_districts_and_unknown_refresh_date(archive):
    before = json.loads(archive.read_text())
    collector.main([])
    after = json.loads(archive.read_text())
    assert after["milwaukee"] == before["milwaukee"]
    assert after["extra_provenance"] == before["extra_provenance"]
    assert after["_refresh"]["milwaukee"] == {
        "state": "retained", "last_success_at": None, "person_ids": OWNERS,
    }
    assert set(after["westalliswi"]["districts"]) == {str(n) for n in range(1, 6)}
    for n in range(1, 6):
        assert after["westalliswi"]["districts"][str(n)]["page"] == collector.WA_PAGES[n]
    stamp = after["_refresh"]["westalliswi"]
    assert stamp["state"] == "refreshed"
    assert datetime.fromisoformat(stamp["last_success_at"]).tzinfo is not None
    assert not archive.with_suffix(".json.tmp").exists()


def test_retention_does_not_advance_a_known_collection_date(archive):
    before = json.loads(archive.read_text())
    before["_refresh"] = {"milwaukee": {
        "state": "refreshed", "last_success_at": "2026-09-01T12:00:00+00:00",
    }}
    archive.write_text(json.dumps(before))
    collector.main([])
    (archive.parent / "milwaukee/officerecords.json").write_text("[]")
    collector.main([])
    status = json.loads(archive.read_text())["_refresh"]["milwaukee"]
    assert status == {"state": "retained", "last_success_at": "2026-09-01T12:00:00+00:00",
                      "person_ids": OWNERS}


@pytest.mark.parametrize("problem", ["missing", "district", "page", "photos", "mailto", "tel"])
def test_missing_or_malformed_archive_stops_before_any_collection(archive, monkeypatch, problem):
    data = json.loads(archive.read_text())
    if problem == "missing":
        archive.unlink()
    else:
        if problem == "district":
            del data["milwaukee"]["seats"]["15"]
        else:
            data["milwaukee"]["seats"]["1"][problem] = None
        archive.write_text(json.dumps(data))
    before = archive.read_bytes() if archive.exists() else None
    monkeypatch.setattr(collector, "west_allis_district",
                        lambda *args: pytest.fail("unexpected fetch"))
    with pytest.raises(RuntimeError, match="archiv"):
        collector.main([])
    assert (archive.read_bytes() if archive.exists() else None) == before


def test_other_source_failure_leaves_entire_archive_untouched(archive, monkeypatch):
    before = archive.read_bytes()
    def denied(*args):
        raise SourceAccessError("West Allis denied")
    monkeypatch.setattr(collector, "west_allis_district", denied)
    with pytest.raises(SourceAccessError, match="West Allis"):
        collector.main([])
    assert archive.read_bytes() == before


def test_access_gate_still_denies_paused_milwaukee_requests():
    with pytest.raises(SourceAccessError, match="Collection paused"):
        SourceAccess().source(collector.MKE_BASE + "/CommonCouncil/CouncilMembers/District1")


def test_reviewed_reactivation_restores_collection_and_clears_retained_status(archive, monkeypatch):
    collector.main([])
    collector.ACCESS.policies["city.milwaukee.gov"].pop("paused")
    seen = []
    def fetch(http, n, delay):
        seen.append(n)
        return copy.deepcopy(archived_profiles()["milwaukee"]["seats"][str(n)])
    monkeypatch.setattr(collector, "milwaukee_district", fetch)
    collector.main([])
    after = json.loads(archive.read_text())
    assert seen == list(collector.MKE_DISTRICTS)
    assert after["_refresh"]["milwaukee"]["state"] == "refreshed"
    assert after["_refresh"]["milwaukee"]["last_success_at"]


def test_import_adds_notice_metadata_without_changing_attribution_or_votes(
    tmp_path, make_db, monkeypatch,
):
    monkeypatch.setattr("importer.import_local.TENANTS", [s for s in TENANTS
                                                       if s.get("provider") != "civicclerk"])
    profiles = archived_profiles()
    conn = build(tmp_path, make_db, profiles=profiles,
                 milwaukee_office=[office(1, "Example", "1st District")],
                 milwaukee_events=[event_file(1, "2025-01-01", [item(10)],
                                             {"10": [vote(1, "Example")]})])
    tables = ("local_members", "local_member_terms", "local_events", "local_actions", "local_votes")
    before = {t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables}
    profiles["_refresh"] = {"milwaukee": {
        "state": "retained", "last_success_at": None, "person_ids": OWNERS,
    }}
    (tmp_path / "local/profiles.json").write_text(json.dumps(profiles))
    run(tmp_path / "local", tmp_path / "wi.sqlite")
    assert {t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in tables} == before
    value = conn.execute(
        "SELECT value FROM meta WHERE key='local_profiles_milwaukee'"
    ).fetchone()[0]
    assert json.loads(value) == profiles["_refresh"]["milwaukee"]
    assert meta(conn)["local_profiles_milwaukee"] == value
    assert conn.execute("PRAGMA quick_check").fetchone() == ("ok",)
    conn.close()


def test_replacement_member_cannot_inherit_retained_profile(tmp_path, make_db):
    profiles = archived_profiles()
    profiles["_refresh"] = {"milwaukee": {
        "state": "retained", "last_success_at": None, "person_ids": OWNERS,
    }}
    conn = build(tmp_path, make_db, profiles=profiles,
                 milwaukee_office=[office(999, "Example", "1st District")],
                 persons={"milwaukee": {"999": {"PersonEmail": "current@milwaukee.gov"}}})
    assert conn.execute(
        "SELECT image_url, image_basis, email, phone FROM local_members"
    ).fetchone() == (
        None, None, "current@milwaukee.gov", None,
    )
    assert json.loads((tmp_path / "local/profiles.json").read_text()) == profiles
    conn.close()


def test_ambiguous_original_owner_stops_retention(archive):
    path = archive.parent / "milwaukee/officerecords.json"
    records = json.loads(path.read_text())
    records.append(office(999, "Other", "1st District"))
    path.write_text(json.dumps(records))
    with pytest.raises(ValueError, match="Ambiguous"):
        milwaukee_profile_owners(archive.parent)


def test_retention_runs_before_roster_refresh(tmp_path):
    context = {"finance_as_of": "2026-09-08"}
    modules = [command[0] for command in commands("community", tmp_path, "2026", context)]
    assert modules.index("scraper.fetch_local_profiles") < modules.index(
        "scraper.fetch_local_votes"
    )


@pytest.mark.parametrize("status", [None, {"state": "unknown"}, {"state": "refreshed"},
                                    {"state": "retained", "last_success_at": "yesterday"},
                                    {"state": "retained", "person_ids": {}},
                                    {"state": "retained", "person_ids": dict.fromkeys(OWNERS, 1)}])
def test_invalid_freshness_metadata_cannot_replace_existing_database(tmp_path, make_db, status):
    conn = build(tmp_path, make_db, milwaukee_office=[office(9, "Example", "1st District")])
    before = conn.execute("SELECT * FROM local_members").fetchall()
    (tmp_path / "local/profiles.json").write_text(json.dumps({"_refresh": {"milwaukee": status}}))
    with pytest.raises(ValueError):
        run(tmp_path / "local", tmp_path / "wi.sqlite")
    assert conn.execute("SELECT * FROM local_members").fetchall() == before
    conn.close()
