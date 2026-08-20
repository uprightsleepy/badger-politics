"""WEC candidate-name matching: tolerant of format noise, strict on identity."""

from importer.import_wec import family_key, match_candidate, same_person


def test_middle_initial_and_accents_ignored() -> None:
    assert same_person("Robin J. Vos", "Robin Vos")
    assert same_person("André Jacque", "Andre Jacque")


def test_suffix_stripped() -> None:
    assert same_person("Russell Antonio Goodwin, Sr.", "Russell Goodwin")
    assert family_key("Russell Antonio Goodwin, Sr.") == "goodwin"


def test_hyphenated_surname_matches_spaced_form() -> None:
    assert same_person("Amaad Rivera Wagner", "Amaad Rivera-Wagner")


def test_different_people_do_not_match() -> None:
    assert not same_person("Alice Johnson", "Robert Johnson")


def row(candidate: str, status: str = "Approve") -> dict:
    return {"candidate": candidate, "party": "Test", "ballot_status": status}


def test_nickname_matches_via_unique_family_fallback() -> None:
    rows = [row("Nate Gustafson"), row("Maria Lopez")]
    assert match_candidate("Gus Gustafson", rows) == [rows[0]]


def test_family_fallback_refuses_ambiguity() -> None:
    rows = [row("Russell Goodwin, Sr."), row("Russell Goodwin, Jr.")]
    # both reduce to the same strict key too — no unique answer, no guess
    assert match_candidate("Rusty Goodwin", rows) == []


def test_strict_match_beats_fallback() -> None:
    rows = [row("Jane Smith"), row("John Smith")]
    assert match_candidate("Jane Smith", rows) == [rows[0]]
