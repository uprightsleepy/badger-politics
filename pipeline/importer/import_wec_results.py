"""Import WEC ward-by-ward canvass spreadsheets: legislative and statewide
general-election results, statewide judicial races and statewide referenda.

Usage: python -m importer.import_wec_results <xlsx_dir> <sqlite_path>

Each contest appears as a title row, a party header containing 'Total Votes
Cast', a candidate row, then ward rows whose votes are summed per candidate.
Files are named <ger|spring|primary><year>[-part].xlsx (scraper.fetch_wec_results);
the workbook's own election line must agree, so a pinned URL that came back
as a different election fails the import.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

from scraper.fetch_wec_results import FILES

# 2016-2024 canvasses say "STATE SENATOR DISTRICT 5"; the G.A.B.-era 2014
# report says "STATE SENATE - DISTRICT 5" and "ASSEMBLY - DISTRICT 11"
CONTEST_RE = re.compile(
    r"^(STATE SENATOR|STATE SENATE|REPRESENTATIVE TO THE ASSEMBLY|ASSEMBLY)"
    r"\s*[-\u2013]?\s*DISTRICT\s+(\d+)", re.I
)
STATEWIDE_RE = re.compile(
    r"^(GOVERNOR ?/ ?LIEUTENANT GOVERNOR|ATTORNEY GENERAL"
    r"|SECRETARY OF STATE|STATE TREASURER)$",
    re.I,
)
JUDICIAL_RE = re.compile(r"^(JUSTICE OF THE SUPREME COURT|COURT OF APPEALS JUDGE DISTRICT (\d+))$",
                         re.I)
# "STATE REFERENDUM" (2014), "State of Wisconsin Referendum" (2025), or with
# the question's subject: "State of Wisconsin Election Officials Referendum - Question 2"
REFERENDUM_RE = re.compile(r"^(STATE REFERENDUM|STATE OF WISCONSIN\b.*\bREFERENDUM\b.*)$", re.I)
TITLES = (("leg", CONTEST_RE), ("statewide", STATEWIDE_RE), ("judicial", JUDICIAL_RE),
          ("referendum", REFERENDUM_RE))
ELECTION_RE = re.compile(r"^(\d{4}) (General Election|Spring Election|Partisan Primary)", re.I)
KIND = {"general election": "general", "spring election": "spring",
        "partisan primary": "primary"}
FILE_RE = re.compile(r"^(ger|spring|primary)(\d{4})\b")
PREFIX = {"ger": "general", "spring": "spring", "primary": "primary"}


def _ticket(candidate: str) -> str:
    """'Tony Evers \\n Sara Rodriguez' -> 'Tony Evers / Sara Rodriguez'."""
    parts = [" ".join(p.split()) for p in str(candidate).split("\n")]
    return " / ".join(p for p in parts if p)


SUBTOTAL_RE = re.compile(r"(sub)?totals?:\s*$", re.I)


def _walk_contests(path: Path):
    """Yield (kind, year, election, match, parties, candidates, sums,
    total_cast, counties) per contest, in one pass over the workbook — kind
    is which TITLES pattern opened the contest; election is general, spring
    or primary, from the report's own election line.

    Columns anchor absolutely on the 'Total Votes Cast' header (canvass
    rows are ragged, so length arithmetic misaligns). Subtotal rows are
    excluded from the ward sums — the report interleaves them, which
    silently multiplies every total — but the 'County Totals:' rows are
    themselves certified county aggregates, so they're captured as
    (county, per-candidate votes) instead of discarded."""
    wb = load_workbook(path, read_only=True)
    year: int | None = None
    election: str | None = None
    kind: str | None = None
    match: re.Match | None = None
    base: int | None = None
    parties: list[str | None] = []
    candidates: list[str] = []
    totals: list[int] = []
    total_cast = 0
    county: str | None = None
    counties: list[tuple[str, list[int]]] = []

    def snapshot():
        return (kind, year, election, match, list(parties), list(candidates),
                list(totals), total_cast, list(counties))

    def reset(k, m):
        nonlocal kind, match, base, parties, candidates
        nonlocal totals, total_cast, county, counties
        kind, match, base, parties, candidates = k, m, None, [], []
        totals, total_cast, county, counties = [], 0, None, []

    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            cells = list(row)
            texts = ["" if c is None else str(c).strip() for c in cells]
            first = texts[0] if texts else ""
            if year is None:
                m = ELECTION_RE.match(first)
                if m:
                    year, election = int(m.group(1)), KIND[m.group(2).lower()]
            new_kind, m = next(((k, m) for k, pattern in TITLES
                                if (m := pattern.match(first))), (None, None))
            if m:
                if match and candidates:
                    yield snapshot()
                reset(new_kind, m)
                continue
            if match is None:
                continue
            if "Total Votes Cast" in texts:
                base = texts.index("Total Votes Cast") + 1
                parties, candidates, totals = [t or None for t in texts[base:]], [], []
                continue
            if base is not None and not candidates and any(texts[base:]):
                candidates = texts[base:]
                while candidates and not candidates[-1]:
                    candidates.pop()
                totals = [0] * len(candidates)
                parties = (parties + [None] * len(candidates))[: len(candidates)]
                continue
            if candidates:
                # the by-CD layout adds a CD rollup row: a CD label with an
                # empty municipality cell (real ward rows carry the CD label
                # in col 0 WITH a municipality, and must still be summed)
                if (
                    any(t.startswith("U.S. Congressional District") for t in texts[:3])
                    and (len(texts) < 3 or not texts[2])
                ):
                    continue
                if any(SUBTOTAL_RE.search(t) for t in texts[:3] if t):
                    # the county aggregate row: capture once, never sum
                    if texts[1] == "County Totals:" and county:
                        counties.append((
                            county,
                            [int(cells[base + i]) if base + i < len(cells)
                             and isinstance(cells[base + i], (int, float)) else 0
                             for i in range(len(candidates))],
                        ))
                    # the contest's own certified totals END it: verify our
                    # ward sums against them to the vote, then deactivate so
                    # trailing non-legislative contests can't leak in (the
                    # old parser let the file's last contest absorb them)
                    if "Office Totals:" in texts[:2]:
                        official = [
                            int(cells[base + i]) if base + i < len(cells)
                            and isinstance(cells[base + i], (int, float)) else 0
                            for i in range(len(candidates))
                        ]
                        cast = cells[base - 1] if base - 1 < len(cells) else None
                        if official != totals or (
                            isinstance(cast, (int, float)) and int(cast) != total_cast
                        ):
                            raise RuntimeError(
                                f"{path.name} {match.group(0)!r}: ward sums {totals}"
                                f"/{total_cast} != Office Totals {official}/{cast}"
                            )
                        yield snapshot()
                        reset(None, None)
                    continue
                if first:
                    # canonical county casing ('Fond du Lac', not 'Fond Du Lac')
                    county = " ".join(first.split()).title().replace(" Du ", " du ")
                cast = cells[base - 1] if base - 1 < len(cells) else None
                if isinstance(cast, (int, float)):
                    total_cast += int(cast)
                for i in range(len(candidates)):
                    v = cells[base + i] if base + i < len(cells) else None
                    if isinstance(v, (int, float)):
                        totals[i] += int(v)
    if match and candidates:
        yield snapshot()
    wb.close()


def parse_all(path: Path):
    """One walk per workbook: (legislative rows, statewide rows, county rows,
    judicial rows, referendum rows). Legislative and constitutional-office
    rows come only from general elections (a spring canvass can carry a
    special legislative election, which is not a seat's regular result)."""
    leg_rows: list[tuple[int, str, int, str, str | None, int, int]] = []
    sw_rows: list[tuple[int, str, str, str | None, int, int]] = []
    county_rows: list[tuple[int, str, str, str, str | None, int]] = []
    judicial_rows: list[tuple] = []
    referendum_rows: list[tuple] = []
    named = FILE_RE.match(path.name)
    for kind, year, election, m, parties, candidates, totals, cast, counties in (
        _walk_contests(path)
    ):
        if year is None:
            raise RuntimeError(f"{path.name}: contest found before year header")
        if named and (int(named.group(2)), PREFIX[named.group(1)]) != (year, election):
            raise RuntimeError(f"{path.name}: workbook is the {year} {election} canvass")
        if kind == "referendum":
            question = re.search(r"QUESTION (\d+)$", m.group(1), re.I)
            votes = dict(zip((c.upper() for c in candidates), totals, strict=True))
            if set(votes) != {"YES", "NO"}:
                raise RuntimeError(f"{path.name} {m.group(1)!r}: columns {candidates}")
            referendum_rows.append((
                year, election, int(question.group(1)) if question else 1,
                " ".join(m.group(1).split()), votes["YES"], votes["NO"], cast,
                len(counties), path.name,
            ))
            continue
        if kind in ("leg", "statewide") and election != "general":
            continue
        for i, candidate in enumerate(candidates):
            if not candidate or candidate.upper() == "SCATTERING":
                continue
            if kind == "leg":
                chamber = "upper" if m.group(1).upper().startswith("STATE SEN") else "lower"
                leg_rows.append(
                    (year, chamber, int(m.group(2)),
                     " ".join(str(candidate).split()), parties[i], totals[i], cast)
                )
            elif kind == "judicial":
                office = ("JUSTICE OF THE SUPREME COURT" if m.group(2) is None
                          else "COURT OF APPEALS JUDGE")
                judicial_rows.append((
                    year, election, office, m.group(2) and int(m.group(2)),
                    " ".join(str(candidate).split()), totals[i], cast, len(counties),
                    path.name,
                ))
            else:
                office = re.sub(r"\s*/\s*", " / ", m.group(1).upper())
                sw_rows.append(
                    (year, office, _ticket(candidate), parties[i], totals[i], cast)
                )
                for county, values in counties:
                    county_rows.append(
                        (year, office, county, _ticket(candidate), parties[i], values[i])
                    )
    return leg_rows, sw_rows, county_rows, judicial_rows, referendum_rows


def parse_statewide(path: Path):
    """Returns (candidate rows incl. total_cast, county rows)."""
    _, sw_rows, county_rows, _, _ = parse_all(path)
    return sw_rows, county_rows


def run(xlsx_dir: Path, db_path: Path) -> int:
    all_rows: list[tuple] = []
    statewide_rows: list[tuple] = []
    county_rows: list[tuple] = []
    judicial_rows: list[tuple] = []
    referendum_rows: list[tuple] = []
    for path in sorted(xlsx_dir.glob("*.xlsx")):
        rows, sw, counties, judicial, referenda = parse_all(path)
        print(f"{path.name}: {len(rows)} candidate rows"
              + (f", {len(sw)} statewide" if sw else "")
              + (f", {len(judicial)} judicial" if judicial else "")
              + (f", {len(referenda)} referendum questions" if referenda else ""))
        all_rows.extend(rows)
        statewide_rows.extend(sw)
        county_rows.extend(counties)
        judicial_rows.extend(judicial)
        referendum_rows.extend(referenda)
    if not all_rows:
        raise RuntimeError(f"no legislative contests parsed from {xlsx_dir}")
    assembly_by_year: dict[int, set[int]] = defaultdict(set)
    legislative_contests: dict[tuple, list[tuple]] = defaultdict(list)
    for row in all_rows:
        legislative_contests[row[:3]].append(row)
        if row[1] == "lower":
            assembly_by_year[row[0]].add(row[2])
    # a general election covers all 99 Assembly districts
    for year in {r[0] for r in all_rows}:
        assembly = assembly_by_year[year]
        if len(assembly) < 95:
            raise RuntimeError(
                f"{year}: only {len(assembly)} Assembly districts parsed — format drift?"
            )
    # the official Total Votes Cast can never be below the candidate sum
    for key in {(r[0], r[1], r[2]) for r in all_rows}:
        contest = legislative_contests[key]
        if contest[0][6] < sum(r[5] for r in contest):
            raise RuntimeError(f"{key}: total cast below candidate sum — bad parse")
    statewide_contests: dict[tuple, list[tuple]] = defaultdict(list)
    county_contests: dict[tuple, list[tuple]] = defaultdict(list)
    for row in statewide_rows:
        statewide_contests[row[:2]].append(row)
    for row in county_rows:
        county_contests[row[:2]].append(row)
    # Require at least two candidates and plausible statewide totals.
    # Each candidate's total must equal the sum across all 72 counties.
    for year, office in {(r[0], r[1]) for r in statewide_rows}:
        contest = statewide_contests[(year, office)]
        total = sum(r[4] for r in contest)
        if len(contest) < 2 or total < 500_000 or contest[0][5] < total:
            raise RuntimeError(
                f"{year} {office}: {len(contest)} candidates, {total} votes"
                " — format drift?"
            )
        county_contest = county_contests[(year, office)]
        counties = {r[2] for r in county_contest}
        if len(counties) != 72:
            raise RuntimeError(
                f"{year} {office}: {len(counties)} counties parsed, expected 72"
            )
        candidate_totals: dict[str, int] = defaultdict(int)
        for county in county_contest:
            candidate_totals[county[3]] += county[5]
        for r in contest:
            county_sum = candidate_totals[r[2]]
            if county_sum != r[4]:
                raise RuntimeError(
                    f"{year} {office} {r[2]}: county sum {county_sum}"
                    f" != statewide {r[4]}"
                )

    judicial_out, referendum_out = _check_spring(judicial_rows, referendum_rows)

    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("DELETE FROM election_history")
        conn.executemany(
            "INSERT INTO election_history (year, chamber, district, candidate,"
            " party, votes, total_cast) VALUES (?, ?, ?, ?, ?, ?, ?)",
            all_rows,
        )
        conn.execute("DELETE FROM statewide_history")
        conn.executemany(
            "INSERT INTO statewide_history (year, office, candidate, party, votes,"
            " total_cast) VALUES (?, ?, ?, ?, ?, ?)",
            statewide_rows,
        )
        conn.execute("DELETE FROM statewide_county_results")
        conn.executemany(
            "INSERT INTO statewide_county_results (year, office, county, candidate,"
            " party, votes) VALUES (?, ?, ?, ?, ?, ?)",
            county_rows,
        )
        conn.execute("DELETE FROM judicial_history")
        conn.executemany(
            "INSERT INTO judicial_history (year, election, office, district, candidate,"
            " votes, total_cast, source_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            judicial_out,
        )
        conn.execute("DELETE FROM referendum_history")
        conn.executemany(
            "INSERT INTO referendum_history (year, election, question, title, yes, no,"
            " total_cast, source_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            referendum_out,
        )
    seats = conn.execute(
        "SELECT COUNT(DISTINCT chamber || district || year) FROM election_history"
    ).fetchone()[0]
    conn.close()
    print(f"election_history: {len(all_rows)} rows across {seats} contests")
    contests = len(statewide_contests)
    print(f"statewide_history: {len(statewide_rows)} rows across {contests} contests;"
          f" {len(county_rows)} county result rows")
    print(f"judicial_history: {len(judicial_out)} rows across"
          f" {len({r[:4] for r in judicial_out})} contests;"
          f" referendum_history: {len(referendum_out)} questions")
    return 0


def _source(name: str) -> str:
    if name not in FILES:
        raise RuntimeError(f"{name}: not a pinned canvass file (scraper.fetch_wec_results)")
    return FILES[name]


def _check_spring(judicial_rows: list[tuple], referendum_rows: list[tuple]):
    """Judicial and referendum rows checked against the certified totals,
    returned in table shape: a statewide question or Supreme Court race
    covers all 72 counties, a contest comes from exactly one pinned file,
    and YES + NO is the question's Total Votes Cast."""
    files: dict[tuple, set[str]] = defaultdict(set)
    contests: dict[tuple, list[tuple]] = defaultdict(list)
    for row in judicial_rows:
        key = row[:4]
        contests[key].append(row)
        files[key].add(row[8])
    for key, rows in contests.items():
        year, election, office, district = key
        label = f"{year} {election} {office}" + (f" {district}" if district else "")
        if len(files[key]) > 1:
            raise RuntimeError(f"{label}: in more than one file {sorted(files[key])}")
        if rows[0][6] < sum(r[5] for r in rows):
            raise RuntimeError(f"{label}: total cast below candidate sum — bad parse")
        if office == "JUSTICE OF THE SUPREME COURT" and rows[0][7] != 72:
            raise RuntimeError(f"{label}: {rows[0][7]} counties parsed, expected 72")
    questions: set[tuple] = set()
    for row in referendum_rows:
        year, election, question, title, yes, no, cast, counties, _ = row
        label = f"{year} {election} question {question}"
        if row[:3] in questions:
            raise RuntimeError(f"{label}: parsed twice")
        questions.add(row[:3])
        if yes + no != cast or counties != 72:
            raise RuntimeError(
                f"{label}: yes {yes} + no {no} vs cast {cast}, {counties} counties"
            )
    return (
        [(*r[:7], _source(r[8])) for r in judicial_rows],
        [(*r[:7], _source(r[8])) for r in referendum_rows],
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("xlsx_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.xlsx_dir, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
