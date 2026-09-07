"""Canvass validation preserves rows, attribution, and the previous database."""

import copy
import re
import sqlite3

import pytest

from importer import import_wec_results as wec

TABLES = ("election_history", "statewide_history", "statewide_county_results")
OFFICE = "ATTORNEY GENERAL"


def legislative(year=2022, districts=95):
    return [
        (year, "lower", district, name, party, votes, 10)
        for district in range(1, districts + 1)
        for name, party, votes in (("Candidate A", "DEM", 4), ("Candidate B", "REP", 6))
    ]


def statewide(year=2022, office=OFFICE, votes=(250_000, 250_000), county_count=72):
    rows, counties = [], []
    for index, total in enumerate(votes):
        name = f"Candidate {index}"
        party = ("DEM", "REP")[index % 2]
        rows.append((year, office, name, party, total, sum(votes)))
        for county in range(county_count):
            amount = total // county_count + (county < total % county_count)
            counties.append((year, office, f"County {county:02}", name, party, amount))
    return rows, counties


@pytest.fixture()
def run_case(tmp_path, monkeypatch, make_db):
    archive = tmp_path / "canvasses"
    archive.mkdir()
    db_path = tmp_path / "wi.sqlite"
    conn = make_db(db_path)
    conn.execute("INSERT INTO election_history VALUES (2020, 'lower', 1, 'Old', NULL, 1, 1)")
    conn.execute("INSERT INTO statewide_history VALUES (2020, 'Old office', 'Old', NULL, 1, 1)")
    conn.execute(
        "INSERT INTO statewide_county_results VALUES (2020, 'Old office', 'Old', 'Old', NULL, 1)"
    )
    conn.commit()
    conn.close()
    before = db_path.read_bytes()

    def run(workbooks, error=None):
        original = copy.deepcopy(workbooks)
        for name in workbooks:
            (archive / name).touch()
        monkeypatch.setattr(wec, "parse_all", lambda path: workbooks[path.name])
        if error:
            with pytest.raises(RuntimeError, match=f"^{re.escape(error)}$"):
                wec.run(archive, db_path)
            assert db_path.read_bytes() == before
        else:
            assert wec.run(archive, db_path) == 0
            with sqlite3.connect(db_path) as conn:
                for index, table in enumerate(TABLES):
                    expected = [
                        row for name in sorted(workbooks) for row in workbooks[name][index]
                    ]
                    actual = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
                    assert actual == expected
        assert workbooks == original

    return run


def test_multiple_workbooks_years_and_offices_preserve_every_row_in_order(run_case):
    sw_2022, counties_2022 = statewide()
    sw_2024, counties_2024 = statewide(2024)
    sw_governor, counties_governor = statewide(2024, "GOVERNOR / LIEUTENANT GOVERNOR")
    leg = legislative()
    zero_row = (2022, "lower", 1, "Zero votes", None, 0, 0)
    leg.extend([zero_row, zero_row])
    counties_2022.append((2020, "Unrelated office", "Other county", "Other", None, 17))
    run_case({
        "z-2024.xlsx": (
            legislative(2024), sw_governor + sw_2024, counties_2024 + counties_governor,
        ),
        "a-2022.xlsx": (leg, sw_2022, counties_2022),
    })


def test_duplicate_candidate_names_ignore_party_and_duplicate_counties_are_not_dropped(run_case):
    sw, counties = statewide(votes=(250_000,))
    candidate = sw[0]
    sw = [(*candidate[:3], party, 250_000, 500_000) for party in ("DEM", "REP")]
    first = counties.pop(0)
    counties[:0] = [(*first[:4], "DEM", 1), (*first[:4], "REP", first[5] - 1)]
    run_case({"votes.xlsx": (legislative(), sw, counties)})


def test_later_total_cast_values_do_not_replace_the_first_row(run_case):
    leg = legislative()
    leg[1] = (*leg[1][:6], 0)
    sw, counties = statewide()
    sw[1] = (*sw[1][:5], 0)
    run_case({"votes.xlsx": (leg, sw, counties)})


def test_first_legislative_total_cast_is_used_even_if_later_value_is_valid(run_case):
    leg = legislative()
    leg[0] = (*leg[0][:6], 9)
    run_case(
        {"votes.xlsx": (leg, [], [])},
        "(2022, 'lower', 1): total cast below candidate sum — bad parse",
    )


