"""Annotate the curation worklist with FollowTheMoney committee leads.

Usage: python -m scraper.ftm_leads [--db ../data/wi.sqlite]

For each member needing curation, FTM's own candidate->filer attribution
names the committee their money ran through. That is a lead for human
verification on campaignfinance.wi.gov, never an accepted mapping: FTM
is not the primary source and carries no CFIS entity ids. Responses are
cached under _data/ftm/ (CC BY-NC-SA, research use, quota-limited).
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

import requests

from scraper.crosscheck_ftm import (
    USER_AGENT,
    fetch_cycle,
    ftm_get,
    ftm_total,
    norm,
    report_quota,
)

WORKLIST = Path(__file__).resolve().parents[2] / "docs" / "curation-worklist.md"


def candidate_index(records: list[dict]) -> dict[str, list[tuple[int, int, str]]]:
    """normalized 'first last' -> [(ftm candidate id, cycle, raw name)]."""
    index: dict[str, list] = {}
    for cycle, recs in records:
        for rec in recs:
            cand = rec.get("Candidate", {})
            raw = cand.get("Candidate", "")
            cid = cand.get("id")
            last, _, rest = raw.partition(",")
            tokens = norm(f"{rest} {last}").split()
            if not tokens or cid is None:
                continue
            key = f"{tokens[0]} {tokens[-1]}"
            index.setdefault(key, []).append((int(cid), cycle, raw))
    return index


def filers_for(http: requests.Session, cid: int, cycle: int) -> list[tuple[str, float]]:
    d = ftm_get(
        http,
        f"dt=1&y={cycle}&s=WI&c-t-id={cid}&gro=f-eid",
        f"ftm-filers-{cycle}-{cid}.json",
    )
    return [
        (rec["Filer"]["Filer"], ftm_total(rec))
        for rec in d.get("records", [])
        if rec.get("Filer", {}).get("Filer")
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="../data/wi.sqlite")
    args = ap.parse_args()
    db = sqlite3.connect(args.db)

    text = WORKLIST.read_text(encoding="utf-8")
    person_ids = re.findall(r"^`(ocd-person/[0-9a-f-]+)`$", text, re.M)
    people = {
        pid: (name, chamber)
        for pid, name, chamber in db.execute(
            "SELECT id, name, chamber FROM people WHERE current_role IN"
            " ('Representative', 'Senator')"
        )
        if pid in set(person_ids)
    }
    print(f"{len(people)} worklist members", file=sys.stderr)

    # assembly seats were all on the 2024 ballot; odd senate seats on 2022
    cycles = [(2024, fetch_cycle(2024))]
    if any(ch == "upper" for _, ch in people.values()):
        cycles.append((2022, fetch_cycle(2022, ("S00",))))
    index = candidate_index(cycles)

    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    lines = text.split("\n")
    out, i, annotated = [], 0, 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = re.match(r"^`(ocd-person/[0-9a-f-]+)`$", line)
        i += 1
        if not m or m.group(1) not in people:
            continue
        name, _chamber = people[m.group(1)]
        tokens = norm(name).split()
        cands = index.get(f"{tokens[0]} {tokens[-1]}", [])
        leads = []
        for cid, cycle, _raw in cands:
            for filer, total in filers_for(http, cid, cycle):
                leads.append((filer, total, cycle))
        if not leads:
            out.append("- FTM: no candidacy found in the 2022/2024 cycles "
                       "(special-election member or name-format gap)")
        for filer, total, cycle in leads:
            # FTM names candidate filers after the person, so the committee
            # name rarely comes through; the dollar total is the real lead
            named = f" via \"{filer}\"" if norm(filer) != norm(name) else ""
            out.append(f"- FTM fingerprint: ${total:,.0f} raised in the {cycle} "
                       f"cycle{named}. The committee you confirm on CFIS should "
                       "show money at this scale.")
            annotated += 1
        # corroborate CFIS hits that match a lead by normalized name
        lead_names = {norm(f) for f, _, _ in leads}
        while i < len(lines) and lines[i].startswith("- "):
            hit = lines[i]
            hm = re.match(r"^- \[ \] (\d+) - (.+?)(  <- likely| {2}\(other office\))?$", hit)
            if hm and norm(hm.group(2)) in lead_names:
                hit = f"- [ ] {hm.group(1)} - {hm.group(2)}  <- FTM-corroborated"
            out.append(hit)
            i += 1
    WORKLIST.write_text("\n".join(out), encoding="utf-8")
    print(f"annotated {annotated} leads across {len(people)} members -> {WORKLIST}")
    report_quota()
    return 0


if __name__ == "__main__":
    sys.exit(main())
