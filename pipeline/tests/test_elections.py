"""WI election-cycle rules — the 2024/2026/2028 acceptance cases."""

from importer.elections import (
    assembly_districts_on_ballot,
    next_election_year,
    senate_districts_on_ballot,
)


def test_assembly_every_even_year_all_99() -> None:
    for year in (2024, 2026, 2028):
        assert assembly_districts_on_ballot(year) == list(range(1, 100))
    assert assembly_districts_on_ballot(2025) == []


def test_senate_2026_midterm_odd_districts() -> None:
    districts = senate_districts_on_ballot(2026)
    assert len(districts) == 17
    assert all(d % 2 == 1 for d in districts)
    assert 1 in districts and 33 in districts


def test_senate_2024_presidential_even_districts() -> None:
    districts = senate_districts_on_ballot(2024)
    assert len(districts) == 16
    assert all(d % 2 == 0 for d in districts)


def test_senate_2028_presidential_even_districts() -> None:
    assert senate_districts_on_ballot(2028) == senate_districts_on_ballot(2024)


def test_next_election_for_assembly_is_next_even_year() -> None:
    assert next_election_year("lower", 15, 2026) == 2026
    assert next_election_year("lower", 15, 2027) == 2028


def test_next_election_for_senate_respects_stagger() -> None:
    assert next_election_year("upper", 5, 2026) == 2026   # odd district, midterm
    assert next_election_year("upper", 6, 2026) == 2028   # even district waits
    assert next_election_year("upper", 6, 2028) == 2028
    assert next_election_year("upper", 5, 2028) == 2030
