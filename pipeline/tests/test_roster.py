"""Vote attribution: chamber-scoped, alias-aware, and never a best guess."""

import pytest

from importer.roster import (
    AmbiguousNameError,
    Member,
    Roster,
    UnmatchedNameError,
)


def member(name: str, chamber: str, district: int, aliases: list[str] | None = None) -> Member:
    return Member(
        id=f"ocd-person/{name.replace(' ', '-').lower()}-{district}",
        name=name,
        family_name=name.split()[-1],
        party="Test",
        chamber=chamber,
        district=district,
        image_url=None,
        aliases=aliases or [],
    )


@pytest.fixture()
def roster() -> Roster:
    return Roster(
        [
            member("Adam Neylon", "lower", 15, aliases=["Neylon, A.", "NEYLON, A"]),
            member("Joan Ballweg", "upper", 14),
            # deliberate same-surname pair in one chamber
            member("Alice Johnson", "lower", 40),
            member("Robert Johnson", "lower", 41),
            # same surname across chambers is fine
            member("Sam Rivera", "lower", 7),
            member("Dana Rivera", "upper", 3),
        ]
    )


def test_surname_resolves_within_chamber(roster: Roster) -> None:
    assert roster.resolve("Neylon", "lower").name == "Adam Neylon"


def test_allcaps_assembly_style_resolves(roster: Roster) -> None:
    assert roster.resolve("NEYLON", "lower").name == "Adam Neylon"


def test_alias_forms_resolve(roster: Roster) -> None:
    assert roster.resolve("Neylon, A.", "lower").name == "Adam Neylon"
    assert roster.resolve("NEYLON, A", "lower").name == "Adam Neylon"


def test_cross_chamber_duplicate_surname_is_fine(roster: Roster) -> None:
    assert roster.resolve("RIVERA", "lower").district == 7
    assert roster.resolve("Rivera", "upper").district == 3


def test_same_chamber_duplicate_surname_hard_fails(roster: Roster) -> None:
    with pytest.raises(AmbiguousNameError, match="Johnson"):
        roster.resolve("JOHNSON", "lower")


def test_duplicate_surname_full_name_still_resolves(roster: Roster) -> None:
    assert roster.resolve("Alice Johnson", "lower").district == 40


def test_unknown_name_hard_fails(roster: Roster) -> None:
    with pytest.raises(UnmatchedNameError):
        roster.resolve("ZZYZX", "lower")


def test_wrong_chamber_hard_fails(roster: Roster) -> None:
    with pytest.raises(UnmatchedNameError):
        roster.resolve("Ballweg", "lower")


def test_lenient_variant_returns_none_never_guesses(roster: Roster) -> None:
    assert roster.resolve_or_none("JOHNSON", "lower") is None
    assert roster.resolve_or_none("ZZYZX", "upper") is None


def test_truncated_long_surname_resolves_by_prefix() -> None:
    r = Roster([member("Marisabel Cabral-Guevara", "lower", 55)])
    assert r.resolve("CABRAL-GUEVA", "lower").name == "Marisabel Cabral-Guevara"


def test_short_prefix_never_drifts() -> None:
    r = Roster([member("Dale Kruger", "lower", 1)])
    # short names must not prefix-match longer surnames
    with pytest.raises(UnmatchedNameError):
        r.resolve("KRUG", "lower")


def test_truncation_ambiguity_hard_fails() -> None:
    r = Roster(
        [
            member("Ana Gonzalez-Rivera", "lower", 1),
            member("Bo Gonzalez-Riviera", "lower", 2),
        ]
    )
    with pytest.raises(AmbiguousNameError):
        r.resolve("GONZALEZ-RIV", "lower")
