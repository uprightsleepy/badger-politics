"""Overlay WEC candidate data onto the elections table.

Usage: python -m importer.import_wec <candidates.csv> <sqlite_path> --cycle 2026

Reads the normalized CSV produced by wec_pdf (or any future WEC format
converted to the same contract) and fills on_ballot + opponents_json for
seats on the given cycle's ballot. Rows become source='wec'.

on_ballot for the sitting incumbent means: they have an Approve row and did
not file noncandidacy. Opponents are every other Approve/Challenged
candidate for the seat (Challenged kept, labeled — challenges may still be
resolved in their favor).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

EXPECTED_COLUMNS = [
    "office",
    "incumbent",
    "incumbent_noncandidacy",
    "candidate",
    "party",
    "ballot_status",
]
OFFICE_RE = re.compile(
    r"^(STATE SENATOR|REPRESENTATIVE TO THE ASSEMBLY) DISTRICT (\d+)$"
)


SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _words(name: str) -> list[str]:
    """Lowercase name words: accents folded, suffixes dropped, hyphens removed
    within words ('Rivera-Wagner' -> 'riverawagner')."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = [
        re.sub(r"[^a-z]", "", w.lower())
        for w in ascii_name.replace("-", "").split()
    ]
    words = [w for w in words if len(w) > 1]
    while words and words[-1] in SUFFIXES:
        words.pop()
    return words


def family_key(name: str) -> str:
    words = _words(name)
    return words[-1] if words else ""


def _families(name: str) -> set[str]:
    """Surname variants: the last word, plus the joined last two for spaced
    double surnames ('Rivera Wagner' matches 'Rivera-Wagner')."""
    words = _words(name)
    if not words:
        return set()
    families = {words[-1]}
    if len(words) >= 3:
        families.add("".join(words[-2:]))
    return families


def _first(name: str) -> str:
    words = _words(name)
    return words[0] if words else ""


def same_person(a: str, b: str) -> bool:
    """Same surname (variant-tolerant) and compatible first names: equal, or
    one a prefix of the other ('Rob'/'Robert' — but never 'Jane'/'John')."""
    if not _families(a) & _families(b):
        return False
    fa, fb = _first(a), _first(b)
    return bool(fa and fb) and (fa.startswith(fb) or fb.startswith(fa))


def match_candidate(person_name: str, rows: list[dict]) -> list[dict]:
    """Rows for the person. Exactly one strict match wins; several strict
    matches (a Sr./Jr. pair) is ambiguity — no guess. With no strict match,
    a family-only match is accepted ONLY when unique within the seat, so
    nicknames ('Gus'/'Nate') resolve but same-surname pairs never do."""
    strict = [r for r in rows if same_person(r["candidate"], person_name)]
    if len(strict) == 1:
        return strict
    if len(strict) > 1:
        return []
    families = _families(person_name)
    loose = [r for r in rows if family_key(r["candidate"]) in families]
    return loose if len(loose) == 1 else []


def load_candidates(csv_path: Path) -> dict[tuple[str, int], list[dict]]:
    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise RuntimeError(
                f"WEC drift: CSV columns {reader.fieldnames} != {EXPECTED_COLUMNS}"
            )
        rows = list(reader)
    seats: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        m = OFFICE_RE.match(row["office"])
        if not m:
            continue
        chamber = "upper" if m.group(1) == "STATE SENATOR" else "lower"
        seats.setdefault((chamber, int(m.group(2))), []).append(row)
    return seats


def overlay(csv_path: Path, db_path: Path, cycle: int) -> int:
    seats = load_candidates(csv_path)
    if not seats:
        raise RuntimeError("WEC drift: no legislative seats in CSV")

    conn = sqlite3.connect(db_path)
    warnings = 0
    updated = 0
    with conn:
        on_cycle = conn.execute(
            "SELECT e.person_id, e.district, p.chamber, p.name FROM elections e"
            " JOIN people p ON p.id = e.person_id WHERE e.cycle_year = ?",
            (cycle,),
        ).fetchall()
        for person_id, district, chamber, person_name in on_cycle:
            rows = seats.get((chamber, district))
            if rows is None:
                print(
                    f"WARNING: no WEC data for {chamber} district {district}"
                    f" ({person_name})",
                    file=sys.stderr,
                )
                warnings += 1
                continue
            wec_incumbent = rows[0]["incumbent"]
            noncandidacy = rows[0]["incumbent_noncandidacy"] == "1"
            if wec_incumbent and not (
                same_person(wec_incumbent, person_name)
                or family_key(wec_incumbent) == family_key(person_name)
            ):
                print(
                    f"WARNING: WEC incumbent {wec_incumbent!r} != roster"
                    f" {person_name!r} ({chamber} {district})",
                    file=sys.stderr,
                )
                warnings += 1
            viable = [r for r in rows if r["ballot_status"] in ("Approve", "Challenged")]
            incumbent_rows = match_candidate(person_name, viable)
            on_ballot = int(bool(incumbent_rows) and not noncandidacy)
            opponents = [
                {
                    "name": r["candidate"],
                    "party": r["party"],
                    "ballot_status": r["ballot_status"],
                }
                for r in viable
                if r not in incumbent_rows
            ]
            conn.execute(
                "UPDATE elections SET on_ballot = ?, opponents_json = ?, source = 'wec'"
                " WHERE person_id = ? AND cycle_year = ?",
                (on_ballot, json.dumps(opponents), person_id, cycle),
            )
            updated += 1
    conn.close()
    print(f"wec overlay: {updated} seats updated, {warnings} warnings")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--cycle", type=int, required=True)
    ns = parser.parse_args(argv)
    return overlay(ns.csv_path, ns.db_path, ns.cycle)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
