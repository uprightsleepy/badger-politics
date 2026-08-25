"""Shared HTTP plumbing for our own fetchers (not the vendored scraper).

One place for the identifying User-Agent and the GitHub-contents-directory
download pattern used by the people/committee roster fetchers.
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

USER_AGENT = "badgerpolitics.org data pipeline (contact: hphil.work@gmail.com)"


def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


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
