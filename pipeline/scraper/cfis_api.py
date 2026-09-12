"""The CFIS (campaignfinance.wi.gov) public tRPC API, shared by the two
fetchers that read its transaction feed: fetch_cfis for legislator
receipts through the verified committee map, fetch_cf_committees for
every other filer. One request shape and one month-windowing rule, so
the two archives can never disagree about where a month ends.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterator
from datetime import date, timedelta

import requests

BASE = "https://campaignfinance.wi.gov/api/trpc/"
PAGE = 1000


def call(http: requests.Session, proc: str, payload: dict, timeout: int = 60):
    url = BASE + proc + "?input=" + requests.utils.quote(json.dumps({"json": payload}))
    response = http.get(url, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    result = body.get("result", {}).get("data", {}).get("json")
    if result is None:
        raise RuntimeError(f"CFIS drift: unexpected shape from {proc}: {str(body)[:200]}")
    return result


def transaction_pages(
    http: requests.Session, first: str, last: str, *, timeout: int = 60,
    offset_step: int | None = None, page_size: int | None = None,
) -> Iterator[list[dict]]:
    """Yield date-sorted pages; advance by received rows unless a fixed step is supplied."""
    size = PAGE if page_size is None else page_size
    skip = 0
    while True:
        page = call(
            http, "publicFrontendApi.getTransactions",
            {"take": size, "skip": skip, "sortBy": "date",
             "sortDirection": "asc", "dateFrom": first, "dateTo": last},
            timeout=timeout,
        )
        results = page.get("results", [])
        yield results
        if len(results) < size:
            return
        skip += len(results) if offset_step is None else offset_step


def verified(http, first, last, fetch, label, attempts=3):
    """Run `fetch(page_size)`, which returns (result, scanned, expected,
    seen_ids), until the listing is complete and unique: paged rows equal
    the source's count. Smaller pages recover inconsistent small listings;
    a window that never settles stops the run. Returns (result, scanned)."""
    page_size = PAGE
    for attempt in range(attempts):
        result, scanned, expected, seen_ids = fetch(page_size)
        if scanned == expected == len(seen_ids):
            if attempt:
                expected = transaction_count(http, first, last)
            if scanned == expected:
                return result, scanned
        if attempt < attempts - 1:
            print(f"{label}: incomplete listing ({scanned} rows, {len(seen_ids)} unique,"
                  f" expected {expected}), retaking")
            page_size = min(PAGE, 100) if expected <= PAGE else PAGE
            time.sleep(5)
    raise RuntimeError(f"CFIS drift: {label} paged {scanned} rows"
                       f" ({len(seen_ids)} unique) but count said {expected}")


def transaction_count(http: requests.Session, first: str, last: str) -> int:
    count = call(http, "publicFrontendApi.getTransactionsTotalCount",
                 {"dateFrom": first, "dateTo": last})
    if (isinstance(count, bool) or not isinstance(count, (int, float))
            or not math.isfinite(count) or count < 0 or count != int(count)):
        raise RuntimeError("CFIS drift: invalid transaction count")
    return int(count)


def month_windows(since: str, until: str | None = None) -> list[tuple[str, str, str]]:
    """(label, first_day, last_instant) for each month from `since` through
    `until`, both YYYY-MM; `until` defaults to the current month.

    dateTo carries an end-of-day time: some CFIS rows hold timezone
    artifacts like T05:00:00Z, and a bare date bound parses as midnight,
    silently dropping last-day rows into the crack between months."""
    year, month = int(since[:4]), int(since[5:7])
    end = until or date.today().strftime("%Y-%m")
    end_year, end_month = int(end[:4]), int(end[5:7])
    windows = []
    while (year, month) <= (end_year, end_month):
        nxt_y, nxt_m = (year + 1, 1) if month == 12 else (year, month + 1)
        last = date(nxt_y, nxt_m, 1) - timedelta(days=1)
        windows.append(
            (f"{year:04d}-{month:02d}", f"{year:04d}-{month:02d}-01",
             last.isoformat() + "T23:59:59")
        )
        year, month = nxt_y, nxt_m
    return windows
