"""Older and spring canvasses: G.A.B.-era titles, judicial races, statewide
referenda, and the guards that keep each file to its own election.

Rows are trimmed from the real certified workbooks (Assembly District 11,
2014; State Senate District 8 special and Court of Appeals District 4, 2023;
the 2025 photo ID question), with Office Totals restated for the trim."""

import sqlite3
from pathlib import Path

import pytest
from openpyxl import Workbook

from importer import import_wec_results as wec
from importer.checks import check_results


def _workbook(path: Path, election: str, contests: list[tuple[str, list[list]]]) -> Path:
    """One sheet per contest after a 'Document map', as the reports are laid out."""
    wb = Workbook()
    wb.active.title = "Document map"
    wb.active.append(["Ward by Ward Report"])
    for title, _ in contests:
        wb.active.append([None, title])
    for title, rows in contests:
        ws = wb.create_sheet()
        for row in (["WEC Canvass Reporting System"], ["Ward by Ward Report"], [election],
                    [title], *rows):
            ws.append(row)
    wb.save(path)
    return path


ASSEMBLY_11_2014 = ("ASSEMBLY - DISTRICT 11", [
    ["", None, "Total Votes Cast", "DEM", ""],
    [None, None, None, "MANDELA BARNES", "SCATTERING"],
    ["MILWAUKEE ", "CITY OF GLENDALE WARDS 1, 7", 783, 783, 0],
    [None, "CITY OF GLENDALE WARDS 2, 8S", 531, 525, 6],
    [None, "County Totals:", 1314, 1308, 6],
    ["Office Totals:", None, 1314, 1308, 6],
])
SENATE_8_SPECIAL = ("STATE SENATOR DISTRICT 8", [
    ["", None, "Total Votes Cast", "DEM", "REP", ""],
    [None, None, None, "Jodi Habush Sinykin", "Dan Knodl", "SCATTERING"],
    ["MILWAUKEE ", "Village of BAYSIDE Wards 1,3", 1200, 700, 499, 1],
    [None, "County Totals:", 1200, 700, 499, 1],
    ["Office Totals:", None, 1200, 700, 499, 1],
])
APPEALS_4_2023 = ("COURT OF APPEALS JUDGE DISTRICT 4", [
    ["", None, "Total Votes Cast", "NP", ""],
    [None, None, None, "Chris Taylor", "SCATTERING"],
    ["DANE ", "City of MADISON Ward 1", 412, 410, 2],
    [None, "County Totals:", 412, 410, 2],
    ["Office Totals:", None, 412, 410, 2],
])


def _statewide(title: str, header: list, names: list, county_votes: list[list[int]]):
    """A statewide contest with one ward per county, all 72 counties."""
    rows = [["", None, "Total Votes Cast", *header], [None, None, None, *names]]
    for i in range(72):
        votes = county_votes[i % len(county_votes)]
        rows += [[f"COUNTY {i:02} ", f"Town of T{i} Ward 1", sum(votes), *votes],
                 [None, "County Totals:", sum(votes), *votes]]
    totals = [sum(county_votes[i % len(county_votes)][c] for i in range(72))
              for c in range(len(names))]
    rows.append(["Office Totals:", None, sum(totals), *totals])
    return title, rows


PHOTO_ID_2025 = _statewide("State of Wisconsin Referendum", ["", ""], ["YES", "NO"],
                           [[426, 118], [372, 97]])
SUPREME_2025 = _statewide("JUSTICE OF THE SUPREME COURT", ["NP", "NP", ""],
                          ["Brad  Schimel", "Susan Crawford", "SCATTERING"],
                          [[313, 234, 0], [205, 197, 1]])


def test_gab_era_titles_parse_as_legislative_and_statewide(tmp_path):
    governor = _statewide("GOVERNOR/LIEUTENANT GOVERNOR", ["DEM", "REP"],
                          ["MARY BURKE\nJOHN LEHMAN", "SCOTT WALKER\nREBECCA KLEEFISCH"],
                          [[233, 258]])
    path = _workbook(tmp_path / "ger2014.xlsx", "2014 GENERAL ELECTION",
                     [governor, ASSEMBLY_11_2014,
                      ("STATE SENATE – DISTRICT 17", ASSEMBLY_11_2014[1])])
    leg, sw, counties, judicial, referenda = wec.parse_all(path)
    assert leg == [(2014, "lower", 11, "MANDELA BARNES", "DEM", 1308, 1314),
                   (2014, "upper", 17, "MANDELA BARNES", "DEM", 1308, 1314)]
    # the office is stored under the heading the later canvasses use
    assert {r[1] for r in sw} == {"GOVERNOR / LIEUTENANT GOVERNOR"}
    assert sw[0][2] == "MARY BURKE / JOHN LEHMAN"
    assert len({r[2] for r in counties}) == 72
    assert judicial == referenda == []


def test_spring_canvass_yields_judicial_and_referendum_rows_only(tmp_path):
    path = _workbook(tmp_path / "spring2025.xlsx", "2025 Spring Election",
                     [SENATE_8_SPECIAL, SUPREME_2025, APPEALS_4_2023, PHOTO_ID_2025])
    leg, sw, counties, judicial, referenda = wec.parse_all(path)
    # a special legislative election is not a seat's regular general result
    assert leg == sw == counties == []
    assert [r[:7] for r in judicial] == [
        (2025, "spring", "JUSTICE OF THE SUPREME COURT", None, "Brad Schimel", 18648, 34200),
        (2025, "spring", "JUSTICE OF THE SUPREME COURT", None, "Susan Crawford", 15516, 34200),
        (2025, "spring", "COURT OF APPEALS JUDGE", 4, "Chris Taylor", 410, 412),
    ]
    assert judicial[0][7:] == (72, "spring2025.xlsx")
    assert referenda == [(2025, "spring", 1, "State of Wisconsin Referendum",
                          28728, 7740, 36468, 72, "spring2025.xlsx")]


