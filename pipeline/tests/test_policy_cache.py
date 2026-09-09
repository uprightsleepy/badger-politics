"""Shared checks reduce requests without permitting stale or denied collection."""

import copy
import json
from pathlib import Path

import pytest
import yaml
from test_nightly import Store, runner
from test_source_access import HOST, ROBOTS, URL
from test_source_access import network as network_fixture

from check_workflows import validate
from nightly import policies
from nightly.storage import GCS, StorageError
from scraper import http, source_access
from scraper.scrape import build_command
from scraper.source_access import (
    REPORT_ENV,
    REPORT_TTL,
    SourceAccess,
    SourceAccessError,
    policy_digest,
    validate_report,
)

network = network_fixture


def report_for(access, now):
    return {"version": 1, "policy_sha256": policy_digest(access.policies), "started_at": now,
            "sources": {host: {"state": "approved", "checked_at": now}
                        for host in access.policies}}


@pytest.fixture
def cached(network, tmp_path, monkeypatch):
    old, calls, state, clock = network
    monkeypatch.setattr(source_access.time, "time", lambda: 100000 + clock[0])
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report_for(old, 100000)))
    monkeypatch.setenv(REPORT_ENV, str(path))
    access = SourceAccess(old.policies)
    monkeypatch.setattr(http, "ACCESS", access)
    return access, path, calls, state, clock


def test_processes_share_check_but_keep_first_request_and_session_pacing(cached, monkeypatch):
    access, _, calls, _, _ = cached
    http.session().get(URL)
    http.session().get(URL)
    monkeypatch.setattr(http, "ACCESS", SourceAccess(access.policies))
    http.session().get(URL)
    assert [call[0] for call in calls] == [URL] * 3
    assert [call[1] for call in calls] == [10, 20, 30]
    assert all(call[2] == source_access.USER_AGENT for call in calls)


def test_cached_requests_accept_zero_retry_after_and_keep_pacing(cached):
    _, _, calls, state, _ = cached
    state["records"] = [(200, {"Retry-After": "0"})] * 2
    assert http.session().get(URL).text == "ok"
    assert http.session().get(URL).text == "ok"
    assert [call[0] for call in calls] == [URL, URL]
    assert [call[1] for call in calls] == [10, 20]


def test_shared_check_expires_mid_process_without_fetching_robots(cached):
    _, _, calls, _, clock = cached
    http.session().get(URL)
    clock[0] = REPORT_TTL
    with pytest.raises(SourceAccessError, match="expired"):
        http.session().get(URL)
    assert len(calls) == 1


def test_first_request_cannot_outwait_report_expiry(cached):
    _, _, calls, _, clock = cached
    clock[0] = REPORT_TTL - 1
    with pytest.raises(SourceAccessError, match="expired"):
        http.session().get(URL)
    assert calls == []


def test_wall_clock_rollback_cannot_extend_cache_lifetime(cached, monkeypatch):
    _, _, calls, _, clock = cached
    http.session().get(URL)
    clock[0] = REPORT_TTL
    monkeypatch.setattr(source_access.time, "time", lambda: 100000)
    with pytest.raises(SourceAccessError, match="expired"):
        http.session().get(URL)
    assert len(calls) == 1


@pytest.mark.parametrize("problem", [
    "missing", "json", "oversized", "version", "manifest", "source", "blocked", "paused",
    "pending", "expired", "future", "nan", "unknown", "before_start",
])
def test_bad_report_never_falls_back_to_live_requests(cached, problem):
    access, path, calls, _, _ = cached
    report = json.loads(path.read_text())
    if problem == "missing":
        path.unlink()
    elif problem == "json":
        path.write_text("{")
    elif problem == "oversized":
        path.write_text(" " * (1024 * 1024 + 1))
    else:
        if problem == "version":
            report["version"] = 2
        elif problem == "manifest":
            access.policies[HOST]["delay_seconds"] = 20
        elif problem == "source":
            report["sources"].pop(HOST)
        elif problem in ("blocked", "paused", "pending", "unknown"):
            report["sources"][HOST]["state"] = problem
        elif problem == "expired":
            report["started_at"] -= REPORT_TTL
            report["sources"][HOST]["checked_at"] -= REPORT_TTL
        elif problem == "before_start":
            report["sources"][HOST]["checked_at"] -= 1
        else:
            report["sources"][HOST]["checked_at"] = float("nan") if problem == "nan" else 100001
        path.write_text(json.dumps(report))
    with pytest.raises(SourceAccessError):
        http.session().get(URL)
    assert calls == []


