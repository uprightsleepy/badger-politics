"""Vote attribution: chamber-scoped, alias-aware, and never a best guess."""

import pytest

from importer.roster import (
    AmbiguousNameError,
    Member,
    Person,
    Roster,
    Term,
    UnmatchedNameError,
    find_person,
    merge_listing,
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


def person(name: str, chamber: str, district: int, aliases: list[str] | None = None) -> Person:
    return Person(
        id=f"ocd-person/{name.replace(' ', '-').lower()}",
        name=name,
        family_name=name.split()[-1],
        party="Test",
        image_url=None,
        aliases=aliases or [],
        terms=[Term(chamber, district, "2019-01-07", "2023-01-03")],
    )


def test_listing_newcomer_never_inherits_a_retired_surname() -> None:
    # Bob Smith has no people file; Alice Smith once held another seat
    people = [person("Alice Smith", "lower", 40)]
    with pytest.raises(UnmatchedNameError):
        find_person(people, "Bob Smith", "lower", 12)
    with pytest.raises(UnmatchedNameError):
        merge_listing(
            Roster([]), [{"name": "Bob Smith", "chamber": "lower", "district": 12}], people
        )


def test_listing_nickname_resolves_within_its_seat() -> None:
    people = [person("Robert Smith", "lower", 12), person("Alice Smith", "lower", 40)]
    roster = merge_listing(
        Roster([]), [{"name": "Bob Smith", "chamber": "lower", "district": 12}], people
    )
    (m,) = roster.members
    assert (m.name, m.district, m.from_listing) == ("Robert Smith", 12, True)