def test_question_number_comes_from_the_title(tmp_path):
    title = "State of Wisconsin Election Officials Referendum - Question 2"
    path = _workbook(tmp_path / "spring2024.xlsx", "2024 Spring Election",
                     [(title, PHOTO_ID_2025[1])])
    assert wec.parse_all(path)[4][0][2:4] == (2, title)


@pytest.mark.parametrize("name,error", [
    ("spring2024.xlsx", "spring2024.xlsx: workbook is the 2025 spring canvass"),
    ("ger2025.xlsx", "ger2025.xlsx: workbook is the 2025 spring canvass"),
])
def test_a_pinned_name_must_match_the_workbooks_own_election(tmp_path, name, error):
    path = _workbook(tmp_path / name, "2025 Spring Election", [SUPREME_2025])
    with pytest.raises(RuntimeError, match=f"^{error}$"):
        wec.parse_all(path)


def _judicial(counties=72, cast=100, files=("spring2025.xlsx",)):
    return [(2025, "spring", "JUSTICE OF THE SUPREME COURT", None, f"C{i}", 40, cast,
             counties, name) for name in files for i in range(2)]


@pytest.mark.parametrize("rows,error", [
    (_judicial(counties=71), "counties parsed, expected 72"),
    (_judicial(cast=79), "total cast below candidate sum"),
    (_judicial(files=("spring2025.xlsx", "spring2025-copy.xlsx")), "in more than one file"),
    (_judicial(files=("spring2025-unpinned.xlsx",)), "not a pinned canvass file"),
])
def test_judicial_rows_are_held_to_the_certified_contest(rows, error):
    with pytest.raises(RuntimeError, match=error):
        wec._check_spring(rows, [])


@pytest.mark.parametrize("row,error", [
    ((2025, "spring", 1, "Q", 60, 40, 101, 72, "spring2025.xlsx"), "vs cast 101"),
    ((2025, "spring", 1, "Q", 60, 40, 100, 70, "spring2025.xlsx"), "70 counties"),
])
def test_referendum_rows_must_add_up_statewide(row, error):
    with pytest.raises(RuntimeError, match=error):
        wec._check_spring([], [row])
    with pytest.raises(RuntimeError, match="parsed twice"):
        good = (*row[:6], 100, 72, row[8])
        wec._check_spring([], [good, good])


def test_spring_rows_carry_their_pinned_source_url():
    judicial, referenda = wec._check_spring(
        _judicial(), [(2025, "spring", 1, "Q", 60, 40, 100, 72, "spring2025.xlsx")])
    assert {r[7] for r in judicial + referenda} == {wec.FILES["spring2025.xlsx"]}


@pytest.fixture()
def results_db(make_db):
    conn = make_db(":memory:")
    conn.executemany(
        "INSERT INTO election_history VALUES (?, ?, ?, 'A', NULL, 5, 10)",
        [(2024, "lower", d) for d in range(1, 100)] + [(2022, "upper", 17), (2024, "upper", 2)],
    )
    conn.execute("INSERT INTO judicial_history VALUES (2025, 'spring',"
                 " 'JUSTICE OF THE SUPREME COURT', NULL, 'A', 6, 10, 'u')")
    conn.execute("INSERT INTO referendum_history VALUES (2025, 'spring', 1, 'Q', 6, 4, 10, 'u')")
    return conn


def test_clean_results_pass(results_db):
    assert check_results(results_db) == []


@pytest.mark.parametrize("sql,failure", [
    ("INSERT INTO election_history VALUES (2024, 'upper', 3, 'B', NULL, 1, 10)",
     "Senate results for a seat not on that year's ballot: 1"),
    ("DELETE FROM election_history WHERE chamber = 'lower' AND district = 99",
     "general elections missing Assembly seats: 1"),
    ("INSERT INTO election_history VALUES (2024, 'lower', 1, 'A', NULL, 1, 10)",
     "a candidate listed twice in one legislative contest: 1"),
    ("UPDATE election_history SET total_cast = 4 WHERE chamber = 'upper' AND district = 17",
     "legislative contests above their official ballots cast: 1"),
    ("INSERT INTO judicial_history VALUES (2025, 'spring',"
     " 'JUSTICE OF THE SUPREME COURT', NULL, 'B', 5, 10, 'u')",
     "judicial contests above their official ballots cast: 1"),
    ("UPDATE referendum_history SET no = 5", "referendum yes + no differs from votes cast: 1"),
])
def test_results_checks_catch_each_broken_invariant(results_db, sql, failure):
    results_db.execute(sql)
    assert check_results(results_db) == [failure]


def test_judicial_and_referendum_tables_reject_unknown_values(make_db):
    conn = make_db(":memory:")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO judicial_history VALUES (2025, 'spring',"
                     " 'CIRCUIT COURT JUDGE', 1, 'A', 1, 1, 'u')")
