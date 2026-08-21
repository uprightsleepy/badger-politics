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
    """(label, first_day, last_day) for each month from `since` to now."""
    year, month = int(since[:4]), int(since[5:7])
    today = date.today()
    windows = []
    while (year, month) <= (today.year, today.month):
        nxt_y, nxt_m = (year + 1, 1) if month == 12 else (year, month + 1)
        last = date(nxt_y, nxt_m, 1).toordinal() - 1
        windows.append(
            (f"{year:04d}-{month:02d}", f"{year:04d}-{month:02d}-01",
             date.fromordinal(last).isoformat())
        )
        year, month = nxt_y, nxt_m
    return windows


def fetch_transactions(since: str) -> None:
    committee_ids = {
        m["entity_id"]: m["person_id"]
        for m in json.loads(MAP_PATH.read_text(encoding="utf-8"))
    }
    http = requests.Session()
    http.headers["User-Agent"] = USER_AGENT

    def fetch_month(first: str, last: str) -> tuple[list[dict], int, object, set]:
        expected = call(
            http, "publicFrontendApi.getTransactionsTotalCount",
            {"dateFrom": first, "dateTo": last},
        )
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

    windows = month_windows(since)
    for label, first, last in windows:
        out = DATA_DIR / f"tx-{label}.json"
        # immutable once past; always refresh the two newest months
        if out.exists() and label not in {w[0] for w in windows[-2:]}:
            continue
        # the newest month is a moving target: filings land while we page,
        # so retake the whole snapshot until count and pages agree exactly
        attempts = 3 if label == windows[-1][0] else 1
        for attempt in range(attempts):
            rows, skip, expected, seen_ids = fetch_month(first, last)
            matched = not isinstance(expected, (int, float)) or skip == expected
            if matched:
                break
            if attempt < attempts - 1:
                print(f"{label}: count moved during fetch ({skip} vs {expected}), retaking")
                time.sleep(5)
        diffable = (label == windows[-1][0]
                    and isinstance(expected, (int, float)) and expected <= PAGE)
        if not matched and diffable:
            # the date-sorted view can briefly omit freshly amended rows that
            # the unsorted view still returns. Accept only if every omitted
            # row is one our data can never contain (not an incoming receipt
            # to a mapped committee); anything else stays a hard failure.
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
            if len(plain) == expected and not relevant:
                print(
                    f"WARNING: {label} date-sorted view omitted {len(omitted)} "
                    "non-receipt rows; accepted, refreshes nightly"
                )
                matched = True
        if not matched:
            raise RuntimeError(
                f"CFIS drift: {label} paged {skip} rows but count said {expected}"
            )
        out.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        print(f"{label}: {skip} scanned, {len(rows)} receipts kept -> {out.name}")
        time.sleep(DELAY)


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
    print(f"unknown command {argv[0]!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
