"""Import WEC ward-by-ward canvass spreadsheets into election_history.

Usage: python -m importer.import_wec_results <xlsx_dir> <sqlite_path>

Parses every .xlsx in the directory (the official 'Ward by Ward Report'
files from elections.wi.gov results pages). Each contest appears as a
title row ('STATE SENATOR DISTRICT 1'), a party header row containing
'Total Votes Cast', a candidate-name row, then ward rows whose votes are
summed per candidate. The election year comes from the report header
('2022 General Election'). Non-legislative contests are skipped.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

from openpyxl import load_workbook

CONTEST_RE = re.compile(
    r"^(STATE SENATOR|REPRESENTATIVE TO THE ASSEMBLY)\s+DISTRICT\s+(\d+)", re.I
)
YEAR_RE = re.compile(r"^(\d{4}) General Election", re.I)


def parse_workbook(path: Path) -> list[tuple[int, str, int, str, str | None, int]]:
    wb = load_workbook(path, read_only=True)
    rows_out: list[tuple[int, str, int, str, str | None, int]] = []
    year: int | None = None
    contest: tuple[str, int] | None = None
    parties: list[str | None] = []
    candidates: list[str] = []
    totals: list[int] = []

    def flush() -> None:
        nonlocal contest, candidates, totals, parties
        if contest and candidates:
            if year is None:
                raise RuntimeError(f"{path.name}: contest found before year header")
            chamber, district = contest
            for i, candidate in enumerate(candidates):
                if not candidate or candidate.upper() == "SCATTERING":
                    continue
                rows_out.append(
                    (year, chamber, district,
                     " ".join(str(candidate).split()),
                     parties[i] if i < len(parties) else None,
                     totals[i] if i < len(totals) else 0)
                )
        contest, candidates, totals, parties = None, [], [], []

    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = list(row)
            first = str(cells[0]).strip() if cells and cells[0] is not None else ""
            if year is None:
                m = YEAR_RE.match(first)
                if m:
                    year = int(m.group(1))
            m = CONTEST_RE.match(first)
            if m:
                flush()
                chamber = "upper" if m.group(1).upper().startswith("STATE SEN") else "lower"
                contest = (chamber, int(m.group(2)))
                continue
            if contest is None:
                continue
            texts = ["" if c is None else str(c).strip() for c in cells]
            if "Total Votes Cast" in texts:
                start = texts.index("Total Votes Cast")
                parties = [t or None for t in texts[start + 1:]]
                candidates, totals = [], []
                continue
            if parties and not candidates and any(texts[len(texts) - len(parties):]):
                offset = len(texts) - len(parties)
                candidates = texts[offset:]
                totals = [0] * len(candidates)
                continue
            if candidates:
                offset = len(texts) - len(parties)
                numeric = cells[offset:]
                if any(isinstance(v, (int, float)) for v in numeric):
                    for i, v in enumerate(numeric):
                        if isinstance(v, (int, float)) and i < len(totals):
                            totals[i] += int(v)
                elif first and CONTEST_RE.match(first) is None and all(
                    not t for t in texts[2:]
                ):
                    continue
    flush()
    wb.close()
    return rows_out


def run(xlsx_dir: Path, db_path: Path) -> int:
    all_rows: list[tuple] = []
    for path in sorted(xlsx_dir.glob("*.xlsx")):
        rows = parse_workbook(path)
        print(f"{path.name}: {len(rows)} candidate rows")
        all_rows.extend(rows)
    if not all_rows:
        raise RuntimeError(f"no legislative contests parsed from {xlsx_dir}")

    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS election_history (
                 year INTEGER NOT NULL,
                 chamber TEXT NOT NULL CHECK (chamber IN ('lower', 'upper')),
                 district INTEGER NOT NULL, candidate TEXT NOT NULL,
                 party TEXT, votes INTEGER NOT NULL)"""
        )
        conn.execute("DELETE FROM election_history")
        conn.executemany(
            "INSERT INTO election_history (year, chamber, district, candidate,"
            " party, votes) VALUES (?, ?, ?, ?, ?, ?)",
            all_rows,
        )
    seats = conn.execute(
        "SELECT COUNT(DISTINCT chamber || district || year) FROM election_history"
    ).fetchone()[0]
    conn.close()
    print(f"election_history: {len(all_rows)} rows across {seats} contests")
    # sanity: an Assembly general election should cover ~99 districts
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.xlsx_dir, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
