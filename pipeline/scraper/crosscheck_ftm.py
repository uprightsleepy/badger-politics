"""Cross-check per-candidate totals against FollowTheMoney (nimsp.org).

Usage: python -m scraper.crosscheck_ftm --cycle 2024 [--db ../data/wi.sqlite]

FTM data is CC BY-NC-SA, research use, 1,000 records/year quota. Raw
responses are cached under _data/ftm/ so re-runs are free, and nothing
here is read by the importer or the site build: the comparison report
is the only output. Expect close-not-exact: FTM cycles, refund and
transfer handling differ from our receipt sums.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path

import requests

from scraper.http import session

BASE = "https://api.followthemoney.org/"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "ftm"
OFFICES = ("R01", "S00")  # Assembly, Senate

_quota_fetched = 0


def api_key() -> str:
    key = os.environ.get("FTM_API_KEY")
    if not key:
        env = Path(__file__).resolve().parents[1] / ".env"
        if env.exists():
            m = re.search(r"^FTM_API_KEY=(.+)$", env.read_text(encoding="utf-8"), re.M)
            key = m.group(1).strip() if m else None
    if not key:
        sys.exit("FTM_API_KEY not set (env or pipeline/.env)")
    return key


def ftm_get(http: requests.Session, query: str, cache_name: str) -> dict:
    """Cache-first FTM request; only cache misses spend quota."""
    global _quota_fetched
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cached = DATA_DIR / cache_name
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    d = http.get(f"{BASE}?{query}&APIKey={api_key()}&mode=json", timeout=60).json()
    if "records" not in d:
        raise RuntimeError(f"FTM drift: unexpected response {str(d)[:200]}")
    cached.write_text(json.dumps(d), encoding="utf-8")
    _quota_fetched += len(d["records"])
    time.sleep(1)
    return d


def report_quota() -> None:
    if _quota_fetched:
        print(f"quota: fetched {_quota_fetched} new records from FTM this run")


def ftm_total(rec: dict) -> float:
    return float(rec.get("Total_$", {}).get("Total_$", 0) or 0)


def norm(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(folded.lower().replace(".", " ").replace(",", " ").split())


def ftm_key(raw: str) -> str:
    """FTM 'LAST, FIRST M' -> 'first last'."""
    last, _, rest = raw.partition(",")
    tokens = norm(f"{rest} {last}").split()
    return f"{tokens[0]} {tokens[-1]}" if tokens else ""


def fetch_cycle(cycle: int, offices: tuple[str, ...] = OFFICES) -> list[dict]:
    """Candidate totals per chamber, cache-first to respect quota."""
    http = session()
    records = []
    for office in offices:
        page = 0
        while True:
            d = ftm_get(
                http,
                f"dt=1&y={cycle}&s=WI&c-r-oc={office}&gro=c-t-id&p={page}",
                f"ftm-{cycle}-{office}-p{page}.json",
            )
            records.extend(d["records"])
            paging = d["metaInfo"]["paging"]
            if paging["currentPage"] >= paging["maxPage"]:
                break
            page += 1
    return records


def match_people(records: list[dict], db: sqlite3.Connection) -> tuple[list, list]:
    """FTM candidates -> our people, exact-unique only; no guesses. One
    person can have several FTM candidacies (e.g. Assembly + Senate runs
    in the same cycle), so totals aggregate to the person."""
    people = db.execute(
        "SELECT id, name FROM people WHERE current_role IN ('Representative', 'Senator')"
    ).fetchall()
    by_full: dict[str, str | None] = {}
    by_firstlast: dict[str, str | None] = {}
    for pid, name in people:
        n = norm(name)
        by_full[n] = None if n in by_full else pid
        tokens = n.split()
        fl = f"{tokens[0]} {tokens[-1]}"
        by_firstlast[fl] = None if fl in by_firstlast else pid
    totals: dict[str, float] = {}
    unmatched = []
    for rec in records:
        raw = rec.get("Candidate", {}).get("Candidate", "")
        last, _, rest = raw.partition(",")
        n = norm(f"{rest} {last}")
        pid = by_full.get(n) or by_firstlast.get(ftm_key(raw))
        if pid:
            totals[pid] = totals.get(pid, 0.0) + ftm_total(rec)
        else:
            unmatched.append({"ftm_name": raw, "ftm_total": ftm_total(rec)})
    matched = [{"person_id": k, "ftm_total": v} for k, v in totals.items()]
    return matched, unmatched


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle", type=int, default=2024)
    ap.add_argument("--db", default="../data/wi.sqlite")
    args = ap.parse_args()

    db = sqlite3.connect(args.db)
    records = fetch_cycle(args.cycle)
    matched, unmatched = match_people(records, db)
    covered = {r[0] for r in db.execute("SELECT DISTINCT person_id FROM contributions")}

    lines = [
        f"# Cross-check vs FollowTheMoney, {args.cycle} cycle",
        "",
        "Data: National Institute on Money in State Politics "
        "(followthemoney.org), CC BY-NC-SA, research use. Our figure is the "
        f"sum of CFIS receipts dated {args.cycle - 1}-01-01 to {args.cycle}-12-31 "
        "per legislator (all their committees). Differences under ~5% are "
        "expected from methodology (refunds, transfers, cycle edges).",
        "",
        "| Legislator | Ours | FTM | Diff |",
        "|---|--:|--:|--:|",
    ]
    flagged = 0
    rows = []
    for m in matched:
        if m["person_id"] not in covered:
            continue
        ours = db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM contributions"
            " WHERE person_id = ? AND date >= ? AND date <= ?",
            (m["person_id"], f"{args.cycle - 1}-01-01", f"{args.cycle}-12-31"),
        ).fetchone()[0]
        name = db.execute(
            "SELECT name FROM people WHERE id = ?", (m["person_id"],)
        ).fetchone()[0]
        theirs = m["ftm_total"]
        base = max(ours, theirs)
        pct = abs(ours - theirs) / base * 100 if base else 0
        flag = " ⚠" if pct > 5 and abs(ours - theirs) > 5000 else ""
        if flag:
            flagged += 1
        rows.append((pct, f"| {name}{flag} | ${ours:,.0f} | ${theirs:,.0f} | {pct:.1f}% |"))
    lines += [r for _, r in sorted(rows, reverse=True)]
    lines += [
        "",
        f"{len(rows)} compared, {flagged} flagged (>5% and >$5k). "
        f"{len(unmatched)} FTM candidates had no exact-unique name match "
        "(challengers, retirees, or name-format differences); never guessed.",
        "",
        "Reading the flags: FTM higher than us usually means we are missing "
        "one of the member's committees (see the curation worklist). Us "
        "higher than FTM usually reflects their cycle windows and transfer "
        "handling. Both deserve a look; neither is proof by itself.",
    ]
    out = Path(__file__).resolve().parents[2] / "docs" / f"crosscheck-ftm-{args.cycle}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(rows)} compared, {flagged} flagged -> {out}")
    report_quota()
    return 0


if __name__ == "__main__":
    sys.exit(main())
