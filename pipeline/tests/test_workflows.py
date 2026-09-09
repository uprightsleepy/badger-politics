"""Release policy rejects regressions even when YAML formatting changes."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from check_workflows import validate

WORKFLOW = {
    "on": {"push": {}, "workflow_dispatch": {}},
    "permissions": {"contents": "read"},
    "jobs": {
        "validate": {"uses": "./.github/workflows/ci.yml"},
        "deploy": {
            "needs": "validate",
            "environment": "dev",
            "permissions": {"contents": "read", "id-token": "write"},
            "steps": [{"uses": "actions/checkout@" + "a" * 40}],
        },
    },
}


def test_valid_release() -> None:
    assert validate(WORKFLOW, "deploy.yml") == []


def test_mutable_action_and_missing_validation_fail() -> None:
    workflow = deepcopy(WORKFLOW)
    workflow["jobs"]["deploy"]["steps"][0]["uses"] = "actions/checkout@v4"
    workflow["jobs"]["deploy"].pop("needs")
    errors = validate(workflow, "deploy.yml")
    assert any("full commit SHA" in error for error in errors)
    assert any("depend on validation" in error for error in errors)


def test_pull_request_cannot_obtain_deploy_credentials() -> None:
    workflow = deepcopy(WORKFLOW)
    workflow["on"] = ["pull_request_target"]
    errors = validate(workflow, "deploy.yml")
    assert any("trusted trigger" in error for error in errors)
    assert any("only use push" in error for error in errors)


def test_job_permissions_and_raw_cache_are_checked() -> None:
    workflow = deepcopy(WORKFLOW)
    workflow["jobs"]["deploy"]["permissions"]["contents"] = "write"
    workflow["jobs"]["deploy"]["steps"].append({
        "uses": "actions/cache@" + "b" * 40,
        "with": {"path": "data/wi.sqlite.gz", "key": "snapshot-example"},
    })
    errors = validate(workflow, "deploy.yml")
    assert any("forbidden write" in error for error in errors)
    assert any("must not enter" in error for error in errors)


def deploy_workflow():
    path = Path(__file__).resolve().parents[2] / ".github/workflows/deploy.yml"
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


@pytest.mark.parametrize(("field", "value", "allowed"), [
    ("conclusion", "success", True),
    ("conclusion", "failure", False),
    ("conclusion", "cancelled", False),
    ("conclusion", "skipped", False),
    ("display_title", "source policy checks", False),
    ("head_branch", "feature", False),
    ("repository", "someone/fork", False),
    ("event", "workflow_dispatch", True),
    ("event", "pull_request", False),
    ("event", "pull_request_target", False),
])
def test_only_successful_main_parsers_release(field, value, allowed):
    workflow = deploy_workflow()
    assert validate(workflow, "deploy.yml") == []
    values = dict(conclusion="success", display_title="nightly parser", head_branch="main",
                  repository="uprightsleepy/badger-politics", event="schedule")
    values[field] = value
    repository = values.pop("repository")
    run = SimpleNamespace(**values, head_repository=SimpleNamespace(full_name=repository))
    github = SimpleNamespace(ref="refs/heads/main", event_name="workflow_run",
                             repository="uprightsleepy/badger-politics",
                             event=SimpleNamespace(workflow_run=run))
    # Evaluate the checked-in boolean guard with fixture contexts, without builtins.
    condition = " ".join(workflow["jobs"]["validate"]["if"].split())
    condition = condition.replace("&&", " and ").replace("||", " or ")
    assert eval(condition, {"__builtins__": {}}, {"github": github}) is allowed


@pytest.mark.parametrize("mutation", [
    "guard", "branch", "event", "target", "concurrency", "workflow_concurrency",
])
def test_automatic_release_boundaries_cannot_be_weakened(mutation):
    workflow = deploy_workflow()
    if mutation == "guard":
        workflow["jobs"]["validate"].pop("if")
    elif mutation == "branch":
        workflow["on"]["workflow_run"].pop("branches")
    elif mutation == "event":
        workflow["on"]["workflow_run"]["types"] = ["requested"]
    elif mutation == "target":
        workflow["env"]["TARGET"] = "badgerpolitics-prod"
    elif mutation == "concurrency":
        workflow["jobs"]["deploy"]["concurrency"]["cancel-in-progress"] = "true"
    elif mutation == "workflow_concurrency":
        workflow["concurrency"] = workflow["jobs"]["deploy"].pop("concurrency")
    assert validate(workflow, "deploy.yml")


@pytest.mark.parametrize("change", [None, "stale", "missing"])
def test_live_metadata_must_match_the_built_snapshot(tmp_path, monkeypatch, change):
    import json
    import subprocess
    import sys

    steps = deploy_workflow()["jobs"]["deploy"]["steps"]
    smoke = next(step["run"] for step in steps if step.get("name") == "Smoke-test what is live")
    script = smoke.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    expected = {"imported_at": "2026-09-09T16:00:00+00:00", "data_through": "2026-08-18"}
    actual = dict(expected)
    if change == "stale":
        actual["imported_at"] = "2026-09-02T00:19:32-05:00"
    elif change == "missing":
        expected.pop("imported_at")
        actual.pop("imported_at")
    monkeypatch.chdir(tmp_path)
    metadata = tmp_path / "site/public/api/v1/meta.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps(expected), encoding="utf-8")
    live = tmp_path / "live.json"
    live.write_text(json.dumps(actual, sort_keys=True), encoding="utf-8")
    result = subprocess.run([sys.executable, "-", str(live)], input=script, text=True,
                            capture_output=True)
    assert result.returncode == (0 if change is None else 1)