@pytest.mark.parametrize("status,headers", [
    (401, {}), (403, {}), (429, {}), (503, {"Retry-After": "120"}),
    (200, {"X-RateLimit-Remaining": "0"}),
    (429, {"Retry-After": "0"}),
    (200, {"Retry-After": "0", "X-RateLimit-Remaining": "0"}),
])
def test_cached_permission_does_not_override_live_access_limits(cached, status, headers):
    _, _, calls, state, _ = cached
    state["records"] = [(status, headers)]
    with pytest.raises(SourceAccessError):
        http.session().get(URL)
    with pytest.raises(SourceAccessError, match="stopped"):
        http.session().get(URL)
    assert len(calls) == 1


def test_cached_policy_still_rejects_unreviewed_urls_and_tls_bypass(cached):
    _, _, calls, _, _ = cached
    for url in ("https://unreviewed.example/", f"https://{HOST}/scroll/private"):
        with pytest.raises(SourceAccessError):
            http.session().get(url)
    with pytest.raises(SourceAccessError, match="TLS"):
        http.session().get(URL, verify=False)
    assert calls == []


def test_checker_ignores_report_and_uses_existing_live_policy_checks(cached):
    access, _, calls, _, _ = cached
    checker = SourceAccess(access.policies, use_report=False)
    checker.verify_robots(HOST, checker.policies[HOST])
    assert [call[0] for call in calls] == [f"https://{HOST}/robots.txt"]


def test_compose_subprocess_receives_the_mandatory_report(cached, monkeypatch):
    _, path, _, _, _ = cached
    monkeypatch.setattr("scraper.scrape.shutil.which", lambda name: None)
    command = build_command("bills", [])
    assert f"{path.resolve()}:/badger-policy-report.json:ro" in command
    assert f"{REPORT_ENV}=/badger-policy-report.json" in command
    path.unlink()
    with pytest.raises(FileNotFoundError):
        build_command("bills", [])


class PolicyStore(Store):
    def list_names(self, prefix):
        return [name for name in self.objects if name.startswith(prefix)]


@pytest.fixture
def checked_run(tmp_path, network, monkeypatch):
    access, _, _, clock = network
    monkeypatch.setattr(source_access.time, "time", lambda: 100000 + clock[0])
    access.policies["paused.example"] = {"paused": "requires review"}
    store = PolicyStore()
    r = runner(tmp_path, store)
    r.acquire()
    return r, access, clock


@pytest.mark.parametrize("headers", [{}, {"Retry-After": "0"}])
def test_daily_report_roundtrip_and_paused_sources_make_no_requests(
    checked_run, network, tmp_path, headers,
):
    r, access, _ = checked_run
    _, calls, state, _ = network
    state["robots_responses"] = [(200, headers, ROBOTS)]
    assert policies.refresh(r, access)
    target = tmp_path / "next-stage/report.json"
    policies.restore(r.store, target, access.policies)
    report = json.loads(target.read_text())
    validate_report(report, access.policies, source_access.time.time())
    assert report["sources"]["paused.example"] == {"state": "paused"}
    assert [call[0] for call in calls] == [f"https://{HOST}/robots.txt"]
    assert len(r.store.list_names(policies.PREFIX)) == 2


def test_latest_failure_supersedes_a_recent_success(checked_run, tmp_path, monkeypatch):
    r, access, clock = checked_run
    assert policies.refresh(r, access)
    clock[0] += 20
    def denied(*args):
        raise SourceAccessError("HTTP 403")
    monkeypatch.setattr(access, "verify_robots", denied)
    assert not policies.refresh(r, access)
    with pytest.raises(SourceAccessError, match="blocked"):
        policies.restore(r.store, tmp_path / "report.json", access.policies)


def test_new_report_cannot_renew_cached_verification(checked_run, network):
    r, access, clock = checked_run
    _, calls, _, _ = network
    assert policies.refresh(r, access)
    clock[0] += 20
    assert policies.refresh(r, access)
    assert [call[0] for call in calls] == [f"https://{HOST}/robots.txt"] * 2


