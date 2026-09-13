"""Overlay the Commission's candidate records onto elections: on_ballot and
opponents per seat, plus the statewide races.

Before the primary is certified the candidates are every approved filing in
the ballot-access report. From September 1 of the cycle year the certified
primary is required, and the candidates are each party's nominee under
Wis. Stat. 8.16 plus the independents the report approved: a primary loser
is never shown as a November candidate.

Usage: python -m importer.import_wec <candidates.csv> <sqlite_path> --cycle 2026
       [--primary primary-2026.xlsx]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

from importer.roster import load_curation
from importer.wec_primary import nominee
from importer.wec_primary import parse as parse_primary

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
# statewide constitutional offices tracked; federal contests are known and
# skipped; anything else in the report is drift and fails loudly
STATEWIDE_OFFICES = {
    "GOVERNOR",
    "LIEUTENANT GOVERNOR",
    "ATTORNEY GENERAL",
    "SECRETARY OF STATE",
    "STATE TREASURER",
}
FEDERAL_RE = re.compile(r"^(REPRESENTATIVE IN CONGRESS|UNITED STATES SENATOR)")
RULINGS_PATH = Path(__file__).with_name("wec_rulings.json")


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


def _read_rows(csv_path: Path) -> list[dict]:
    """One parse of the candidates CSV, with the column-drift check."""
    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise RuntimeError(
                f"WEC drift: CSV columns {reader.fieldnames} != {EXPECTED_COLUMNS}"
            )
        return list(reader)


def _seats(rows: list[dict]) -> dict[tuple[str, int], list[dict]]:
    seats: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        m = OFFICE_RE.match(row["office"])
        if not m:
            if row["office"] in STATEWIDE_OFFICES or FEDERAL_RE.match(row["office"]):
                continue
            raise RuntimeError(f"WEC drift: unrecognized office {row['office']!r}")
        chamber = "upper" if m.group(1) == "STATE SENATOR" else "lower"
        seats.setdefault((chamber, int(m.group(2))), []).append(row)
    return seats


def load_candidates(csv_path: Path) -> dict[tuple[str, int], list[dict]]:
    return _seats(_read_rows(csv_path))


def _in_scope(office: str) -> bool:
    return bool(OFFICE_RE.match(office)) or office in STATEWIDE_OFFICES


def _rulings(cycle: int) -> tuple[dict, dict]:
    cycle_rulings = load_curation(RULINGS_PATH).get(str(cycle), {})
    for entry in cycle_rulings.get("candidates", []) + cycle_rulings.get("contests", []):
        if not str(entry.get("basis", "")).startswith("https://"):
            raise RuntimeError(f"WEC ruling without an official basis: {entry}")
    return ({(r["office"], r["candidate"]): r for r in cycle_rulings.get("candidates", [])},
            {(r["office"], r["party"]): r for r in cycle_rulings.get("contests", [])})


def november(csv_rows: list[dict], contests: list[dict], cycle: int
             ) -> tuple[dict[str, list[dict]], dict[str, list[tuple[str, str]]]]:
    """office -> November candidates, office -> [(party, reason)] still open."""
    by_office: dict[str, dict[str, dict]] = defaultdict(dict)
    for c in contests:
        if _in_scope(c["office"]):
            by_office[c["office"]][c["party"]] = c
    parties = {party for races in by_office.values() for party in races}
    report_offices = {r["office"] for r in csv_rows if _in_scope(r["office"])}
    if report_offices != set(by_office) or any(set(r) != parties for r in by_office.values()):
        raise RuntimeError(
            "WEC primary does not cover the ballot-access offices and parties:"
            f" {sorted(report_offices ^ set(by_office))[:5]}")
    candidate_rulings, contest_rulings = _rulings(cycle)
    ballot: dict[str, list[dict]] = defaultdict(list)
    pending: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for office, races in by_office.items():
        for party, contest in races.items():
            kind, value = nominee(contest)
            ruling = contest_rulings.pop((office, party), None)
            if ruling and kind != "unresolved":
                raise RuntimeError(f"WEC ruling for a settled primary: {office} - {party}")
            if ruling:
                named = [n for n, _ in contest["candidates"]]
                if ruling["nominee"] is not None and ruling["nominee"] not in named:
                    raise RuntimeError(f"WEC ruling names no one in {office} - {party}")
                kind, value = (("nominee", ruling["nominee"]) if ruling["nominee"]
                               else ("none", None))
            if kind == "nominee":
                ballot[office].append({"candidate": value, "party": party})
            elif kind == "unresolved":
                pending[office].append((party, value))
    for row in csv_rows:
        office = row["office"]
        if not _in_scope(office) or row["ballot_status"] == "Deny":
            continue
        entrants = [n for c in by_office[office].values() for n, _ in c["candidates"]]
        if any(same_person(row["candidate"], n) for n in entrants):
            continue
        label = row["party"].strip().rstrip(",")
        if label in parties:
            continue  # a party filing missing from its own primary was not on the ballot
        if any(" " in p and p.split()[0] == label for p in parties):
            raise RuntimeError(f"WEC: truncated party label {label!r} for {row['candidate']}")
        ruling = candidate_rulings.pop((office, row["candidate"]), None)
        if row["ballot_status"] == "Challenged" and ruling is None:
            raise RuntimeError(f"WEC: challenge outcome needs a ruling: {row['candidate']}")
        if ruling and row["ballot_status"] != "Challenged":
            raise RuntimeError(f"WEC ruling for an unchallenged filing: {row['candidate']}")
        if ruling is None or ruling["on_ballot"]:
            ballot[office].append({"candidate": row["candidate"], "party": "Independent"})
    if candidate_rulings or contest_rulings:
        raise RuntimeError(
            f"WEC rulings the data no longer needs: {candidate_rulings or contest_rulings}")
    for office, entries in ballot.items():
        named = [e["party"] for e in entries if e["party"] != "Independent"]
        if len(named) != len(set(named)):
            raise RuntimeError(f"WEC: two candidates of one party for {office}")
    return ballot, pending


def overlay(csv_path: Path, db_path: Path, cycle: int, primary: Path | None = None,
            today: date | None = None) -> int:
    csv_rows = _read_rows(csv_path)
    seats = _seats(csv_rows)
    if not seats:
        raise RuntimeError("WEC drift: no legislative seats in CSV")
    if primary is None and (today or date.today()) >= date(cycle, 9, 1):
        raise RuntimeError(
            f"The {cycle} primary is certified by now: pass --primary, or pre-primary"
            " filings would be shown as November candidates")
    ballot, pending = november(csv_rows, parse_primary(primary, cycle), cycle) \
        if primary else ({}, {})

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
            office = rows[0]["office"]
            viable = ([{**e, "ballot_status": "Approve"} for e in ballot.get(office, [])]
                      if primary else
                      [r for r in rows if r["ballot_status"] in ("Approve", "Challenged")])
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
        statewide = [r for r in csv_rows if r["office"] in STATEWIDE_OFFICES]
        if primary:
            incumbents = {r["office"]: r for r in statewide}
            statewide = [
                {**incumbents[office], **e, "ballot_status": "Approve",
                 "on_ballot": int(bool(incumbents[office]["incumbent"]) and any(
                     same_person(incumbents[office]["incumbent"], x["candidate"])
                     for x in ballot.get(office, [])))}
                for office in sorted(incumbents) for e in ballot.get(office, [])]
        conn.execute("DELETE FROM write_in_pending WHERE cycle_year = ?", (cycle,))
        conn.executemany(
            "INSERT INTO write_in_pending (cycle_year, office, party, reason) VALUES (?, ?, ?, ?)",
            [(cycle, office, party, reason)
             for office, open_ in sorted(pending.items()) for party, reason in open_])
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('wec_ballot_phase', ?)",
                     ("general" if primary else "primary",))
        conn.execute("DELETE FROM statewide_races")
        conn.executemany(
            "INSERT INTO statewide_races (office, incumbent, incumbent_noncandidacy,"
            " incumbent_on_ballot, candidate, party, ballot_status, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'wec')",
            [
                (r["office"], r["incumbent"] or None,
                 int(r["incumbent_noncandidacy"] == "1"), r.get("on_ballot"), r["candidate"],
                 r["party"] or None, r["ballot_status"] or None)
                for r in statewide
            ],
        )
    conn.close()
    races = len({r["office"] for r in statewide})
    print(f"wec overlay ({'November ballot' if primary else 'pre-primary filings'}):"
          f" {updated} seats updated, {warnings} warnings; {len(statewide)} statewide"
          f" candidates across {races} offices; {sum(map(len, pending.values()))} open primaries")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--primary", type=Path, help="certified primary ward-by-ward workbook")
    ns = parser.parse_args(argv)
    return overlay(ns.csv_path, ns.db_path, ns.cycle, ns.primary)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
