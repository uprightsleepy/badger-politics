"""Municipalities share imports while keeping their verified identities and vocabulary."""

import json

import pytest
from test_import_local import build, event_file, item, office, vote

from importer.import_local import TABLES, run
from importer.local_registry import TENANTS
from importer.roster import load_curation


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


@pytest.mark.parametrize("tenant,person_id,seat", [
    ("cityofappleton", 542, 1), ("cityofappleton", 544, 15),
    ("waukesha", 548, 1), ("waukesha", 600, 15),
])
def test_new_cities_use_the_shared_importer_and_curated_ids(
    tmp_path, make_db, tenant, person_id, seat,
):
    conn = build(tmp_path, make_db, extra_tenants={tenant: {
        "office": [office(person_id, "Recorded Name", "Alderperson"),
                   office(99999, "Recorded Name", "Alderperson")],
        "events": [event_file(1, "2025-01-14", [item(7)],
                              {"7": [vote(person_id, "Recorded Name", "Nay")]})],
    }})
    assert conn.execute("SELECT seat FROM local_members WHERE tenant=? AND person_id=?",
                        (tenant, person_id)).fetchone() == (seat,)
    assert conn.execute("SELECT seat FROM local_members WHERE tenant=? AND person_id=99999",
                        (tenant,)).fetchone() == (None,)
    assert conn.execute("SELECT value FROM local_votes WHERE tenant=?", (tenant,)
                        ).fetchone() == ("Nay",)


def test_curated_new_city_rosters_cover_fifteen_distinct_districts():
    from importer.import_local import SEATS_PATH

    seats = load_curation(SEATS_PATH)
    for tenant in ("cityofappleton", "waukesha"):
        assert sorted(entry["seat"] for entry in seats[tenant].values()) == list(range(1, 16))
        spec = next(s for s in TENANTS if s["tenant"] == tenant)
        assert spec["max_new_per_run"] == 2
        assert spec["since"] == 2025
