"""Council backfills advance without replacing or truncating archived records."""

import json
from pathlib import Path

import pytest

from importer.local_registry import TENANTS
from scraper import fetch_local_votes as fetch

MADISON = {**next(s for s in TENANTS if s["tenant"] == "madison"), "bootstrap_event_id": 9}


@pytest.fixture()
def source(tmp_path, monkeypatch):
    events = [{"EventId": n, "EventDate": f"2025-01-{n:02d}T00:00:00",
               "EventMinutesStatusName": "Approved"} for n in range(9, 0, -1)]
    calls = []

    def call(http, tenant, path, delay, **params):
        calls.append(path)
        if path.endswith("/EventItems"):
            return [{"EventItemId": 7, "EventItemActionName": "Adopted"}]
        return []

    monkeypatch.setattr(fetch, "DATA_DIR", tmp_path)
    monkeypatch.setattr(fetch, "call", call)
    monkeypatch.setattr(fetch, "fetch_events", lambda *a: events)
    monkeypatch.setattr(fetch, "fetch_departments", lambda *a: [])
    monkeypatch.setattr(fetch, "fetch_links", lambda *a: {})
    return tmp_path / "madison", events, calls


def test_backfill_advances_and_preserves_existing_bytes(source):
    archive, events, calls = source
    assert fetch.fetch_tenant(None, MADISON, [-1], 0) == (5, 0)
    original = {p.name: p.read_bytes() for p in archive.glob("event_*.json")}
    assert len(original) == 5
    coverage = json.loads((archive / "coverage.json").read_text())
    assert coverage["listed_meetings"] == 9
    assert coverage["pending_meetings"] == 4
    calls.clear()
    assert fetch.fetch_tenant(None, MADISON, [-1], 0) == (4, 5)
    assert len(list(archive.glob("event_*.json"))) == 9
    assert all((archive / name).read_bytes() == data for name, data in original.items())
    assert "Events/9/EventItems" not in calls
    assert json.loads((archive / "coverage.json").read_text())["pending_meetings"] == 0
    # An event disappearing from a later listing must not delete its archive.
    events.pop()
    fetch.fetch_tenant(None, MADISON, [-1], 0)
    assert (archive / "event_1.json").exists()


def test_draft_refresh_does_not_starve_new_meetings(source):
    archive, events, calls = source
    for event in events:
        event["EventMinutesStatusName"] = "Draft"
    assert fetch.fetch_tenant(None, MADISON, [-1], 0) == (5, 0)
    calls.clear()
    assert fetch.fetch_tenant(None, MADISON, [-1], 0) == (9, 0)
    assert "Events/9/EventItems" in calls
    assert (archive / "event_1.json").exists()


def test_first_batch_includes_reviewed_rollcall_then_newest_meetings(source):
    archive, _, calls = source
    spec = {**MADISON, "bootstrap_event_id": 1}
    assert fetch.fetch_tenant(None, spec, [-1], 0) == (5, 0)
    assert {p.name for p in archive.glob("event_*.json")} == {
        f"event_{n}.json" for n in (1, 9, 8, 7, 6)
    }
    assert [p for p in calls if p.endswith("/EventItems")][0] == "Events/1/EventItems"


def test_missing_bootstrap_fails_before_collecting_meetings(source):
    archive, events, calls = source
    events.pop(0)
    with pytest.raises(RuntimeError, match="bootstrap meeting missing"):
        fetch.fetch_tenant(None, MADISON, [-1], 0)
    assert not list(archive.glob("event_*.json"))
    assert not any(p.endswith("/EventItems") for p in calls)


def test_global_budget_and_future_meetings(source):
    archive, events, _ = source
    events.insert(0, {"EventId": 50, "EventDate": "2099-01-01T00:00:00"})
    assert fetch.fetch_tenant(None, MADISON, [2], 0) == (2, 0)
    coverage = json.loads((archive / "coverage.json").read_text())
    assert (coverage["listed_meetings"], coverage["pending_meetings"]) == (9, 7)
    assert json.loads((archive / "upcoming.json").read_text()) == [events[0]]
    assert not (archive / "event_50.json").exists()


def test_existing_tenants_still_use_final_and_have_no_new_limit(source):
    _, events, calls = source
    spec = next(s for s in TENANTS if s["tenant"] == "milwaukee")
    assert fetch.fetch_tenant(None, spec, [-1], 0) == (9, 0)
    # Approved is not Milwaukee's settled status.
    assert fetch.fetch_tenant(None, spec, [-1], 0) == (9, 0)
    for event in events:
        event["EventMinutesStatusName"] = "Final"
    fetch.fetch_tenant(None, spec, [-1], 0)
    calls.clear()
    assert fetch.fetch_tenant(None, spec, [-1], 0) == (0, 9)
    assert not any(p.endswith("/EventItems") for p in calls)


def test_failed_atomic_write_keeps_original(tmp_path, monkeypatch):
    path = tmp_path / "event_1.json"
    path.write_bytes(b'{"old": true}')

    def interrupted(self, target):
        raise OSError("interrupted replacement")

    monkeypatch.setattr(Path, "replace", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        fetch.save_json(path, {"new": True})
    assert path.read_bytes() == b'{"old": true}'


def test_truncated_meeting_response_keeps_cached_record(source, monkeypatch):
    archive, events, _ = source
    events[0]["EventMinutesStatusName"] = "Draft"
    fetch.fetch_tenant(None, MADISON, [1], 0)
    dest = archive / "event_9.json"
    original = dest.read_bytes()
    real_call = fetch.call

    def truncated(http, tenant, path, delay, **params):
        if path.endswith("/EventItems"):
            return [{}] * fetch.PAGE
        return real_call(http, tenant, path, delay, **params)

    monkeypatch.setattr(fetch, "call", truncated)
    with pytest.raises(RuntimeError, match="page cap"):
        fetch.fetch_tenant(None, MADISON, [-1], 0)
    assert dest.read_bytes() == original
