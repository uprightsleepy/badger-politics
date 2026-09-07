"""Offline candidate lead indexing retains every source candidacy."""

import pytest

from scraper.ftm_leads import candidate_index


def candidate(name: str, candidate_id) -> dict:
    return {"Candidate": {"Candidate": name, "id": candidate_id}}


def test_candidate_index_preserves_candidacies_across_cycles():
    records = [
        (2024, [candidate("JACQUE, ANDRÉ M.", "12"), candidate("JACQUE, ANDRE", 13)]),
        (2022, [candidate("JACQUE, ANDRE", "12"), candidate("Ada Lovelace", 20)]),
    ]
    assert candidate_index(records) == {
        "andre jacque": [
            (12, 2024, "JACQUE, ANDRÉ M."),
            (13, 2024, "JACQUE, ANDRE"),
            (12, 2022, "JACQUE, ANDRE"),
        ],
        "ada lovelace": [(20, 2022, "Ada Lovelace")],
    }


def test_candidate_index_skips_missing_names_and_ids_but_keeps_zero_id():
    records = [(2024, [
        {}, {"Candidate": {}}, candidate("", 1), candidate(" , . ", 2),
        candidate("DOE, JANE", None), candidate("CHER", 0),
    ])]
    assert candidate_index(records) == {"cher cher": [(0, 2024, "CHER")]}


def test_candidate_index_rejects_invalid_ids():
    with pytest.raises(ValueError):
        candidate_index([(2024, [candidate("DOE, JANE", "invalid")])])
