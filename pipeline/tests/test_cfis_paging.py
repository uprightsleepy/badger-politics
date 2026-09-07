"""CFIS page traversal preserves wire requests, source rows, and failure boundaries."""

import copy
import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from scraper import cfis_api as api
from scraper import fetch_cf_committees as committees
from scraper import fetch_cfis as receipts
from scraper.source_access import SourceAccessError

FIRST, LAST = "2025-01-01", "2025-01-31T23:59:59"
RAW = {
    "id": 1, "createdByEntityId": 20, "date": "2025-01-31T05:00:00Z", "amount": 123.45,
    "createdByEntity": {"id": 20, "name": "Example Candidate Committee", "committee": {
        "committeeType": {"name": "State Candidate"}, "assignedCommitteeId": "C20",
    }},
    "from_entity": {"id": 30, "name": "Example PAC", "entityType": {"name": "Committee"},
                    "committee": {"committeeType": {"name": "PAC"},
                                  "assignedCommitteeId": "P30"}},
    "to_entity": None, "transactionType": {"direction": "INCOMING"},
    "supportStance": "FOR", "relatedEntity": {"name": "Example Candidate"},
    "relatedOffice": {"name": "State Senate"}, "relatedDistrict": {"name": "1"},
    "finalRecipient": {"id": 50, "name": "Final Recipient"},
    "transactionPurpose": {"name": "Advertising"},
    "reports": [{"id": 60, "name": "Original filing"}, {"id": 61, "name": "Other filing"}],
    "fromOccupationTitle": "Teacher", "transactionCategory": {"label": "Monetary"},
}
RECEIPT = {
    "id": 1, "person_id": "p1", "committee_entity_id": 20, "date": "2025-01-31",
    "amount": 123.45, "from_entity_id": 30, "from_name": "Example PAC",
    "from_type": "Committee", "occupation": "Teacher", "category": "Monetary",
}
COMMITTEE_ROW = {
    "id": 1, "filer_entity_id": 20, "filer_type": "State Candidate", "direction": "INCOMING",
    "date": "2025-01-31", "amount": 123.45, "other_entity_id": 30,
    "other_name": "Example PAC", "other_type": "Committee", "stance": "FOR",
    "related_name": "Example Candidate", "related_office": "State Senate",
    "related_district": "1", "final_recipient_id": 50,
    "final_recipient_name": "Final Recipient", "purpose": "Advertising",
    "report_id": 60, "report_name": "Original filing",
}
REGISTRY = {
    20: {"entity_id": 20, "name": "Example Candidate Committee",
         "committee_type": "State Candidate", "assigned_id": "C20"},
    30: {"entity_id": 30, "name": "Example PAC", "committee_type": "PAC", "assigned_id": "P30"},
}


def page(*rows):
    return {"results": list(rows)}


SCENARIOS = {
    "empty": [page()],
    "short": [page(RAW)],
    "exact": [page(RAW, RAW), page()],
    "multiple": [page(RAW, RAW), page(RAW)],
    "oversized": [page(RAW, RAW, RAW), page()],
    "missing-results": [{}],
    "timeout": [page(RAW, RAW), requests.Timeout("fixture timeout")],
    "denied": [SourceAccessError("fixture source stopped")],
    "http-error": [requests.HTTPError("fixture HTTP 503")],
    "malformed-page": [None],
    "null-results": [{"results": None}],
    "invalid-row": [page({"createdByEntity": RAW["createdByEntity"], "supportStance": "FOR"}, RAW)],
}


class FakeResponse:
    def __init__(self, result):
        self.result = result

    def raise_for_status(self):
        pass

    def json(self):
        return {"result": {"data": {"json": self.result}}}


class FakeHttp:
    def __init__(self, pages, counts=(0,)):
        self.pages = copy.deepcopy(pages)
        self.counts = list(counts)
        self.events = []

    def get(self, url, timeout):
        self.events.append(("request", url, timeout))
        procedure = urlsplit(url).path.rsplit("/", 1)[-1]
        if procedure.endswith("getTransactionsTotalCount"):
            result = self.counts.pop(0)
        else:
            assert procedure == "publicFrontendApi.getTransactions"
            result = self.pages.pop(0)
        if isinstance(result, Exception):
            raise result
        return FakeResponse(result)

    def requests(self):
        requests_made = []
        for event in self.events:
            if event[0] != "request":
                continue
            _, url, timeout = event
            requests_made.append((
                urlsplit(url).path.rsplit("/", 1)[-1],
                json.loads(parse_qs(urlsplit(url).query)["input"][0])["json"], timeout,
            ))
        return requests_made


