"""Shared HTTP plumbing for fetchers and the patched upstream subprocess.

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

from scraper.source_access import ACCESS, USER_AGENT, SourceAccessError


class PolicyAdapter(HTTPAdapter):
    """Guard every network hop, including redirects and transient retries."""

    def send(self, request, **kwargs):
        if not kwargs.get("verify", True):
            raise SourceAccessError("TLS verification cannot be disabled for collection")
        request.headers["User-Agent"] = USER_AGENT
        for attempt in range(4):
            host, _ = ACCESS.before_request(request.url, request.method)
            try:
                response = super().send(request, **kwargs)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 3 or request.method != "GET":
                    raise
            else:
                try:
                    ACCESS.after_response(host, response)
                except SourceAccessError:
                    response.close()
                    raise
                if (
                    response.status_code not in (502, 503, 504)
                    or attempt == 3
                    or request.method != "GET"
                ):
                    return response
                response.close()
            time.sleep(1.5 * 2**attempt)
        raise AssertionError("unreachable retry state")


def configure_session(http: requests.Session) -> requests.Session:
    """Also used by our runtime patch inside the upstream subprocess."""
    http.headers["User-Agent"] = USER_AGENT
    http.verify = True
    # Retries live above the adapter so every attempt respects source pacing.
    http.mount("https://", PolicyAdapter(max_retries=0))
    http.mount("http://", PolicyAdapter(max_retries=0))
    # scrapelib otherwise supplies its own FTP transport outside this gate.
    http.mount("ftp://", PolicyAdapter(max_retries=0))
    return http


def session() -> requests.Session:
    return configure_session(requests.Session())


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
