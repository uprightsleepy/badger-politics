"""CivicClerk attribution, nested motions, bounded collection and archive safety."""

import copy
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from importer import import_local
from importer.civicclerk import adapt_meeting, identity_index, parse_roster, roster_members
from importer.local_registry import TENANTS
from scraper import fetch_civicclerk as fetch
from scraper.http import save_json
from scraper.source_access import SourceAccess, SourceAccessError

SPEC = {**next(s for s in TENANTS if s["tenant"] == "greenbaywi"),
        "seats": 2, "bootstrap_event_id": None}
CURATED = {
    "1": {"name": "Pat Example", "aliases": ["Patrick Example"], "seat": 1,
          "basis": SPEC["roster_url"]},
    "2": {"name": "Lee Another", "seat": 2, "basis": SPEC["roster_url"]},
}
ROSTER_HTML = "<h3>Pat Example, District 1</h3><h3>Lee Another, District 2</h3>"


def roster():
    return {"source_url": SPEC["roster_url"], "checked_at": datetime.now(UTC).isoformat(),
            "members": parse_roster(ROSTER_HTML)}


def test_roster_portraits_require_unique_full_names_and_same_origin():
    page = ROSTER_HTML + '''
    <img src="/ImageRepository/Document?documentID=1" alt=" Pat Example ">
    <img src="/ImageRepository/Document?documentID=2" alt="Lee Another">
    <img src="/ImageRepository/Document?documentID=3" alt="Lee Another">
    <img src="/wrong.jpg" alt="Example">
    <img src="/logo.png" alt="City logo">
    '''
    members = parse_roster(page, SPEC["roster_url"])
    assert members[0]["portrait"] == {
        "url": "https://www.greenbaywi.gov/ImageRepository/Document?documentID=1",
        "name": "Pat Example",
    }
    assert "portrait" not in members[1]
    for src in ("https://another.example/headshot.jpg", "javascript:alert(1)",
                "data:image/png;base64,AAA", "http://www.greenbaywi.gov/photo.jpg"):
        assert "portrait" not in parse_roster(
            ROSTER_HTML + f'<img src="{src}" alt="Pat Example">', SPEC["roster_url"],
        )[0]
    assert "portrait" not in parse_roster(
        '<h3>New Member, District 1</h3><img src="/old.jpg" alt="Pat Example">',
        SPEC["roster_url"],
    )[0]


@pytest.mark.parametrize("portrait", [
    {"name": "Another Person", "url": "https://www.greenbaywi.gov/photo.jpg"},
    {"name": "Pat Example", "url": "https://unreviewed.example/photo.jpg"},
])
def test_roster_rejects_misattributed_archived_portrait(portrait):
    snapshot = roster()
    snapshot["members"][0]["portrait"] = portrait
    with pytest.raises(ValueError, match="portrait attribution"):
        roster_members(snapshot, SPEC, CURATED)


def test_official_roster_portraits_reach_shared_import(source, tmp_path, make_db, monkeypatch):
    fetch.fetch_tenant(source.http, SPEC, [-1], source.root)
    snapshot = roster()
    snapshot["members"] = parse_roster(
        ROSTER_HTML + '<img src="/ImageRepository/Document?documentID=1" alt="Pat Example">',
        SPEC["roster_url"],
    )
    save_json(source.out / "roster.json", snapshot)
    before = {p: p.read_bytes() for p in source.out.rglob("*.json")}
    db = tmp_path / "portraits.sqlite"
    conn = make_db(db)
    monkeypatch.setattr(import_local, "TENANTS", [SPEC])
    import_local.run(source.root, db)
    photos = conn.execute(
        "SELECT image_url,image_basis FROM local_members ORDER BY seat").fetchall()
    assert photos == [
        (snapshot["members"][0]["portrait"]["url"], SPEC["roster_url"]), (None, None),
    ]
    assert conn.execute("SELECT COUNT(*) FROM local_votes").fetchone() == (8,)
    assert conn.execute("SELECT COUNT(*) FROM local_actions").fetchone() == (6,)
    assert {p: p.read_bytes() for p in before} == before
    conn.close()


