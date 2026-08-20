"""Importer derivation rules: identifiers, referrals, and the graveyard flag."""

import pytest

from importer.import_openstates import (
    bill_key,
    committee_from_referral,
    derive_graveyard,
    normalize_identifier,
)


def action(
    description: str, classification: list[str] | None = None, chamber: str = "lower"
) -> dict:
    return {
        "description": description,
        "date": "2025-06-01T05:00:00+00:00",
        "classification": classification or [],
        "chamber": chamber,
    }


SJR1 = "Failed to pass pursuant to Senate Joint Resolution 1"


def test_identifier_normalization() -> None:
    assert normalize_identifier("AB656") == "AB 656"
    assert normalize_identifier("sb 1") == "SB 1"
    assert normalize_identifier("SJR12") == "SJR 12"
    with pytest.raises(ValueError):
        normalize_identifier("not a bill")


def test_bill_key_is_url_friendly() -> None:
    assert bill_key("2025", "AB 656") == "2025-ab656"
    assert bill_key("2026S1", "SB 1") == "2026s1-sb1"


def test_committee_extracted_from_referral() -> None:
    assert (
        committee_from_referral(
            "Read first time and referred to Committee on Children and Families"
        )
        == "Children and Families"
    )
    assert (
        committee_from_referral("Referred to Joint Committee on Finance")
        == "Joint Committee on Finance"
    )
    assert committee_from_referral("Referred to calendar of 3-12-2026") is None
    assert committee_from_referral("Read a third time and passed") is None


def test_referred_never_heard_then_sjr1_dies() -> None:
    actions = [
        action("Introduced"),
        action(
            "Read first time and referred to Committee on Children and Families",
            ["reading-1", "referral-committee"],
        ),
        action(SJR1),
    ]
    died, committee, chamber = derive_graveyard(actions)
    assert died == 1
    assert committee == "Children and Families"
    assert chamber == "lower"


def test_hearing_before_sjr1_is_not_graveyard() -> None:
    actions = [
        action("Read first time and referred to Committee on Health", ["referral-committee"]),
        action("Public hearing held"),
        action(SJR1),
    ]
    assert derive_graveyard(actions) == (0, "Health", "lower")


def test_executive_session_counts_as_heard() -> None:
    actions = [
        action("Read first time and referred to Committee on Health", ["referral-committee"]),
        action("Executive session held"),
        action(SJR1),
    ]
    died, _, _ = derive_graveyard(actions)
    assert died == 0


def test_no_sjr1_action_is_not_graveyard() -> None:
    actions = [
        action("Read first time and referred to Committee on Health", ["referral-committee"]),
    ]
    assert derive_graveyard(actions) == (0, None, None)


def test_sjr1_without_referral_is_not_graveyard() -> None:
    assert derive_graveyard([action("Introduced"), action(SJR1)]) == (0, None, None)


def test_hearing_times_convert_utc_to_central() -> None:
    from importer.import_openstates import to_local

    assert to_local("2025-01-07T15:00:00+00:00") == ("2025-01-07", "09:00")  # CST
    assert to_local("2025-06-03T15:00:00+00:00") == ("2025-06-03", "10:00")  # CDT
    # a UTC time past midnight lands on the previous Central day
    assert to_local("2025-06-04T02:30:00+00:00") == ("2025-06-03", "21:30")
    assert to_local("") == (None, None)


def test_committee_index_is_chamber_scoped() -> None:
    from importer.committees import Committee, CommitteeIndex

    index = CommitteeIndex(
        [
            Committee("c1", "Children and Families", "lower", "p1", "Rep. Chair"),
            Committee("c2", "Children and Families", "upper", "p2", "Sen. Chair"),
            Committee("c3", "Finance", None, "p3", "Co-Chair"),
        ]
    )
    assert index.find("Children and Families", "lower").chair_name == "Rep. Chair"
    assert index.find("Children and Families", "upper").chair_name == "Sen. Chair"
    assert index.find("Joint Committee on Finance", "lower").id == "c3"
    assert index.find("Unknown Committee", "lower") is None


def test_biennium_covers_special_sessions() -> None:
    from importer.import_openstates import TITLE_VOTERS, biennium

    assert biennium("2025") == "2025"
    assert biennium("2026S1") == "2025"
    assert biennium("2023S1") == "2023"
    # the 2025-26 speaker map applies to the special session too
    assert TITLE_VOTERS[(biennium("2026S1"), "lower")]["SPEAKER"] == "Vos"
    # historical sessions have no map yet: titles there must hard-fail
    assert (biennium("2011"), "lower") not in TITLE_VOTERS
