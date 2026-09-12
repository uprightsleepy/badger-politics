"""Daily robots checks and private, immutable reports shared by parser jobs."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from nightly.runner import Runner
from nightly.storage import GCS
from scraper.http import save_json
from scraper.source_access import (
    SourceAccess,
    SourceAccessError,
    policy_digest,
    require_approval,
    validate_report,
)

PREFIX = "parser-state/checkpoints/policies/"
NAME = re.compile(re.escape(PREFIX) + r"\d{8}T\d{6}\.\d{6}Z-\d+-\d+/[01]\.json")


def refresh(runner: Runner, access: SourceAccess) -> bool:
    if access.report_path is not None:
        raise ValueError("The policy job must perform live checks")
    runner.check_lock()
    access.checked.clear()
    started = time.time()
    stamp = datetime.fromtimestamp(started, UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    prefix = f"{PREFIX}{stamp}-{runner.execution}/"
    report = {
        "version": 1, "policy_sha256": policy_digest(access.policies), "started_at": started,
        "sources": {host: {"state": "paused" if policy.get("paused") else "pending"}
                    for host, policy in access.policies.items()},
    }
    # An interrupted refresh must supersede an older successful check.
    runner.store.put_json(prefix + "0.json", report, runner.scratch)
    try:
        for host, policy in access.policies.items():
            if policy.get("paused"):
                continue
            try:
                access.verify_robots(host, policy)
            except SourceAccessError as error:
                report["sources"][host] = {"state": "blocked", "reason": str(error)}
            else:
                report["sources"][host] = {"state": "approved", "checked_at": time.time()}
            print(f"{host}: {report['sources'][host]['state']}", flush=True)
    finally:
        runner.check_lock()
        runner.store.put_json(prefix + "1.json", report, runner.scratch)
    return all(entry["state"] in ("approved", "paused") for entry in report["sources"].values())


def restore(store, target: Path, policies: dict) -> None:
    names = store.list_names(PREFIX)
    if not names or any(not NAME.fullmatch(name) for name in names):
        raise SourceAccessError("Policy report missing or invalid; run the policy-only job")
    # Read the newest attempt, including failures/pending checks. Never search
    # backwards for a successful report, even if it would still be within TTL.
    report, _ = store.read_json(max(names))
    now = time.time()
    validate_report(report, policies, now)
    for host, policy in policies.items():
        if not policy.get("paused"):
            require_approval(report, host, now)
    target.parent.mkdir(parents=True, exist_ok=True)
    save_json(target, report)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=("refresh", "restore"))
    ap.add_argument("--bucket", default="badgerpolitics-prod-snapshots")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    store = GCS(args.bucket)
    access = SourceAccess(use_report=False)
    if args.action == "restore":
        restore(store, root.parent / ".private/policies/report.json", access.policies)
        print("Restored current source policy checks; no source requests")
        return 0
    execution = f"{os.environ.get('GITHUB_RUN_ID', '')}-{os.environ.get('GITHUB_RUN_ATTEMPT', '')}"
    runner = Runner(store, root, os.environ.get("GITHUB_RUN_ID", ""),
                    os.environ.get("GITHUB_SHA", ""), execution)
    return 0 if refresh(runner, access) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Source policy check stopped: {error}", file=sys.stderr)
        sys.exit(1)