@pytest.fixture
def configure(monkeypatch):
    monkeypatch.setattr(api, "PAGE", 2)
    monkeypatch.setattr(receipts, "PAGE", 2)
    monkeypatch.setattr(committees, "PAGE", 2)

    def configured(pages, counts=(0,)):
        http = FakeHttp(pages, counts)
        monkeypatch.setattr(api.time, "sleep", lambda delay: http.events.append(("sleep", delay)))
        return http

    return configured


def collect(kind, http, first=FIRST, last=LAST):
    if kind == "receipts":
        return receipts.fetch_window(http, {20: "p1"}, first, last)
    return committees.fetch_month(http, first, last)


@pytest.mark.parametrize("kind,timeout", [("receipts", 60), ("committees", 90)])
@pytest.mark.parametrize("scenario,row_count", [
    ("empty", 0), ("short", 1), ("exact", 2), ("multiple", 3),
    ("oversized", 3), ("missing-results", 0),
])
def test_complete_rows_requests_and_sleeps(kind, timeout, scenario, row_count, configure):
    http = configure(SCENARIOS[scenario], counts=(row_count,))
    result = collect(kind, http)
    if kind == "receipts":
        assert result == ([RECEIPT] * row_count, row_count, row_count, {1} if row_count else set())
    else:
        assert result == ([COMMITTEE_ROW] * row_count, REGISTRY if row_count else {})
    skips = [0]
    if scenario in ("exact", "multiple", "oversized"):
        skips.append(3 if scenario == "oversized" and kind == "receipts" else 2)
    expected = [
        ("publicFrontendApi.getTransactions", {
            "take": 2, "skip": skip, "sortBy": "date", "sortDirection": "asc",
            "dateFrom": FIRST, "dateTo": LAST,
        }, timeout)
        for skip in skips
    ]
    if kind == "receipts":
        expected.insert(0, ("publicFrontendApi.getTransactionsTotalCount",
                            {"dateFrom": FIRST, "dateTo": LAST}, 60))
    assert http.requests() == expected
    assert [e for e in http.events if e[0] == "sleep"] == [("sleep", 0.4)] * (len(skips) - 1)
    assert not http.pages


@pytest.mark.parametrize("kind", ["receipts", "committees"])
@pytest.mark.parametrize("first,last", [
    ("2008-02-01", "2008-02-29T23:59:59"), ("2025-12-01", "2025-12-31T23:59:59"),
])
def test_window_bounds_pass_through_unchanged(kind, first, last, configure):
    http = configure([page()])
    collect(kind, http, first, last)
    for _, payload, _ in http.requests():
        assert payload["dateFrom"] == first
        assert payload["dateTo"] == last


@pytest.mark.parametrize("kind", ["receipts", "committees"])
@pytest.mark.parametrize("scenario,error,requests_made,sleeps", [
    ("timeout", requests.Timeout, 2, [("sleep", 0.4)]),
    ("denied", SourceAccessError, 1, []),
    ("http-error", requests.HTTPError, 1, []),
    ("malformed-page", RuntimeError, 1, []),
    ("null-results", TypeError, 1, []),
    ("invalid-row", KeyError, 1, []),
])
def test_errors_propagate_without_advancing(
    kind, scenario, error, requests_made, sleeps, configure,
):
    http = configure(SCENARIOS[scenario])
    with pytest.raises(error):
        collect(kind, http)
    assert len(http.requests()) == requests_made + (kind == "receipts")
    assert [e for e in http.events if e[0] == "sleep"] == sleeps


def test_receipt_count_mismatch_retake_keeps_both_waits(configure):
    http = configure([page(RAW), page(RAW, RAW), page()], counts=(2, 2))
    assert receipts._fetch_with_retries(http, {20: "p1"}, FIRST, LAST, "fixture", 2) == (
        [RECEIPT, RECEIPT], 2, 2, {1}, True,
    )
    assert [e for e in http.events if e[0] == "sleep"] == [("sleep", 5), ("sleep", 0.4)]
    assert [proc for proc, _, _ in http.requests()] == [
        "publicFrontendApi.getTransactionsTotalCount", "publicFrontendApi.getTransactions",
        "publicFrontendApi.getTransactionsTotalCount", "publicFrontendApi.getTransactions",
        "publicFrontendApi.getTransactions",
    ]


def test_duplicate_rows_and_latest_registry_observation_are_retained(configure):
    renamed = copy.deepcopy(RAW)
    renamed["from_entity"]["name"] = "Amended PAC Name"
    http = configure([page(RAW, renamed), page()])
    rows, registry = committees.fetch_month(http, FIRST, LAST)
    assert rows == [COMMITTEE_ROW, {**COMMITTEE_ROW, "other_name": "Amended PAC Name"}]
    assert registry == {**REGISTRY, 30: {**REGISTRY[30], "name": "Amended PAC Name"}}
