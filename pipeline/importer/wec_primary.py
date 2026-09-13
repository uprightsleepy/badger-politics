"""Certified partisan primary results -> each party's nominee per office.

The Commission's "Ward by Ward Report ... Partisan Primary ... All State
Contests" workbook: a Document map sheet listing every contest, then one
sheet per contest ("OFFICE - Party"). The primary decides who each party
sends to November, so these certified totals, not the pre-primary
ballot-access report, name the general-election candidates.

Every vote is verified before a nominee is named: ward rows must sum to the
certified county and office totals, to the vote. Nominees follow Wis. Stat.
8.16: the most votes wins where a name was printed on the party's ballot
(sub. 1); where none was, a write-in qualifies only with at least the
office's minimum nomination signatures under 8.15(6), or more (sub. 2).
Whatever the certified totals cannot settle is "unresolved", never guessed.

Usage: python -m importer.wec_primary <primary.xlsx> --cycle 2026
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openpyxl import load_workbook

WRITE_IN = "SCATTERING"
# 8.15(6) minimums; the 8.16(2) threshold is never below these
MIN_SIGNATURES = {
    "GOVERNOR": 2000, "LIEUTENANT GOVERNOR": 2000, "ATTORNEY GENERAL": 2000,
    "SECRETARY OF STATE": 2000, "STATE TREASURER": 2000,
    "REPRESENTATIVE IN CONGRESS": 1000, "STATE SENATOR": 400,
    "REPRESENTATIVE TO THE ASSEMBLY": 200,
}


def _text(cell) -> str:
    return "" if cell is None else str(cell).strip()


def _votes(cell, where: str) -> int:
    if type(cell) is not int or cell < 0:
        raise RuntimeError(f"WEC primary drift: non-count {cell!r} at {where}")
    return cell


def _contest(ws, title: str, cycle: int) -> dict:
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    texts = [[_text(c) for c in r] for r in rows]
    if not any(f"{cycle} Partisan Primary" in t for r in texts for t in r):
        raise RuntimeError(f"WEC primary drift: {ws.title} is not the {cycle} primary")
    if not any(title in r for r in texts):
        raise RuntimeError(f"WEC primary drift: {ws.title} does not hold {title!r}")
    header = next(i for i, r in enumerate(texts) if "Total Votes Cast" in r)
    cast_col = texts[header].index("Total Votes Cast")
    # names sit at fixed columns with gaps between them: key votes by column
    names = {j: t for j, t in enumerate(texts[header + 1]) if j > cast_col and t}
    if not names or list(names.values()).count(WRITE_IN) > 1:
        raise RuntimeError(f"WEC primary drift: no candidate row in {title!r}")
    wards = dict.fromkeys(names, 0)
    counties = dict.fromkeys(names, 0)
    cast = county_cast = 0
    official = None
    for i, r in enumerate(rows[header + 2:], start=header + 2):
        label = " ".join(texts[i][:2])
        if not any(texts[i]):
            continue
        where = f"{title!r} row {i + 1}"
        if "Office Totals:" in label:
            official = ({j: _votes(r[j], where) for j in names}, _votes(r[cast_col], where))
            break
        if "County Totals:" in label:
            for j in names:
                counties[j] += _votes(r[j], where)
            county_cast += _votes(r[cast_col], where)
            continue
        for j in names:
            wards[j] += _votes(r[j], where)
        cast += _votes(r[cast_col], where)
    if official is None:
        raise RuntimeError(f"WEC primary drift: no Office Totals in {title!r}")
    totals, official_cast = official
    if wards != totals or counties != totals or cast != official_cast != county_cast:
        raise RuntimeError(
            f"WEC primary: {title!r} ward sums {wards}/{cast} and county totals"
            f" {counties}/{county_cast} != certified {totals}/{official_cast}"
        )
    office, party = title.rsplit(" - ", 1)
    return {
        "office": office,
        "party": party,
        "candidates": [(names[j], totals[j]) for j in names if names[j] != WRITE_IN],
        "write_in": sum(totals[j] for j in names if names[j] == WRITE_IN),
        "cast": official_cast,
    }


def parse(path: Path, cycle: int) -> list[dict]:
    wb = load_workbook(path, read_only=True)
    if wb.sheetnames[0] != "Document map":
        raise RuntimeError("WEC primary drift: no Document map sheet")
    titles = [t for r in wb.worksheets[0].iter_rows(values_only=True)
              for t in (next((_text(c) for c in r if _text(c)), ""),) if " - " in t]
    sheets = wb.worksheets[1:]
    # the report ends with a header-only page; anything carrying data is drift
    while sheets and not any(
        " - " in _text(c) or "Total Votes Cast" in _text(c) or type(c) is int
        for r in sheets[-1].iter_rows(values_only=True) for c in r
    ):
        sheets.pop()
    if len(titles) != len(sheets) or len(set(titles)) != len(titles):
        raise RuntimeError(
            f"WEC primary drift: {len(titles)} mapped contests for {len(sheets)} sheets")
    contests = [_contest(ws, title, cycle) for ws, title in zip(sheets, titles, strict=True)]
    wb.close()
    return contests


def is_write_in(name: str) -> bool:
    return name.lower().endswith("(write-in)")


def nominee(contest: dict) -> tuple[str, str | None]:
    """("nominee", name), ("none", None) or ("unresolved", reason)."""
    ranked = sorted(contest["candidates"], key=lambda c: -c[1])
    printed = [c for c in ranked if not is_write_in(c[0])]
    if printed:
        leader = ranked[0]
        if len(ranked) > 1 and ranked[1][1] == leader[1]:
            return "unresolved", "tied for the most votes"
        if contest["write_in"] >= leader[1]:
            return "unresolved", "unnamed write-in votes could exceed the leader"
        return "nominee", leader[0]
    top = max([contest["write_in"], *(v for _, v in ranked)])
    minimum = next(v for k, v in MIN_SIGNATURES.items() if contest["office"].startswith(k))
    if top < minimum:
        return "none", None
    return "unresolved", "a write-in candidate may have qualified under s. 8.16(2)"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path)
    ap.add_argument("--cycle", type=int, required=True)
    ns = ap.parse_args(argv)
    contests = parse(ns.path, ns.cycle)
    kinds = [nominee(c)[0] for c in contests]
    print(f"{len(contests)} certified primary contests verified: {kinds.count('nominee')}"
          f" nominees, {kinds.count('unresolved')} unresolved")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
