"""Require reviewed URLs and a recent, matching robots policy check.

The manifest records narrowly reviewed paths and fingerprints of robots.txt.
Any policy change requires human review; we deliberately do not interpret new
directives as permission. This also catches changed crawl delays and bot groups.
Terms and intended reuse still need the documented human review.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests

USER_AGENT = "badgerpolitics.org data pipeline (contact: https://badgerpolitics.org/about/#contact)"
MANIFEST = Path(__file__).with_name("source_policies.json")
POLICY_TTL = 3600  # Local commands without a shared report check again in each process.
REPORT_TTL = 24 * 3600
REPORT_ENV = "SOURCE_POLICY_REPORT"


class SourceAccessError(RuntimeError):
    """A policy failure must not be swallowed as an optional network outage."""


def robots_fingerprint(text: str) -> str:
    """Normalize line endings/spacing; preserve directives and policy comments."""
    lines = [line.strip() for line in text.splitlines()]
    return hashlib.sha256("\n".join(line for line in lines if line).encode()).hexdigest()


def policy_digest(policies: dict) -> str:
    content = json.dumps({"sources": policies, "user_agent": USER_AGENT}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def validate_report(report: dict, policies: dict, now: float) -> None:
    def timestamp(value):
        return type(value) in (int, float) and math.isfinite(value) and 0 < value <= now

    if (not isinstance(report, dict) or report.get("version") != 1
            or report.get("policy_sha256") != policy_digest(policies)
            or not timestamp(report.get("started_at"))
            or not isinstance(report.get("sources"), dict)
            or set(report["sources"]) != set(policies)):
        raise SourceAccessError("Invalid or mismatched policy report; run the policy-only job")
    for entry in report["sources"].values():
        if not isinstance(entry, dict) or entry.get("state") not in (
            "approved", "blocked", "paused", "pending",
        ):
            raise SourceAccessError("Invalid source status in policy report")
        if entry["state"] == "approved" and (
            not timestamp(entry.get("checked_at")) or entry["checked_at"] < report["started_at"]
        ):
            raise SourceAccessError("Invalid policy check timestamp")


def require_approval(report: dict, host: str, now: float) -> None:
    entry = report["sources"][host]
    if entry["state"] != "approved":
        raise SourceAccessError(f"Policy check is {entry['state']} for {host}; review required")
    if not 0 <= now - entry["checked_at"] < REPORT_TTL:
        raise SourceAccessError(f"Policy check expired for {host}; run the policy-only job")


class SourceAccess:
    def __init__(self, policies: dict | None = None, *, use_report: bool = True):
        self.policies = policies if policies is not None else json.loads(
            MANIFEST.read_text(encoding="utf-8")
        )["sources"]
        self.checked: dict[str, float] = {}
        self.last_request: dict[str, float] = {}
        self.stopped: set[str] = set()
        self.report_path = os.environ.get(REPORT_ENV) if use_report else None
        self.report: dict | None = None
        self.report_clock = (time.time(), time.monotonic())

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
        if self.report_path is not None:
            # A configured report is mandatory: never fall back to an older
            # success or a live request after a missing/failed daily check.
            now = max(time.time(), self.report_clock[0] + time.monotonic() - self.report_clock[1])
            if self.report is None:
                try:
                    path = Path(self.report_path)
                    if path.stat().st_size > 1024 * 1024:
                        raise ValueError("oversized report")
                    report = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    raise SourceAccessError("Policy report missing or unreadable") from None
                validate_report(report, self.policies, now)
                self.report = report
            require_approval(self.report, host, now)
            # Keep the first request paced even across collector processes.
            self.last_request.setdefault(host, time.monotonic())
            return
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
        if self.report_path is not None:
            self.verify_robots(host, policy)  # The pacing wait must not outlast approval.
        self.last_request[host] = time.monotonic()
        return host, policy

    def after_response(self, host: str, response: requests.Response) -> None:
        # A successful response with Retry-After: 0 asks for no additional delay.
        retry_after = response.headers.get("Retry-After")
        retry_required = retry_after is not None and not (
            200 <= response.status_code < 300 and re.fullmatch(r"[ \t]*0+[ \t]*", retry_after)
        )
        if response.status_code in (401, 403, 429) or response.headers.get(
            "X-RateLimit-Remaining"
        ) == "0" or retry_required:
            self.stopped.add(host)
            raise SourceAccessError(
                f"Collection stopped for {host} (HTTP {response.status_code}); "
                "honor Retry-After/rate-limit reset before restarting"
            )


ACCESS = SourceAccess()
