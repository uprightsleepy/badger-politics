"""Validate release boundaries and immutable action pins in parsed workflow YAML."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

PIN = re.compile(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}")


def validate(workflow: dict, name: str) -> list[str]:
    errors = []
    permissions = workflow.get("permissions")
    if not isinstance(permissions, dict) or permissions.get("contents") != "read":
        errors.append("workflow must explicitly grant contents: read")
    if isinstance(permissions, dict) and any(v == "write" for v in permissions.values()):
        errors.append("write permissions must be scoped to an individual job")
    events = workflow.get("on", {})
    events = [events] if isinstance(events, str) else events
    untrusted = any(e in events for e in ("pull_request", "pull_request_target"))
    for job_name, job in workflow.get("jobs", {}).items():
        grants = job.get("permissions", permissions)
        if not isinstance(grants, dict):
            errors.append(f"{job_name}: permissions must be an explicit mapping")
        else:
            for scope, value in grants.items():
                if value == "write" and scope != "id-token":
                    errors.append(f"{job_name}: forbidden write permission: {scope}")
            if grants.get("id-token") == "write" and (untrusted or not job.get("environment")):
                errors.append(f"{job_name}: OIDC requires a trusted trigger and environment")
        for step in [job, *job.get("steps", [])]:
            action = step.get("uses", "")
            if action and not action.startswith("./") and not PIN.fullmatch(action):
                errors.append(f"{job_name}: action must use a full commit SHA: {action}")
            if action.startswith("actions/cache"):
                settings = str(step.get("with", {}))
                if "snapshot-" in settings or "data/wi.sqlite" in settings:
                    errors.append(f"{job_name}: raw snapshots must not enter Actions caches")
    if name == "deploy.yml":
        if untrusted or not set(events).issubset({"push", "workflow_dispatch"}):
            errors.append("deploy may only use push or workflow_dispatch")
        needs = workflow.get("jobs", {}).get("deploy", {}).get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        if "validate" not in needs:
            errors.append("deploy must depend on validation of its revision")
    return errors


def main() -> int:
    failures = []
    for path in sorted(Path(sys.argv[1]).glob("*.yml")):
        # BaseLoader preserves GitHub's `on` key instead of YAML 1.1's boolean.
        workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        errors = validate(workflow, path.name)
        failures.extend(f"{path.name}: {error}" for error in errors)
        if not errors:
            print(f"ok: {path.name}")
    for error in failures:
        print(error, file=sys.stderr)
    return bool(failures)


if __name__ == "__main__":
    sys.exit(main())
