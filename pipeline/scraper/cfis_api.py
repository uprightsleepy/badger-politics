"""The CFIS (campaignfinance.wi.gov) public tRPC API, shared by the two
fetchers that read its transaction feed: fetch_cfis for legislator
receipts through the verified committee map, fetch_cf_committees for
every other filer. One request shape and one month-windowing rule, so
the two archives can never disagree about where a month ends.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import requests

BASE = "https://campaignfinance.wi.gov/api/trpc/"
PAGE = 1000
DELAY = 0.4


def call(http: requests.Session, proc: str, payload: dict, timeout: int = 60):
    url = BASE + proc + "?input=" + requests.utils.quote(json.dumps({"json": payload}))
    response = http.get(url, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    result = body.get("result", {}).get("data", {}).get("json")
    if result is None:
        raise RuntimeError(f"CFIS drift: unexpected shape from {proc}: {str(body)[:200]}")
    return result


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