def event(event_id=11):
    return {"id": event_id, "agendaId": event_id + 100, "eventCategoryId": 26,
            "eventDate": "2026-07-21T18:00:00Z", "isPublished": "Published",
            "isDeleted": False, "hasAgenda": True, "publishedFiles": [
                {"type": "Minutes", "fileId": 500, "publishOn": "2026-07-23T12:00:00Z"},
            ]}


def motion(**kwargs):
    return {"motionName": "approve", "passFail": 1, "initiatedBy": "Pat Example",
            "secondedBy": "Lee Another", "yesVotes": ["Patrick Example"],
            "noVotes": ["Lee Another"], "abstainVotes": [], **kwargs}


def item(item_id, motions=(), children=()):
    return {"id": item_id, "agendaObjectId": 0, "eventId": 0,
            "agendaObjectItemName": "Example item", "hasVote": False, "hasMotion": False,
            "minutesItemVotes": list(motions), "childItems": list(children)}


def archive(event_id=11):
    return {"provider": "civicclerk", "version": 1, "event": event(event_id),
            "checked_at": datetime.now(UTC).isoformat(),
            "meeting": {"id": event_id + 100, "items": [
                item(event_id * 10, children=[item(event_id * 10 + 1, [
                    motion(passFail=0),
                    motion(yesVotes=[], abstainVotes=["Pat Example"]),
                    motion(yesVotes=[], noVotes=[]),
                ])]),
            ]}}


def test_all_nested_motions_and_positions_survive_false_summary_flags():
    data = archive()
    before = copy.deepcopy(data)
    result = adapt_meeting(data, SPEC, CURATED)
    assert data == before
    assert [i["EventItemId"] for i in result["items"]] == [111001, 111002, 111003]
    assert [i["EventItemPassedFlag"] for i in result["items"]] == [0, 1, 1]
    assert [[(v["VotePersonId"], v["VoteValueName"]) for v in row]
            for row in result["votes"].values()] == [
        [(1, "Yes"), (2, "No")], [(2, "No"), (1, "Abstain")], [],
    ]
    assert result["rollcalls"] == {}
    assert result["event"]["EventMinutesStatusName"] == "Published"
    assert result["event"]["EventInSiteURL"].endswith("/event/11/files")
    assert result["items"][0]["EventItemMoverId"] == 1


@pytest.mark.parametrize("changes", [
    {"noVotes": ["Pat Example"]}, {"yesVotes": ["Patrick Example", "Pat Example"]},
    {"yesVotes": ["P. Example"]}, {"yesVotes": ["Example"]}, {"yesVotes": [""]},
    {"yesVotes": None}, {"passFail": 2}, {"passFail": True}, {"motionName": ""},
    {"initiatedBy": "Unknown Member"},
    {"recusedVotes": ["Pat Example"]},
])
def test_ambiguous_missing_or_unreviewed_facts_fail_instead_of_dropping_votes(changes):
    data = archive()
    data["meeting"]["items"][0]["childItems"][0]["minutesItemVotes"][0].update(changes)
    with pytest.raises(ValueError):
        adapt_meeting(data, SPEC, CURATED)


def test_ambiguous_aliases_and_changed_rosters_fail():
    curated = copy.deepcopy(CURATED)
    curated["2"]["aliases"] = ["Patrick Example"]
    with pytest.raises(ValueError, match="Ambiguous"):
        identity_index(curated)
    snapshot = roster()
    snapshot["members"][0]["seat"] = 2
    with pytest.raises(ValueError, match="roster changed"):
        roster_members(snapshot, SPEC, CURATED)
    snapshot = roster()
    snapshot["members"].pop()
    with pytest.raises(ValueError, match="Incomplete"):
        roster_members(snapshot, SPEC, CURATED)


