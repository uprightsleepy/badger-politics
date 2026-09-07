"""Policy regressions must stop requests before records or archives change."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from scraper import http, source_access
from scraper.fetch_lobbying import main as lobbying_main
from scraper.fetch_lobbying import parse_principals
from scraper.scrape import build_command
from scraper.source_access import SourceAccess, SourceAccessError, robots_fingerprint

HOST = "docs.legis.wisconsin.gov"
URL = f"https://{HOST}/2025/proposals/ab1"
ROBOTS = "User-agent: *\nDisallow: /scroll/\n"


def response(request, status=200, body="ok", headers=None):
    res = requests.Response()
    res.status_code = status
    res._content = body.encode()
    res._content_consumed = True
    res.headers.update(headers or {})
    res.request = request
    res.url = request.url
    return res


@pytest.fixture
def network(monkeypatch):
    policies = {HOST: {
        "paths": {"GET": [r"/2025/proposals/.*"]},
        "delay_seconds": 10,
        "robots": {"status": 200, "url": f"https://{HOST}/robots.txt",
                   "sha256": robots_fingerprint(ROBOTS)},
    }}
    access = SourceAccess(policies)
    monkeypatch.setattr(http, "ACCESS", access)
    clock = [0.0]
    monkeypatch.setattr(source_access.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(source_access.time, "sleep", lambda seconds: clock.__setitem__(
        0, clock[0] + seconds
    ))
    calls = []
    state = {"robots": ROBOTS, "robots_status": 200, "records": []}

    def send(adapter, request, **kwargs):
        calls.append((request.url, clock[0], request.headers["User-Agent"], kwargs))
        if request.url.endswith("/robots.txt"):
            return response(request, state["robots_status"], state["robots"])
        if state["records"]:
            status, headers = state["records"].pop(0)
            return response(request, status, headers=headers)
        return response(request)

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)
    return access, calls, state, clock


def test_checks_robots_once_and_paces_across_sessions(network):
    _, calls, _, _ = network
    http.session().get(URL, headers={"User-Agent": "Mozilla/5.0"})
    http.session().get(URL)
    assert [call[1] for call in calls] == [0, 10, 20]
    assert all(call[2] == http.USER_AGENT for call in calls)
    assert all(call[3]["verify"] is True for call in calls)


@pytest.mark.parametrize("status,body", [
    (200, "User-agent: *\nDisallow: /\n"),
    (200, "<html>Access denied</html>"),
    (403, "Forbidden"), (429, "Slow down"), (503, "Unavailable"),
    (404, "Not found"),
])
def test_changed_or_unavailable_robots_never_fetches_records(network, status, body):
    _, calls, state, _ = network
    state.update(robots_status=status, robots=body)
    with pytest.raises(SourceAccessError):
        http.session().get(URL)
    assert [call[0] for call in calls] == [f"https://{HOST}/robots.txt"]


def test_policy_refresh_blocks_mid_run_change(network):
    _, calls, state, clock = network
    http.session().get(URL)
    clock[0] += source_access.POLICY_TTL
    state["robots"] += "Disallow: /2025/\n"
    with pytest.raises(SourceAccessError, match="directives changed"):
        http.session().get(URL)
    assert len(calls) == 3  # two policy requests, only the first record request


@pytest.mark.parametrize("url", [
    "https://lobbying.wi.gov/What/BillInformation/2025REG/Information/25090",
    "https://wiseye.org/wp-json/wp/v2/posts",
    "https://api.followthemoney.org/",
    "https://elections.wi.gov/sites/default/files/documents/report.pdf",
    "https://services1.arcgis.com/example/query",
    "https://milwaukeemaps.milwaukee.gov/arcgis/rest/services/",
    "https://unreviewed.example/records",
    "https://docs.legis.wisconsin.gov/scroll/2025/related/subject_index/index",
    "https://docs.legis.wisconsin.gov/search/results?q=ab1",
    "https://docs.legis.wisconsin.gov/%73croll/",
    "https://docs.legis.wisconsin.gov:8443/2025/proposals/ab1",
    "https://docs.legis.wisconsin.gov/2025/%2e%2e/scroll/",
    "https://docs.legis.wisconsin.gov/2025/proposals/%252e%252e/scroll/",
    "http://docs.legis.wisconsin.gov/2025/proposals/ab1",
    "ftp://docs.legis.wisconsin.gov/2025/proposals/ab1",
    "https://www.westalliswi.gov/api/districts",
    "https://city.milwaukee.gov/CommonCouncil/CouncilMembers/District1?PrintPage=yes",
    "https://campaignfinance.wi.gov/registrant-dashboard",
    "https://campaignfinance.wi.gov/api/trpc/admin.delete",
])
def test_reviewed_manifest_rejects_restricted_or_unreviewed_urls(url):
    with pytest.raises(SourceAccessError):
        SourceAccess().source(url)


@pytest.mark.parametrize("url", [
    "https://docs.legis.wisconsin.gov/search",
    "https://docs.legis.wisconsin.gov/2025/related/subject_index/index?down=1",
    "https://docs.legis.wisconsin.gov/document/session/2025/reg/ab1",
    "https://docs.legis.wisconsin.gov/document/proposaltext/2025/AB246",
    "https://campaignfinance.wi.gov/api/trpc/entity.searchEntities?input=example",
    "https://campaignfinance.wi.gov/api/trpc/publicFrontendApi.getTransactions",
    "https://api.github.com/repos/openstates/people/contents/data/wi/committees",
    "https://clerk.house.gov/evs/2026/roll001.xml",
    "https://webapi.legistar.com/v1/milwaukee/Events/1/EventItems",
    "https://westalliswi.legistar.com/MeetingDetail.aspx?ID=1",
    "https://www.westalliswi.gov/page/district-one",
])
def test_reviewed_manifest_accepts_only_intended_routes(url):
    SourceAccess().source(url)


@pytest.mark.parametrize("location", [
    "/scroll/private", "https://lobbying.wi.gov/", "http://docs.legis.wisconsin.gov/",
])
def test_redirect_cannot_escape_policy_gate(network, location):
    _, calls, state, _ = network
    state["records"] = [(302, {"Location": location})]
    with pytest.raises(SourceAccessError):
        http.session().get(URL)
    assert len(calls) == 2  # no request to the redirect target


def test_gateway_retries_are_bounded_and_paced(network):
    _, calls, state, _ = network
    state["records"] = [(503, {})] * 4
    assert http.session().get(URL).status_code == 503
    times = [call[1] for call in calls[1:]]
    assert len(times) == 4
    assert all(b - a >= 10 for a, b in zip(times, times[1:], strict=False))


def test_read_only_post_is_checked_but_never_retried(network):
    access, calls, state, _ = network
    access.policies[HOST]["paths"]["POST"] = [r"/2025/proposals/.*"]
    state["records"] = [(503, {})]
    assert http.session().post(URL, data={"page": "2"}).status_code == 503
    assert len(calls) == 2


def test_missing_robots_must_match_the_reviewed_response(network):
    access, calls, state, _ = network
    access.policies[HOST]["robots"] = {
        "status": 404, "url": f"https://{HOST}/robots.txt",
    }
    state["robots_status"] = 404
    assert http.session().get(URL).status_code == 200
    assert len(calls) == 2


def test_policy_comments_are_not_silently_accepted(network):
    _, calls, state, _ = network
    state["robots"] += "# Automated collection now requires written permission.\n"
    with pytest.raises(SourceAccessError):
        http.session().get(URL)
    assert len(calls) == 1


@pytest.mark.parametrize("status,headers", [
    (401, {}), (403, {}), (429, {"Retry-After": "120"}),
    (503, {"Retry-After": "120"}), (200, {"X-RateLimit-Remaining": "0"}),
])
def test_access_and_rate_limits_stop_without_retry(network, status, headers):
    _, calls, state, _ = network
    state["records"] = [(status, headers)]
    with pytest.raises(SourceAccessError):
        http.session().get(URL)
    with pytest.raises(SourceAccessError):
        http.session().get(URL)
    assert len(calls) == 2


def test_tls_cannot_be_disabled(network):
    _, calls, _, _ = network
    with pytest.raises(SourceAccessError, match="TLS"):
        http.session().get(URL, verify=False)
    assert calls == []


def test_removed_lobbying_command_preserves_archive_without_network(network, tmp_path, monkeypatch):
    _, calls, _, _ = network
    archive = tmp_path / "interests-2025REG.json"
    archive.write_text('[{"identifier":"AB 246","principals":[]}]', encoding="utf-8")
    before = archive.read_bytes()
    monkeypatch.chdir(tmp_path)
    assert lobbying_main(["--refresh", "--session", "2025REG"]) == 2
    assert calls == []
    assert archive.read_bytes() == before
    assert parse_principals('''<a href="/Who/PrincipalInformation/2025REG/Information/1">
        Example Organization</a>''') == [{"id": 1, "name": "Example Organization"}]


def test_vendor_command_exposes_policy_module_and_disables_fastmode(monkeypatch):
    monkeypatch.setattr("scraper.scrape.shutil.which", lambda name: None)
    command = build_command("bills", ["session=2023"])
    assert "--fastmode" not in command
    assert "PYTHONPATH=/badger-pipeline:./scrapers" in command
    assert any("/badger-pipeline/scraper:ro" in arg for arg in command)
    with pytest.raises(ValueError):
        build_command("bills", ["--fastmode"])


def test_nightly_job_keeps_archives_and_omits_paused_fetchers():
    root = Path(__file__).resolve().parents[2]
    commands = [line for line in (root / "pipeline/run.sh").read_text().splitlines()
                if line.startswith("python -m ")]
    assert "python -m importer.import_lobbying _data/lobbying ../data/wi.sqlite" in commands
    assert not any("scraper.fetch_" + name in line for line in commands
                   for name in ("lobbying", "wiseye", "wec"))
    policies = json.loads(source_access.MANIFEST.read_text())
    assert policies["reviewed_on"] == "2026-09-07"
