"""Shared HTTP plumbing for our own fetchers (not the vendored scraper).

One place for the identifying User-Agent, transient-failure retries, the
on-disk page cache the enrichment steps share, and the GitHub-contents-
directory download pattern used by the roster fetchers.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

USER_AGENT = "badgerpolitics.org data pipeline (contact: hphil.work@gmail.com)"

# Three tries with backoff on connection errors and gateway 5xx, reads
# only: a nightly run rides out a blip instead of aborting on one 502.
# The last response comes back as-is, so every caller's own status
# handling (raise_for_status, 404 probes) still sees it.
RETRY = Retry(
    total=3,
    backoff_factor=1.5,
    status_forcelist=(502, 503, 504),
    allowed_methods=frozenset({"GET", "HEAD"}),
    raise_on_status=False,
)


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    s.mount("https://", HTTPAdapter(max_retries=RETRY))
    s.mount("http://", HTTPAdapter(max_retries=RETRY))
    return s


def cached_page(http: requests.Session, url: str, cache_dir: Path) -> tuple[str, bool]:
    """A page through an on-disk cache keyed by URL, not by record: a
    bill's text URL can change (an enrolled version replacing the proposal
    text) and must refetch. Returns (html, was_cached) so callers throttle
    only the fetches that actually went out."""
    cache_file = cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8", errors="replace"), True
    response = http.get(url, timeout=60)
    response.raise_for_status()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(response.text, encoding="utf-8")
    return response.text, False


def fetch_github_dir(repo_path: str, dest: Path) -> int:
    """Download every .yml file in a GitHub contents directory."""
    http = session()
    listing = http.get(f"{repo_path}?per_page=1000", timeout=30)
    listing.raise_for_status()
    entries = [e for e in listing.json() if e["name"].endswith(".yml")]
    if not entries:
        raise RuntimeError(f"no YAML files listed at {repo_path}")

    dest.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        # the name is remote JSON used as a filename: never let it escape dest
        name = entry["name"]
        if "/" in name or "\\" in name or ".." in name:
            raise RuntimeError(f"unsafe filename from GitHub listing: {name!r}")
        response = http.get(entry["download_url"], timeout=30)
        response.raise_for_status()
        (dest / name).write_bytes(response.content)
        time.sleep(0.1)
    return len(entries)