@pytest.mark.parametrize("districts", [94, 95])
def test_assembly_threshold_counts_distinct_districts(run_case, districts):
    leg = legislative(districts=districts)
    leg.extend((2022, "lower", 1, "Zero votes", None, 0, 0) for _ in range(5))
    error = (
        f"2022: only {districts} Assembly districts parsed — format drift?"
        if districts < 95 else None
    )
    run_case({"votes.xlsx": (leg, [], [])}, error)


@pytest.mark.parametrize("total", [499_999, 500_000])
def test_statewide_turnout_threshold(run_case, total):
    sw, counties = statewide(votes=(250_000, total - 250_000))
    error = (
        f"2022 {OFFICE}: 2 candidates, {total} votes — format drift?"
        if total < 500_000 else None
    )
    run_case({"votes.xlsx": (legislative(), sw, counties)}, error)


def test_statewide_requires_two_candidates(run_case):
    sw, counties = statewide(votes=(500_000,))
    run_case(
        {"votes.xlsx": (legislative(), sw, counties)},
        f"2022 {OFFICE}: 1 candidates, 500000 votes — format drift?",
    )


def test_first_statewide_total_cast_is_used_even_if_later_value_is_valid(run_case):
    sw, counties = statewide()
    sw[0] = (*sw[0][:5], 499_999)
    run_case(
        {"votes.xlsx": (legislative(), sw, counties)},
        f"2022 {OFFICE}: 2 candidates, 500000 votes — format drift?",
    )


@pytest.mark.parametrize("count", [71, 73])
def test_county_coverage_requires_exactly_72_distinct_counties(run_case, count):
    sw, counties = statewide(county_count=count)
    run_case(
        {"votes.xlsx": (legislative(), sw, counties)},
        f"2022 {OFFICE}: {count} counties parsed, expected 72",
    )


def test_county_candidate_mismatch_is_rejected(run_case):
    sw, counties = statewide()
    counties[0] = (*counties[0][:5], counties[0][5] + 1)
    run_case(
        {"votes.xlsx": (legislative(), sw, counties)},
        f"2022 {OFFICE} Candidate 0: county sum 250001 != statewide 250000",
    )


def test_duplicate_county_rows_still_contribute_to_the_sum(run_case):
    sw, counties = statewide()
    counties.append(counties[0])
    run_case(
        {"votes.xlsx": (legislative(), sw, counties)},
        f"2022 {OFFICE} Candidate 0: county sum {250_000 + counties[0][5]} != statewide 250000",
    )


def test_duplicate_legislative_rows_still_contribute_to_the_sum(run_case):
    leg = legislative()
    leg.append(leg[0])
    run_case(
        {"votes.xlsx": (leg, [], [])},
        "(2022, 'lower', 1): total cast below candidate sum — bad parse",
    )


def test_multiple_invalid_contests_keep_existing_set_traversal(run_case):
    leg = legislative() + legislative(2024)
    bad = {(2022, "lower", 1), (2024, "lower", 2)}
    leg = [(*row[:6], 0) if row[:3] in bad else row for row in leg]
    first = next(key for key in {(r[0], r[1], r[2]) for r in leg} if key in bad)
    run_case(
        {"votes.xlsx": (leg, [], [])},
        f"{first}: total cast below candidate sum — bad parse",
    )


def test_multiple_statewide_failures_keep_existing_set_traversal(run_case):
    low_turnout, counties = statewide(votes=(100, 100))
    missing_county, partial_counties = statewide(2024, county_count=71)
    sw = missing_county + low_turnout
    errors = {
        (2022, OFFICE): f"2022 {OFFICE}: 2 candidates, 200 votes — format drift?",
        (2024, OFFICE): f"2024 {OFFICE}: 71 counties parsed, expected 72",
    }
    first = next(iter({(r[0], r[1]) for r in sw}))
    run_case(
        {"votes.xlsx": (legislative(), sw, counties + partial_counties)}, errors[first],
    )


def test_statewide_validation_does_not_override_an_assembly_coverage_error(run_case):
    sw, counties = statewide(votes=(1,))
    run_case(
        {"votes.xlsx": (legislative(districts=94), sw, counties)},
        "2022: only 94 Assembly districts parsed — format drift?",
    )


def test_empty_legislative_results_leave_previous_database_untouched(run_case, tmp_path):
    run_case(
        {"votes.xlsx": ([], [], [])},
        f"no legislative contests parsed from {tmp_path / 'canvasses'}",
    )
