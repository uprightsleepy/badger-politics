"""Validate release boundaries and immutable action pins in parsed workflow YAML."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

from nightly.stages import STAGES

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
            parser_call = (name == "nightly-parser.yml"
                           and job.get("uses") == "./.github/workflows/parser-stage.yml")
            if grants.get("id-token") == "write" and (
                untrusted or not (job.get("environment") or parser_call)
            ):
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
    if name == "nightly-parser.yml":
        if set(events) != {"schedule", "workflow_dispatch"}:
            errors.append("nightly parser requires only schedule and workflow_dispatch")
        concurrency = workflow.get("concurrency", {})
        if (concurrency.get("group") != "nightly-parser"
                or str(concurrency.get("cancel-in-progress")).lower() != "false"):
            errors.append("nightly parser requires a fixed, non-cancelling concurrency group")
        schedules = events.get("schedule", []) if isinstance(events, dict) else []
        if schedules != [
            {"cron": "15 4 * * *", "timezone": "America/Chicago"},
            {"cron": "15 5 * * *", "timezone": "America/Chicago"},
        ]:
            errors.append("nightly parser requires separate daily policy and parser schedules")
        policies = workflow.get("jobs", {}).get("policies", {})
        policy_trigger = "inputs.policy_only || github.event.schedule == '15 4 * * *'"
        if (policies.get("needs") != "validate" or policies.get("environment") != "nightly-parser"
                or policies.get("if") != policy_trigger
                or str(policies.get("timeout-minutes")) != "30"):
            errors.append("policies: require validation, environment, and a policy-only trigger")
        policy_steps = policies.get("steps", [])
        for command in ("acquire", "policies refresh", "release"):
            invocation = "nightly.policies refresh" if command == "policies refresh" else (
                f"nightly {command}")
            matches = [s for s in policy_steps
                       if s.get("run") == f"uv run --locked python -m {invocation}"]
            if len(matches) != 1 or (command == "release" and matches[0].get("if") != "always()"):
                errors.append("policies: require the lock, refresh, and unconditional release")
        legislature = workflow.get("jobs", {}).get("legislature", {})
        if legislature.get("if") != (
            "${{ !inputs.policy_only && github.event.schedule != '15 4 * * *' }}"
        ):
            errors.append("legislature: must not collect records during a policy-only run")
        previous = "validate"
        for stage in STAGES:
            if stage == "finance-committees":
                previous = "finance-months"
            job = workflow.get("jobs", {}).get(stage, {})
            if (job.get("needs") != previous
                    or job.get("uses") != "./.github/workflows/parser-stage.yml"
                    or job.get("with", {}).get("stage") != stage):
                errors.append(f"{stage}: parser stages must use the helper and run sequentially")
            previous = stage
        months = workflow.get("jobs", {}).get("finance-months", {})
        strategy = months.get("strategy", {})
        if (months.get("needs") != "finance-audit"
                or months.get("uses") != "./.github/workflows/parser-stage.yml"
                or months.get("with", {}).get("stage") != "finance-month"
                or months.get("with", {}).get("month") != "${{ matrix.month }}"
                or str(strategy.get("max-parallel")) != "1"
                or str(strategy.get("fail-fast")).lower() != "true"
                or strategy.get("matrix") != {
                    "month": "${{ fromJSON(needs.finance-audit.outputs.months) }}"}):
            errors.append("finance-months: require the complete frozen matrix, one job at a time")
        finish = workflow.get("jobs", {}).get("finish", {})
        if set(finish.get("needs", [])) != {"validate", "finance-months", *STAGES}:
            errors.append("finish: must await every parser job before releasing the lock")
        if finish.get("if") != (
            "always() && needs.validate.result == 'success'"
            " && needs.legislature.result != 'skipped'"
        ):
            errors.append("finish: must not publish or acquire a lock during policy-only runs")
    if name == "parser-stage.yml":
        job = workflow.get("jobs", {}).get("stage", {})
        if (set(events) != {"workflow_call"} or job.get("environment") != "nightly-parser"
                or job.get("if") != "github.ref == 'refs/heads/main'"
                or str(job.get("timeout-minutes")) != "330"):
            errors.append("parser helper requires main, its environment, and bounded runtime")
        if job.get("env", {}).get("SOURCE_POLICY_REPORT") != (
            "${{ github.workspace }}/.private/policies/report.json"
        ):
            errors.append("parser helper requires a private shared policy report")
        steps = job.get("steps", [])
        policy_indices = [i for i, s in enumerate(steps)
                          if s.get("run") == "uv run --locked python -m nightly.policies restore"]
        run_indices = [i for i, s in enumerate(steps)
                       if s.get("name") == "Run collection or parsing (private diagnostics)"]
        if (len(policy_indices) != 1 or len(run_indices) != 1
                or policy_indices[0] >= run_indices[0]
                or steps[policy_indices[0]].get("if") != "steps.restore.outputs.needed == 'true'"):
            errors.append("parser helper must restore policy checks before collection")
        for step in job.get("steps", []):
            if step.get("uses", "").startswith(("actions/cache", "actions/upload-artifact")):
                errors.append("parser data must not enter Actions caches or artifacts")
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
