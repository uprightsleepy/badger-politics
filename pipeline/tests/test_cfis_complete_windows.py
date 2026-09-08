"""An incomplete CFIS view must recover full coverage before replacing an archive."""

import copy
import json
from datetime import date

import pytest
import requests
from test_cfis_paging import COMMITTEE_ROW, FIRST, LAST, RAW, RECEIPT, REGISTRY, FakeHttp

from scraper import cfis_api as api
from scraper import fetch_cf_committees as committees
from scraper import fetch_cfis as receipts
from scraper.source_access import SourceAccessError


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(api.time, "sleep", lambda _: None)


def collect(kind, http):
    if kind == "receipts":
        rows, scanned, expected, seen, matched = receipts._fetch_with_retries(
            http, {20: "p1"}, FIRST, LAST, "2025-01", attempts=3,
        )
        if not matched:
            raise RuntimeError(
                f"CFIS drift: {scanned} rows, {len(seen)} unique, {expected} expected"
            )
        return rows, None
    return committees.fetch_month(http, FIRST, LAST)


def rows(count):
    return [{**copy.deepcopy(RAW), "id": key} for key in range(1, count + 1)]


def page_requests(http):
    return [payload for proc, payload, _ in http.requests()
            if proc == "publicFrontendApi.getTransactions"]


@pytest.mark.parametrize("kind", ["receipts", "committees"])
@pytest.mark.parametrize("count", [87, 100, 250, 1000])
def test_smaller_pages_recover_every_row_and_field(kind, count):
    complete = rows(count)
    pages = [{"results": complete[:32]}]
    pages.extend({"results": complete[start:start + 100]} for start in range(0, count + 1, 100))
    http = FakeHttp(pages, counts=(count, count, count))

    actual, registry = collect(kind, http)

    template = RECEIPT if kind == "receipts" else COMMITTEE_ROW
    assert actual == [{**template, "id": key} for key in range(1, count + 1)]
    assert registry == (None if kind == "receipts" else REGISTRY)
    assert [(p["take"], p["skip"]) for p in page_requests(http)] == [
        (1000, 0), *((100, start) for start in range(0, count + 1, 100)),
    ]
    for _, payload, _ in http.requests():
        assert payload["dateFrom"] == FIRST and payload["dateTo"] == LAST
    assert not http.pages and not http.counts


@pytest.mark.parametrize("kind", ["receipts", "committees"])
@pytest.mark.parametrize("count", [0, 87, 1000, 1001])
def test_complete_default_listing_does_not_add_retries(kind, count):
    complete = rows(count)
    pages = [{"results": complete[start:start + 1000]} for start in range(0, count + 1, 1000)]
    http = FakeHttp(pages, counts=(count,))
    actual, _ = collect(kind, http)
    assert len(actual) == count
    assert all(p["take"] == 1000 for p in page_requests(http))
    assert not http.pages and not http.counts


@pytest.mark.parametrize("kind", ["receipts", "committees"])
def test_large_incomplete_window_keeps_large_pages(kind):
    http = FakeHttp([{"results": rows(32)}] * 3, counts=(1001,) * 3)
    with pytest.raises(RuntimeError, match="CFIS drift"):
        collect(kind, http)
    assert [p["take"] for p in page_requests(http)] == [1000] * 3


@pytest.mark.parametrize("kind", ["receipts", "committees"])
def test_changed_count_during_recovery_requires_another_complete_fetch(kind):
    http = FakeHttp([{"results": rows(n)} for n in (1, 2, 3)], counts=(2, 2, 3, 3, 3))
    actual, _ = collect(kind, http)
    assert [row["id"] for row in actual] == [1, 2, 3]
    assert not http.pages and not http.counts


@pytest.mark.parametrize("kind", ["receipts", "committees"])
@pytest.mark.parametrize("count", [True, "2", -1, 1.5, float("nan"), float("inf"), {}, None])
def test_invalid_count_stops_before_fetching_records(kind, count):
    http = FakeHttp([], counts=(count,))
    with pytest.raises(RuntimeError, match="CFIS drift"):
        collect(kind, http)
    assert not page_requests(http)


@pytest.mark.parametrize("kind", ["receipts", "committees"])
@pytest.mark.parametrize("error", [SourceAccessError("source stopped"),
                                  requests.HTTPError("HTTP 429"), requests.Timeout("timed out")])
def test_access_and_transport_errors_are_not_retried_as_incomplete_windows(kind, error):
    http = FakeHttp([error], counts=(87,))
    with pytest.raises(type(error), match=str(error)):
        collect(kind, http)
    assert len(page_requests(http)) == 1


@pytest.mark.parametrize("kind", ["receipts", "committees", "audit"])
@pytest.mark.parametrize("problem", ["short", "duplicates", "moving-count"])
def test_failed_window_preserves_archives_and_registry(tmp_path, monkeypatch, kind, problem):
    # Both source rows would be filtered out: omissions still cannot be accepted.
    irrelevant = {**RAW, "createdByEntityId": 999, "supportStance": None,
                  "transactionType": {"direction": "OUTGOING"}}
    short = [irrelevant]
    complete = [irrelevant, {**irrelevant, "id": 2}]
    if problem == "short":
        pages, counts = [short] * 3, (2, 2, 2)
    elif problem == "duplicates":
        pages, counts = [[irrelevant, irrelevant]] * 3, (2, 2, 2)
    else:
        pages, counts = [short, complete, complete], (2, 2, 3, 2, 3)
    http = FakeHttp([{"results": page} for page in pages], counts=counts)
    for name, value in (("tx-2025-01.json", [RECEIPT]),
                        ("pac-2025-01.json", [COMMITTEE_ROW]),
                        ("committees.json", list(REGISTRY.values()))):
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    monkeypatch.setattr(receipts, "load_committee_ids", lambda: {20: "p1"})
    for module in (receipts, committees):
        monkeypatch.setattr(module, "session", lambda: http)
        monkeypatch.setattr(module, "DATA_DIR", tmp_path)

    with pytest.raises(RuntimeError, match="CFIS drift"):
        if kind == "receipts":
            receipts.fetch_transactions("2025-01", date(2025, 1, 31))
        elif kind == "audit":
            receipts.audit_archives(1, date(2025, 3, 31))
        else:
            committees.main(["--since", "2025-01", "--until", "2025-01"])

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
    assert len(page_requests(http)) == 3
    assert not http.counts
