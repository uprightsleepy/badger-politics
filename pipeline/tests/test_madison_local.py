"""Madison uses recorded identities and explicit coverage, never inferred votes."""

import json

import pytest
from test_import_local import build, event_file, item, office, vote

from importer.import_local import TABLES, run


def test_madison_person_url_assigns_only_its_own_district(tmp_path, make_db):
    conn = build(tmp_path, make_db, madison_office=[
        office(9, "Pat Example", None), office(10, "Pat Example", None),
        office(11, "Mayor Example", "Mayor"),
    ], persons={"madison": {"9": {
        "PersonWWW": "http://www.cityofmadison.com/council/district3/",
    }}})
    assert conn.execute(
        "SELECT person_id, seat, seat_basis FROM local_members WHERE tenant='madison'"
        " ORDER BY person_id"
    ).fetchall() == [
        (9, 3, "https://www.cityofmadison.com/council/district3/"),
        (10, None, None), (11, None, None),
    ]


@pytest.mark.parametrize("url", [
    "https://www.cityofmadison.com.example/council/district3/",
    "https://www.cityofmadison.com/council/district3/?district=4",
    "https://other.example/council/district3/", "", None,
])
def test_unverified_district_url_stays_unknown(tmp_path, make_db, url):
    conn = build(tmp_path, make_db, madison_office=[office(9, "Pat Example", None)],
                 persons={"madison": {"9": {"PersonWWW": url}}})
    assert conn.execute("SELECT seat FROM local_members").fetchone() == (None,)


@pytest.mark.parametrize("seat", [0, 21, 99])
def test_out_of_range_district_is_rejected(tmp_path, make_db, seat):
    with pytest.raises(RuntimeError, match="out of range"):
        build(tmp_path, make_db, madison_office=[office(9, "Pat Example", None)],
              persons={"madison": {"9": {
                  "PersonWWW": f"https://www.cityofmadison.com/council/district{seat}/",
              }}})


def test_tenant_ids_remain_distinct_and_voice_votes_remain_unattributed(tmp_path, make_db):
    def meeting(value):
        return event_file(1, "2025-01-14", [item(7), item(8, EventItemPassedFlag=1)],
                          {"7": [vote(9, "Pat Example", value)], "8": []})

    conn = build(tmp_path, make_db, milwaukee_events=[meeting("Aye")],
                 westallis_events=[meeting("No")], madison_events=[meeting("Abstain")])
    assert conn.execute("SELECT tenant, person_id, value FROM local_votes ORDER BY tenant"
                        ).fetchall() == [
        ("madison", 9, "Abstain"), ("milwaukee", 9, "Aye"), ("westalliswi", 9, "No"),
    ]
    assert conn.execute("SELECT COUNT(*) FROM local_actions WHERE event_item_id=8"
                        ).fetchone() == (3,)
    assert conn.execute("SELECT COUNT(*) FROM local_votes WHERE event_item_id=8"
                        ).fetchone() == (0,)


@pytest.mark.parametrize("invalid", [None, {}, {
    "since": 2025, "listed_meetings": 2, "pending_meetings": 3,
    "checked_at": "2026-09-08T00:00:00+00:00",
}, {
    "since": 2025, "listed_meetings": 2, "pending_meetings": 1,
    "checked_at": "2026-09-08T00:00:00",
}])
def test_bad_coverage_rolls_back_all_existing_council_data(tmp_path, make_db, invalid):
    conn = build(tmp_path, make_db, milwaukee_office=[office(9, "Pat Example", "3rd District")])
    before = {t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in (*TABLES, "meta")}
    coverage = tmp_path / "local/madison/coverage.json"
    if invalid is None:
        coverage.unlink()
    else:
        coverage.write_text(json.dumps(invalid))
    with pytest.raises(ValueError):
        run(tmp_path / "local", tmp_path / "wi.sqlite")
    after = {t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in (*TABLES, "meta")}
    assert after == before
