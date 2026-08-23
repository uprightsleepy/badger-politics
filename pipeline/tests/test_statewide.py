"""Statewide contests: canvass parsing, ticket names, and drift alarms."""

from pathlib import Path

import pytest
from openpyxl import Workbook

from importer.import_wec import STATEWIDE_OFFICES, load_candidates
from importer.import_wec_results import _ticket, parse_statewide


def _canvass(tmp_path: Path, header: str, rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(["WEC Canvass Reporting System"])
    ws.append(["2022 General Election"])
    ws.append([header])
    for row in rows:
        ws.append(row)
    path = tmp_path / "canvass.xlsx"
    wb.save(path)
    return path


def test_statewide_contest_parses_with_ticket_names(tmp_path: Path) -> None:
    path = _canvass(tmp_path, "GOVERNOR / LIEUTENANT GOVERNOR", [
        ["", "", "Total Votes Cast", "DEM", "REP"],
        ["", "", "", "Tony Evers \n Sara Rodriguez", "Tim Michels \n Roger Roth"],
        ["ADAMS", "Town of ADAMS", 10, 4, 6],
        ["", "Town of BIG FLATS", 20, 12, 8],
    ])
    rows = parse_statewide(path)
    assert rows == [
        (2022, "GOVERNOR / LIEUTENANT GOVERNOR", "Tony Evers / Sara Rodriguez", "DEM", 16),
        (2022, "GOVERNOR / LIEUTENANT GOVERNOR", "Tim Michels / Roger Roth", "REP", 14),
    ]


def test_legislative_contest_is_not_statewide(tmp_path: Path) -> None:
    path = _canvass(tmp_path, "STATE SENATOR DISTRICT 5", [
        ["", "", "Total Votes Cast", "DEM", "REP"],
        ["", "", "", "A", "B"],
        ["X", "Town of X", 10, 4, 6],
    ])
    assert parse_statewide(path) == []


def test_ticket_normalization() -> None:
    assert _ticket("Tony Evers \n Sara  Rodriguez") == "Tony Evers / Sara Rodriguez"
    assert _ticket("Joan Ellis Beglinger \n") == "Joan Ellis Beglinger"


def test_unrecognized_office_fails_loudly(tmp_path: Path) -> None:
    csv_path = tmp_path / "candidates.csv"
    csv_path.write_text(
        "office,incumbent,incumbent_noncandidacy,candidate,party,ballot_status\n"
        "COUNTY SHERIFF,,0,Somebody New,Independent,Approve\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="unrecognized office"):
        load_candidates(csv_path)


def test_statewide_offices_are_the_constitutional_five() -> None:
    assert STATEWIDE_OFFICES == {
        "GOVERNOR", "LIEUTENANT GOVERNOR", "ATTORNEY GENERAL",
        "SECRETARY OF STATE", "STATE TREASURER",
    }
