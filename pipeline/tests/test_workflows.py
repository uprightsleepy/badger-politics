"""Release policy rejects regressions even when YAML formatting changes."""

from copy import deepcopy

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
