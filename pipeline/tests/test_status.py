"""Status derivation covers every lifecycle branch."""

from importer.status import derive_status


def action(classification: str, chamber: str = "lower", description: str = "") -> dict:
    return {"classification": classification, "chamber": chamber, "description": description}


SJR1 = "Failed to pass pursuant to Senate Joint Resolution 1"


def test_introduced() -> None:
    assert derive_status([action("introduction")]) == "introduced"


def test_in_committee() -> None:
    assert derive_status([action("reading-1,referral-committee")]) == "in_committee"


def test_passed_one_chamber() -> None:
    actions = [action("referral-committee"), action("passage,reading-3", "lower")]
    assert derive_status(actions) == "passed_chamber"


def test_passed_both_chambers() -> None:
    actions = [action("passage,reading-3", "lower"), action("passage", "upper")]
    assert derive_status(actions) == "passed"


def test_enacted_via_became_law() -> None:
    actions = [action("passage", "lower"), action("passage", "upper"), action("became-law")]
    assert derive_status(actions) == "enacted"


def test_vetoed() -> None:
    actions = [action("passage", "lower"), action("passage", "upper"), action("executive-veto")]
    assert derive_status(actions) == "vetoed"


def test_failed_override_stays_vetoed() -> None:
    actions = [
        action("passage", "lower"),
        action("passage", "upper"),
        action("executive-veto"),
        action("failure", description="Failed to pass notwithstanding the objections"
                                      " of the Governor pursuant to Joint Rule 82"),
    ]
    assert derive_status(actions) == "vetoed"


def test_partial_veto_is_enacted() -> None:
    actions = [action("executive-veto-line-item"), action("became-law")]
    assert derive_status(actions) == "enacted"


def test_failed_sjr1() -> None:
    actions = [action("reading-1,referral-committee"), action("failure", description=SJR1)]
    assert derive_status(actions) == "failed_sjr1"


def test_all_sjr1_phrasings_die() -> None:
    for verb in ("pass", "concur in", "adopt"):
        desc = f"Failed to {verb} pursuant to Senate Joint Resolution 1"
        assert derive_status([action("failure", description=desc)]) == "failed_sjr1", verb


def test_sjr1_outranks_passed_chamber() -> None:
    actions = [action("passage", "lower"), action("failure", description=SJR1)]
    assert derive_status(actions) == "failed_sjr1"


def test_database_string_classification_form() -> None:
    # database rows carry classification as a comma-joined string
    assert derive_status([{"classification": "passage,reading-3", "chamber": "lower"}]) == (
        "passed_chamber"
    )