@pytest.mark.parametrize("field,value", [("id", 12), ("eventCategoryId", 27),
                                        ("eventDate", "2026-06-01T18:00:00Z"),
                                        ("isPublished", "Draft"), ("isDeleted", True)])
def test_out_of_scope_or_mismatched_events_fail(field, value):
    data = archive()
    if field == "id":
        data["meeting"]["id"] = value
    else:
        data["event"][field] = value
    with pytest.raises(ValueError):
        adapt_meeting(data, SPEC, CURATED)


def test_duplicate_and_mismatched_item_ids_fail():
    data = archive()
    data["meeting"]["items"].append(copy.deepcopy(data["meeting"]["items"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        adapt_meeting(data, SPEC, CURATED)
    for field in ("agendaObjectId", "eventId"):
        data = archive()
        data["meeting"]["items"][0][field] = 999
        with pytest.raises(ValueError, match="mismatched"):
            adapt_meeting(data, SPEC, CURATED)


@pytest.fixture
def source(tmp_path, monkeypatch):
    curation = tmp_path / "seats.json"
    save_json(curation, {"greenbaywi": CURATED})
    monkeypatch.setattr(fetch, "SEATS_PATH", curation)
    monkeypatch.setattr(import_local, "SEATS_PATH", curation)
    records = [archive(n) for n in (13, 12, 11)]
    calls = []

    def get(url, params, timeout):
        calls.append((url, params))
        if url == SPEC["roster_url"]:
            return SimpleNamespace(text=ROSTER_HTML, raise_for_status=lambda: None)
        if url.endswith("/Events"):
            skip, top = params["$skip"], params["$top"]
            data = {"value": [r["event"] for r in records][skip:skip + top]}
        else:
            data = next(r["meeting"] for r in records if url.endswith(f"/{r['meeting']['id']}"))
        return SimpleNamespace(json=lambda: copy.deepcopy(data), raise_for_status=lambda: None)

    return SimpleNamespace(http=SimpleNamespace(get=get), records=records, calls=calls,
                           root=tmp_path / "local", out=tmp_path / "local/greenbaywi")


def test_collection_pages_caps_backfills_and_reuses_cached_meetings(source, monkeypatch):
    monkeypatch.setattr(fetch, "PAGE", 2)
    assert fetch.fetch_tenant(source.http, SPEC, [-1], source.root) == (2, 0)
    coverage = json.loads((source.out / "coverage.json").read_text())
    assert (coverage["listed_meetings"], coverage["pending_meetings"]) == (3, 1)
    assert coverage["start_date"] == "2026-07-01"
    assert len(list(source.out.glob("event_*.json"))) == 2
    assert fetch.fetch_tenant(source.http, SPEC, [-1], source.root) == (1, 2)
    assert fetch.fetch_tenant(source.http, SPEC, [-1], source.root) == (0, 3)
    assert len([url for url, _ in source.calls if "/Meetings/" in url]) == 3


def test_shared_budget_applies_to_civicclerk(source):
    budget = [1]
    assert fetch.fetch_tenant(source.http, SPEC, budget, source.root) == (1, 0)
    assert budget == [0]


def test_changed_event_metadata_refreshes_and_preserves_original_revision(source):
    fetch.fetch_tenant(source.http, SPEC, [-1], source.root)
    source.records[0]["event"]["publishedFiles"][0]["fileId"] = 501
    assert fetch.fetch_tenant(source.http, SPEC, [-1], source.root) == (2, 1)
    files = list((source.out / "revisions/event_13").glob("*.json"))
    assert {json.loads(p.read_text())["event"]["publishedFiles"][0]["fileId"]
            for p in files} == {500, 501}


def test_denial_keeps_existing_meeting_bytes(source, monkeypatch):
    fetch.fetch_tenant(source.http, SPEC, [-1], source.root)
    before = {p: p.read_bytes() for p in source.out.glob("event_*.json")}

    def denied(*args, **kwargs):
        raise SourceAccessError("Rate limit response")

    monkeypatch.setattr(source.http, "get", denied)
    with pytest.raises(SourceAccessError, match="Rate limit"):
        fetch.fetch_tenant(source.http, SPEC, [-1], source.root)
    assert {p: p.read_bytes() for p in before} == before


def test_bootstrap_is_required_on_first_collection(source):
    with pytest.raises(ValueError, match="bootstrap"):
        fetch.fetch_tenant(source.http, {**SPEC, "bootstrap_event_id": 999}, [-1], source.root)
    assert not list(source.out.glob("event_*.json"))


def test_refresh_cannot_remove_votes_and_keeps_candidate_for_review(source):
    fetch.fetch_tenant(source.http, SPEC, [-1], source.root)
    dest = source.out / "event_13.json"
    held = json.loads(dest.read_text())
    held["checked_at"] = "2000-01-01T00:00:00+00:00"
    save_json(dest, held)
    before = dest.read_bytes()
    source.records[0]["meeting"]["items"][0]["childItems"][0]["minutesItemVotes"] = []
    with pytest.raises(ValueError, match="removed recorded data"):
        fetch.fetch_tenant(source.http, SPEC, [-1], source.root)
    assert dest.read_bytes() == before
    assert len(list((source.out / "revisions/event_13").glob("*.json"))) == 2


def test_shared_import_preserves_positions_without_inventing_terms_or_attendance(
    source, tmp_path, make_db, monkeypatch,
):
    fetch.fetch_tenant(source.http, SPEC, [-1], source.root)
    db = tmp_path / "wi.sqlite"
    conn = make_db(db)
    monkeypatch.setattr(import_local, "TENANTS", [SPEC])
    original = {p: p.read_bytes() for p in source.out.rglob("*.json")}
    import_local.run(source.root, db)
    assert conn.execute("SELECT COUNT(*) FROM local_votes").fetchone() == (8,)
    assert conn.execute("SELECT COUNT(*) FROM local_actions").fetchone() == (6,)
    assert conn.execute("SELECT COUNT(*) FROM local_member_terms").fetchone() == (0,)
    assert conn.execute("SELECT COUNT(*) FROM local_rollcalls").fetchone() == (0,)
    assert conn.execute("SELECT seat,is_current FROM local_members ORDER BY seat").fetchall() == [
        (1, 1), (2, 1),
    ]
    assert {p: p.read_bytes() for p in original} == original
    before = {t: conn.execute(f"SELECT * FROM {t}").fetchall()
              for t in (*import_local.TABLES, "meta")}
    broken = json.loads((source.out / "event_13.json").read_text())
    broken["meeting"]["items"][0]["childItems"][0]["minutesItemVotes"][0]["yesVotes"] = ["Unknown"]
    save_json(source.out / "event_13.json", broken)
    with pytest.raises(ValueError, match="Unreviewed"):
        import_local.run(source.root, db)
    assert {t: conn.execute(f"SELECT * FROM {t}").fetchall() for t in before} == before
    conn.close()


def test_network_scope_excludes_staff_routes_and_blocked_cities():
    access = SourceAccess()
    for url in [f"{SPEC['api_base']}/Events", f"{SPEC['api_base']}/Meetings/9275",
                SPEC["roster_url"]]:
        _, policy = access.source(url)
        assert policy["delay_seconds"] >= 5
    for url in [f"{SPEC['api_base']}/Users", f"{SPEC['api_base']}/Meetings/Delete",
                "https://kenosha.granicus.com/ViewPublisher.php",
                "https://webapi.legistar.com/v1/cityofracine/Events"]:
        with pytest.raises(SourceAccessError):
            access.source(url)
