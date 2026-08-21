"""CFIS (campaignfinance.wi.gov) ingest via its public tRPC API.

Usage: python -m scraper.fetch_cfis map <sqlite_path>
       python -m scraper.fetch_cfis transactions [--since 2025-01]

`map` resolves each sitting legislator to their candidate committee
(auto-accept only on an unambiguous name match; else listed for curation
in importer/candidate_committees.json). `transactions` archives receipts
for mapped committees into monthly JSON files under _data/cfis/.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
import unicodedata
from datetime import date
from pathlib import Path

import requests

from scraper.http import USER_AGENT

BASE = "https://campaignfinance.wi.gov/api/trpc/"
DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "cfis"
CURATED_PATH = (
    Path(__file__).resolve().parents[1] / "importer" / "candidate_committees.json"
)
MAP_PATH = DATA_DIR / "committee_map.json"
PAGE = 1000
DELAY = 0.4


def call(http: requests.Session, proc: str, payload: dict) -> dict:
    url = BASE + proc + "?input=" + requests.utils.quote(json.dumps({"json": payload}))
    response = http.get(url, timeout=60)
    response.raise_for_status()
    body = response.json()
    result = body.get("result", {}).get("data", {}).get("json")
    if result is None:
        raise RuntimeError(f"CFIS drift: unexpected shape from {proc}: {str(body)[:200]}")
    return result


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(folded.lower().replace(".", " ").replace("-", " ").split())


# our people hold state legislative office; a committee named for any other
# office is never auto-attributed (statewide runs go through curation)
OTHER_OFFICE_WORDS = {
    "judge", "sheriff", "mayor", "alderman", "alderperson", "county", "school",
    "congress", "congressional", "clerk", "coroner", "court", "supervisor",
    "governor", "treasurer", "attorney", "regent", "municipal", "trustee",
}


def _token_match(committee_word: str, name_word: str) -> bool:
    """Prefix matching only between substantial tokens: an initial like 'R.'
    can never satisfy a name word."""
    if len(committee_word) < 3 or len(name_word) < 3:
        return committee_word == name_word
    return committee_word.startswith(name_word) or name_word.startswith(committee_word)


def match_committees(person_name: str, hits: list[dict]) -> list[dict]:
    """Committees safely attributable to this person: candidate/legacy-typed,
    no other-office words, and EVERY word of the person's name must match a
    substantial committee-name token."""
    words = _normalize(person_name).split()
    matched = []
    for h in hits:
        ctype = (((h.get("committee") or {}).get("committeeType") or {}).get("name") or "")
        if ctype and "candidate" not in ctype.lower() and ctype.lower() != "unregistered":
            continue
        cwords = _normalize(h["name"]).split()
        if set(cwords) & OTHER_OFFICE_WORDS:
            continue
        if all(any(_token_match(c, w) for c in cwords) for w in words):
            matched.append(h)
    return matched


def name_variants(
    name: str, family_name: str, aliases: list[str]
) -> list[str]:
    """The display name plus aliases that carry independent identity: at
    least two substantial words, and at least one word beyond the surname
    (a bare-surname alias like 'RIVERA WAGNER' has no identifying power)."""
    surname_tokens = set(_normalize(family_name).split())
    variants = [name]
    for alias in aliases:
        words = _normalize(alias.replace(",", " ")).split()
        if (
            len(words) >= 2
            and all(len(w) >= 3 for w in words)
            and not set(words) <= surname_tokens
        ):
            variants.append(alias)
    return variants


def load_person_details() -> dict[str, tuple[str, list[str]]]:
    from importer.roster import load_people

    people_root = Path(__file__).resolve().parents[1] / "_data" / "people"
    dirs = [d for d in (people_root / "wi", people_root / "wi-executive") if d.exists()]
    return {p.id: (p.family_name, p.aliases) for p in load_people(dirs)}


def build_map(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    people = conn.execute(
        "SELECT id, name FROM people"
        " WHERE current_role IN ('Representative', 'Senator') ORDER BY name"
    ).fetchall()
    conn.close()
    person_details = load_person_details()

    curated = {}
    if CURATED_PATH.exists():
        curated = {
            k: v
            for k, v in json.loads(CURATED_PATH.read_text(encoding="utf-8")).items()
            if not k.startswith("_")
        }

    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    mapped, unresolved = [], []
    for person_id, name in people:
        override = curated.get(person_id)
        if override:
            if override.get("skip"):
                continue
            mapped.append(
                {"person_id": person_id, "person": name,
                 "entity_id": override["entity_id"],
                 "committee": override["committee"], "matched": "curated"}
            )
            continue
        surname = _normalize(name).split()[-1]
        hit_list: list[dict] = []
        seen_ids: set[int] = set()
        for query in (name, surname):
            hits = call(
                http, "entity.searchEntities",
                {"searchQuery": query, "limit": 20, "entityTypeOf": ["COMMITTEE"],
                 "alwaysRespectPiiRedaction": True},
            )
            for h in hits if isinstance(hits, list) else hits.get("results", []):
                if h["id"] not in seen_ids:
                    seen_ids.add(h["id"])
                    hit_list.append(h)
            time.sleep(DELAY)
        family_name, aliases = person_details.get(person_id, (name.split()[-1], []))
        matches: list[dict] = []
        matched_ids: set[int] = set()
        for variant in name_variants(name, family_name, aliases):
            for m in match_committees(variant, hit_list):
                if m["id"] not in matched_ids:
                    matched_ids.add(m["id"])
                    matches.append(m)
        if matches:
            for match in matches:
                mapped.append(
                    {"person_id": person_id, "person": name, "entity_id": match["id"],
                     "committee": match["name"], "matched": "auto"}
                )
        else:
            unresolved.append({"person": name, "person_id": person_id,
                               "hits": [h["name"] for h in hit_list[:5]]})

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(mapped, indent=1), encoding="utf-8")
    print(f"mapped {len(mapped)} committees -> {MAP_PATH}")
    # coverage gap, not misattribution risk: warn and continue
    for u in unresolved:
        print(f"UNRESOLVED (add to candidate_committees.json): {u}", file=sys.stderr)
    if unresolved:
        print(f"WARNING: {len(unresolved)} legislators lack a committee mapping",
              file=sys.stderr)


def month_windows(since: str) -> list[tuple[str, str, str]]:
    """(label, first_day, last_day) for each month from `since` to now.

    dateTo carries an end-of-day time: some CFIS rows hold timezone
    artifacts like T05:00:00Z, and a bare date bound parses as midnight,
    silently dropping last-day rows into the crack between months."""
    year, month = int(since[:4]), int(since[5:7])
    today = date.today()
    windows = []
    while (year, month) <= (today.year, today.month):
        nxt_y, nxt_m = (year + 1, 1) if month == 12 else (year, month + 1)
        last = date(nxt_y, nxt_m, 1).toordinal() - 1
        windows.append(
            (f"{year:04d}-{month:02d}", f"{year:04d}-{month:02d}-01",
             date.fromordinal(last).isoformat() + "T23:59:59")
        )
        year, month = nxt_y, nxt_m
    return windows


def load_committee_ids() -> dict:
    return {
        m["entity_id"]: m["person_id"]
        for m in json.loads(MAP_PATH.read_text(encoding="utf-8"))
    }


def fetch_window(
    http: requests.Session, committee_ids: dict, first: str, last: str,
) -> tuple[list[dict], int, int | None, set]:
    count = call(
        http, "publicFrontendApi.getTransactionsTotalCount",
        {"dateFrom": first, "dateTo": last},
    )
    expected = int(count) if isinstance(count, (int, float)) else None
    rows, skip, seen_ids = [], 0, set()
    while True:
        page = call(
            http, "publicFrontendApi.getTransactions",
            {"take": PAGE, "skip": skip, "sortBy": "date",
             "sortDirection": "asc", "dateFrom": first, "dateTo": last},
        )
        results = page.get("results", [])
        for t in results:
            seen_ids.add(t["id"])
            committee_id = t.get("createdByEntityId")
            person_id = committee_ids.get(committee_id)
            if not person_id:
                continue
            if (t.get("transactionType") or {}).get("direction") != "INCOMING":
                continue
            from_entity = t.get("from_entity") or {}
            rows.append(
                {
                    "id": t["id"],
                    "person_id": person_id,
                    "committee_entity_id": committee_id,
                    "date": (t.get("date") or "")[:10],
                    "amount": t.get("amount"),
                    # CFIS's own entity id: collision-proof donor identity
                    "from_entity_id": from_entity.get("id"),
                    "from_name": from_entity.get("name"),
                    "from_type": (from_entity.get("entityType") or {}).get("name"),
                    "occupation": t.get("fromOccupationTitle"),
                    "category": (t.get("transactionCategory") or {}).get("label"),
                }
            )
        skip += len(results)
        if len(results) < PAGE:
            break
        time.sleep(DELAY)
    return rows, skip, expected, seen_ids


def _fetch_with_retries(
    http: requests.Session, committee_ids: dict, first: str, last: str,
    label: str, attempts: int,
) -> tuple[list[dict], int, int | None, set, bool]:
    """Retake the snapshot until count and pages agree exactly; the newest
    month is a moving target while filings land."""
    for attempt in range(attempts):
        rows, skip, expected, seen_ids = fetch_window(http, committee_ids, first, last)
        if expected is None or skip == expected:
            return rows, skip, expected, seen_ids, True
        if attempt < attempts - 1:
            print(f"{label}: count moved during fetch ({skip} vs {expected}), retaking")
            time.sleep(5)
    return rows, skip, expected, seen_ids, False


def _drift_is_benign(
    http: requests.Session, committee_ids: dict, first: str, last: str,
    seen_ids: set, expected: int, label: str,
) -> bool:
    """The date-sorted view can briefly omit freshly amended rows that the
    unsorted view still returns. Benign only if every omitted row is one
    our data can never contain (not an incoming receipt to a mapped
    committee); anything else stays a hard failure."""
    plain = call(
        http, "publicFrontendApi.getTransactions",
        {"take": PAGE, "skip": 0, "dateFrom": first, "dateTo": last},
    ).get("results", [])
    omitted = [t for t in plain if t["id"] not in seen_ids]
    relevant = [
        t for t in omitted
        if (t.get("transactionType") or {}).get("direction") == "INCOMING"
        and t.get("createdByEntityId") in committee_ids
    ]
    if len(plain) != expected or relevant:
        return False
    print(
        f"WARNING: {label} date-sorted view omitted {len(omitted)} "
        "non-receipt rows; accepted, refreshes nightly"
    )
    return True


def fetch_transactions(since: str) -> None:
    committee_ids = load_committee_ids()
    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT

    windows = month_windows(since)
    # immutable once past; always refresh the two newest months
    refresh = {w[0] for w in windows[-2:]}
    latest = windows[-1][0]
    for label, first, last in windows:
        out = DATA_DIR / f"tx-{label}.json"
        if out.exists() and label not in refresh:
            continue
        rows, skip, expected, seen_ids, matched = _fetch_with_retries(
            http, committee_ids, first, last, label, attempts=3 if label == latest else 1,
        )
        if not matched and label == latest and expected is not None and expected <= PAGE:
            matched = _drift_is_benign(http, committee_ids, first, last, seen_ids, expected, label)
        if not matched:
            raise RuntimeError(
                f"CFIS drift: {label} paged {skip} rows but count said {expected}"
            )
        out.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        print(f"{label}: {skip} scanned, {len(rows)} receipts kept -> {out.name}")
        time.sleep(DELAY)


def audit_archives(sample: int) -> None:
    """Re-fetch a rotating sample of archived past months and reconcile
    against the archive. Amendments legitimately rewrite filed history, so
    a drifted month is refreshed in place and reported, never left stale."""
    committee_ids = load_committee_ids()
    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT
    windows = month_windows("2008-01")
    newest = {w[0] for w in windows[-2:]}
    archived = [w for w in windows
                if w[0] not in newest and (DATA_DIR / f"tx-{w[0]}.json").exists()]
    if not archived:
        print("audit: no archived months to sample")
        return
    # deterministic rotation: full history gets covered over successive days
    offset = date.today().toordinal() * sample
    picks = [archived[(offset + i) % len(archived)] for i in range(min(sample, len(archived)))]
    drifted = 0
    for label, first, last in picks:
        rows, skip, expected, _ = fetch_window(http, committee_ids, first, last)
        if expected is not None and skip != expected:
            raise RuntimeError(
                f"CFIS drift: audit {label} paged {skip} rows but count said {expected}"
            )
        out = DATA_DIR / f"tx-{label}.json"
        old = json.loads(out.read_text(encoding="utf-8"))
        if old == rows:
            print(f"audit {label}: unchanged ({len(rows)} receipts)")
            continue
        drifted += 1
        old_ids = {r["id"] for r in old}
        new_ids = {r["id"] for r in rows}
        print(
            f"audit {label}: AMENDED upstream ({len(old)} -> {len(rows)} receipts, "
            f"+{len(new_ids - old_ids)} added, -{len(old_ids - new_ids)} removed); "
            "archive refreshed"
        )
        out.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        time.sleep(DELAY)
    print(f"audit: {len(picks)} months sampled, {drifted} refreshed")


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    if argv[0] == "map":
        build_map(Path(argv[1]))
        return 0
    if argv[0] == "transactions":
        since = argv[argv.index("--since") + 1] if "--since" in argv else "2025-01"
        fetch_transactions(since)
        return 0
    if argv[0] == "audit":
        sample = int(argv[argv.index("--sample") + 1]) if "--sample" in argv else 3
        audit_archives(sample)
        return 0
    print(f"unknown command {argv[0]!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