def test_interrupted_refresh_supersedes_a_recent_success(checked_run, tmp_path, monkeypatch):
    r, access, clock = checked_run
    assert policies.refresh(r, access)
    clock[0] += 20
    def crash(*args):
        raise RuntimeError("interrupted")
    monkeypatch.setattr(access, "verify_robots", crash)
    with pytest.raises(RuntimeError, match="interrupted"):
        policies.refresh(r, access)
    with pytest.raises(SourceAccessError, match="pending"):
        policies.restore(r.store, tmp_path / "report.json", access.policies)


def test_lost_final_upload_keeps_started_report_as_newest(checked_run, tmp_path, monkeypatch):
    r, access, clock = checked_run
    assert policies.refresh(r, access)
    clock[0] += 20
    upload = r.store.put_json
    def lose_final(name, *args, **kwargs):
        if name.endswith("/1.json"):
            raise StorageError("upload interrupted")
        return upload(name, *args, **kwargs)
    monkeypatch.setattr(r.store, "put_json", lose_final)
    with pytest.raises(StorageError):
        policies.refresh(r, SourceAccess(access.policies, use_report=False))
    with pytest.raises(SourceAccessError, match="pending"):
        policies.restore(r.store, tmp_path / "report.json", access.policies)


def test_missing_or_expired_report_leaves_local_file_untouched(checked_run, tmp_path):
    r, access, clock = checked_run
    target = tmp_path / "report.json"
    target.write_text("old")
    with pytest.raises(SourceAccessError, match="missing"):
        policies.restore(r.store, target, access.policies)
    assert policies.refresh(r, access)
    clock[0] += REPORT_TTL
    with pytest.raises(SourceAccessError, match="expired"):
        policies.restore(r.store, target, access.policies)
    assert target.read_text() == "old"


def test_checker_requires_parser_lock_before_any_source_request(checked_run, network):
    r, access, _ = checked_run
    _, calls, _, _ = network
    r.release()
    with pytest.raises(FileNotFoundError):
        policies.refresh(r, access)
    assert calls == []


def test_gcs_listing_is_scoped_paginated_and_bounded():
    store = object.__new__(GCS)
    store.base = "https://storage.googleapis.com/example"
    calls = []
    def request(method, url, **kwargs):
        calls.append(copy.deepcopy(kwargs["params"]))
        result = ({"items": [{"name": "one"}], "nextPageToken": "next"} if len(calls) == 1
                  else {"items": [{"name": "two"}]})
        class Response:
            def json(self):
                return result
        return Response()
    store.request = request
    assert store.list_names(policies.PREFIX) == ["one", "two"]
    assert all(call["prefix"] == policies.PREFIX for call in calls)
    assert calls[1]["pageToken"] == "next"
    store.request = lambda *args, **kwargs: type("Response", (), {
        "json": lambda self: {"nextPageToken": "forever"},
    })()
    with pytest.raises(StorageError, match="limit"):
        store.list_names(policies.PREFIX)


@pytest.mark.parametrize("mutation", [
    "trigger", "schedule", "timezone", "old_time", "release", "collector", "finish",
])
def test_policy_only_workflow_boundaries(mutation):
    path = Path(__file__).resolve().parents[2] / ".github/workflows/nightly-parser.yml"
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    if mutation == "trigger":
        workflow["jobs"]["policies"]["if"] = "always()"
    elif mutation == "schedule":
        workflow["on"]["schedule"].pop(0)
    elif mutation == "timezone":
        workflow["on"]["schedule"][1]["timezone"] = "UTC"
    elif mutation == "old_time":
        workflow["on"]["schedule"][1]["cron"] = "15 5 * * *"
    elif mutation == "release":
        workflow["jobs"]["policies"]["steps"][-1].pop("if")
    elif mutation == "collector":
        workflow["jobs"]["legislature"].pop("if")
    else:
        workflow["jobs"]["finish"]["if"] = "always()"
    assert validate(workflow, "nightly-parser.yml")


@pytest.mark.parametrize("mutation", ["missing", "late", "environment"])
def test_stage_requires_policy_report_before_collection(mutation):
    path = Path(__file__).resolve().parents[2] / ".github/workflows/parser-stage.yml"
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["stage"]
    step = next(s for s in job["steps"] if s.get("name") == "Restore checked source policies")
    if mutation == "environment":
        job["env"].pop(REPORT_ENV)
    else:
        job["steps"].remove(step)
        if mutation == "late":
            job["steps"].append(step)
    assert validate(workflow, "parser-stage.yml")
