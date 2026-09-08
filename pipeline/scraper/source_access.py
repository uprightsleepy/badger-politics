"""Fail closed unless both the URL and the live robots policy were reviewed.

The manifest records narrowly reviewed paths and fingerprints of robots.txt.
Any policy change requires human review; we deliberately do not interpret new
directives as permission. This also catches changed crawl delays and bot groups.
Terms and intended reuse still need the documented human review.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests

USER_AGENT = "badgerpolitics.org data pipeline (contact: https://badgerpolitics.org/about/#contact)"
MANIFEST = Path(__file__).with_name("source_policies.json")
POLICY_TTL = 3600  # memory only: each new process checks current policies again


class SourceAccessError(RuntimeError):
    """A policy failure must not be swallowed as an optional network outage."""


def robots_fingerprint(text: str) -> str:
    """Normalize line endings/spacing; preserve directives and policy comments."""
    lines = [line.strip() for line in text.splitlines()]
    return hashlib.sha256("\n".join(line for line in lines if line).encode()).hexdigest()


class SourceAccess:
    def __init__(self, policies: dict | None = None):
        self.policies = policies if policies is not None else json.loads(
            MANIFEST.read_text(encoding="utf-8")
        )["sources"]
        self.checked: dict[str, float] = {}
        self.last_request: dict[str, float] = {}
        self.stopped: set[str] = set()

    def source(self, url: str, method: str = "GET") -> tuple[str, dict]:
        parts = urlsplit(url)
        host = parts.hostname or ""
        policy = self.policies.get(host)
        if parts.scheme != "https" or parts.port not in (None, 443) or parts.username:
            raise SourceAccessError("Collection requires a reviewed HTTPS origin")
        if not policy or policy.get("paused"):
            reason = policy.get("paused") if policy else "source has not been reviewed"
            raise SourceAccessError(f"Collection paused for {host}: {reason}")
        # Decode paths before matching so encoded slashes/dot segments cannot
        # turn a reviewed URL into an unreviewed endpoint on the server.
        path = unquote(parts.path)
        if (any(segment in (".", "..") for segment in path.split("/"))
                or "\\" in path or re.search(r"%[0-9a-fA-F]{2}", path)):
            raise SourceAccessError(f"Noncanonical collection path on {host}")
        patterns = policy["paths"].get(method.upper(), [])
        if not any(re.fullmatch(pattern, path) for pattern in patterns):
            raise SourceAccessError(f"Unreviewed {method} path on {host}: {path}")
        if any(re.search(pattern, unquote(parts.query))
               for pattern in policy.get("deny_query", [])):
            raise SourceAccessError(f"Disallowed query on {host}")
        if host in self.stopped:
            raise SourceAccessError(
                f"Collection stopped after an access/rate-limit response: {host}"
            )
        return host, policy

    def verify_robots(self, host: str, policy: dict) -> None:
        checked = self.checked.get(host)
        if checked is not None and time.monotonic() - checked < POLICY_TTL:
            return
        url = f"https://{host}/robots.txt"
        # Separate transport is used ONLY for robots.txt and its same-origin
        # redirects. No record requests can use this unchecked session.
        with requests.Session() as http:
            http.headers["User-Agent"] = USER_AGENT
            for _ in range(6):
                response = self._robots_response(http, url, host, policy)
                if response.is_redirect:
                    url = urljoin(url, response.headers["Location"])
                    response.close()
                    if urlsplit(url).netloc != host or urlsplit(url).scheme != "https":
                        raise SourceAccessError(f"Unreviewed robots redirect for {host}")
                    time.sleep(policy["delay_seconds"])
                    continue
                break
            else:
                raise SourceAccessError(f"Too many robots redirects for {host}")
        expected = policy["robots"]
        if response.status_code != expected["status"] or url != expected["url"]:
            raise SourceAccessError(
                f"Robots response changed for {host} (HTTP {response.status_code},"
                f" expected {expected['status']}; unexpected final URL: {url != expected['url']});"
                " review scraper/README.md"
            )
        if "sha256" in expected and robots_fingerprint(response.text) != expected["sha256"]:
            raise SourceAccessError(f"Robots directives changed for {host}; review required")
        # The Senate redirects to a specific missing-page document (documented
        # in the review). Never treat arbitrary 200 HTML as an empty robots file.
        if expected.get("missing_page") and "text/html" not in response.headers.get(
            "Content-Type", ""
        ):
            raise SourceAccessError(f"Missing-page response changed for {host}")
        self.checked[host] = time.monotonic()
        self.last_request[host] = time.monotonic()

    def _robots_response(self, http: requests.Session, url: str, host: str, policy: dict):
        """Retry transport outages; access decisions and changed policies still stop collection."""
        for attempt in range(4):
            try:
                response = http.get(url, timeout=30, allow_redirects=False)
            except requests.RequestException as error:
                transient = isinstance(error, (requests.ConnectionError, requests.Timeout))
                if (not transient or isinstance(error, requests.exceptions.SSLError)
                        or attempt == 3):
                    raise SourceAccessError(
                        f"Could not verify robots.txt for {host}"
                        f" ({type(error).__name__}, {attempt + 1} attempts)"
                    ) from error
            else:
                try:
                    self.after_response(host, response)
                except SourceAccessError:
                    response.close()
                    raise
                if response.status_code not in (502, 503, 504) or attempt == 3:
                    return response
                response.close()
            time.sleep(max(policy["delay_seconds"], 30 * 2**attempt))
        raise AssertionError("unreachable robots retry state")

    def before_request(self, url: str, method: str) -> tuple[str, dict]:
        host, policy = self.source(url, method)
        self.verify_robots(host, policy)
        remaining = policy["delay_seconds"] - (
            time.monotonic() - self.last_request.get(host, float("-inf"))
        )
        if remaining > 0:
            time.sleep(remaining)
        self.last_request[host] = time.monotonic()
        return host, policy

    def after_response(self, host: str, response: requests.Response) -> None:
        # Stop this process rather than risking retries before Retry-After or
        # GitHub's reset time. A new scheduled run will review policies again.
        if response.status_code in (401, 403, 429) or response.headers.get(
            "X-RateLimit-Remaining"
        ) == "0" or "Retry-After" in response.headers:
            self.stopped.add(host)
            raise SourceAccessError(
                f"Collection stopped for {host} (HTTP {response.status_code}); "
                "honor Retry-After/rate-limit reset before restarting"
            )


ACCESS = SourceAccess()
