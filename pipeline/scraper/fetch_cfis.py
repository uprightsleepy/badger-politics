"""CFIS (campaignfinance.wi.gov) ingest via its public tRPC API.

Usage: python -m scraper.fetch_cfis map <sqlite_path>
       python -m scraper.fetch_cfis transactions [--since 2025-01]
       python -m scraper.fetch_cfis audit [--sample 3]

`map` accepts unambiguous name matches; other matches require curation in
importer/candidate_committees.json. `transactions` archives mapped receipts by
month; `audit` refreshes older months. Both accept --as-of YYYY-MM-DD.
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

from scraper.cfis_api import DELAY, PAGE, call, month_windows, transaction_count, transaction_pages
from scraper.http import session

DATA_DIR = Path(__file__).resolve().parents[1] / "_data" / "cfis"
CURATED_PATH = (
    Path(__file__).resolve().parents[1] / "importer" / "candidate_committees.json"
)
MAP_PATH = DATA_DIR / "committee_map.json"


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(folded.lower().replace(".", " ").replace("-", " ").split())


# Other-office committees require curation, never automatic attribution.
OTHER_OFFICE_WORDS = {
    "judge", "sheriff", "mayor", "alderman", "alderperson", "county", "school",
    "congress", "congressional", "clerk", "coroner", "court", "supervisor",
    "governor", "treasurer", "attorney", "regent", "municipal", "trustee",
}


def _token_match(committee_word: str, name_word: str) -> bool:
    """Allow prefixes only for tokens of 3+ characters; initials must match exactly."""
    if len(committee_word) < 3 or len(name_word) < 3:
        return committee_word == name_word
    return committee_word.startswith(name_word) or name_word.startswith(committee_word)


def match_committees(person_name: str, hits: list[dict]) -> list[dict]:
    """Require a candidate/legacy type, no other-office words, and every name token."""
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
    """Include aliases with two substantial words and a token beyond the surname."""
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

    previous = json.loads(MAP_PATH.read_text(encoding="utf-8")) if MAP_PATH.exists() else []

    http = session()
    mapped, unresolved = [], []
    for person_id, name in people:
        override = curated.get(person_id)
        if override:
            if override.get("skip"):
                continue
            if override.get("retain_existing"):
                mapped.extend(m for m in previous
                              if m["person_id"] == person_id
                              and m["entity_id"] != override["entity_id"])
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

    owners = {}
    for entry in mapped:
        entity_id = entry["entity_id"]
        if entity_id in owners and owners[entity_id] != entry["person_id"]:
            raise ValueError(f"CFIS committee {entity_id} maps to multiple legislators")
        owners[entity_id] = entry["person_id"]
    mapped = list({(m["person_id"], m["entity_id"]): m for m in mapped}.values())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(mapped, indent=1), encoding="utf-8")
    print(f"mapped {len(mapped)} committees -> {MAP_PATH}")
    # coverage gap, not misattribution risk: warn and continue
    for u in unresolved:
        print(f"UNRESOLVED (add to candidate_committees.json): {u}", file=sys.stderr)
    if unresolved:
        print(f"WARNING: {len(unresolved)} legislators lack a committee mapping",
              file=sys.stderr)


def load_committee_ids() -> dict:
    return {
        m["entity_id"]: m["person_id"]
        for m in json.loads(MAP_PATH.read_text(encoding="utf-8"))
    }


def fetch_window(
    http: requests.Session, committee_ids: dict, first: str, last: str,
    *, page_size: int | None = None,
) -> tuple[list[dict], int, int, set]:
    expected = transaction_count(http, first, last)
    rows, skip, seen_ids = [], 0, set()
    for results in transaction_pages(http, first, last, page_size=page_size):
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
    return rows, skip, expected, seen_ids


def _fetch_with_retries(
    http: requests.Session, committee_ids: dict, first: str, last: str,
    label: str, attempts: int,
) -> tuple[list[dict], int, int, set, bool]:
    """Retake incomplete windows; smaller pages recover inconsistent small listings."""
    page_size = PAGE
    for attempt in range(attempts):
        rows, skip, expected, seen_ids = fetch_window(
            http, committee_ids, first, last, page_size=page_size,
        )
        if skip == expected == len(seen_ids):
            if attempt:
                expected = transaction_count(http, first, last)
            if skip == expected:
                return rows, skip, expected, seen_ids, True
        if attempt < attempts - 1:
            print(f"{label}: incomplete listing ({skip} rows, {len(seen_ids)} unique,"
                  f" expected {expected}), retaking")
            page_size = min(PAGE, 100) if expected <= PAGE else PAGE
            time.sleep(5)
    return rows, skip, expected, seen_ids, False


def fetch_transactions(since: str, as_of: date | None = None) -> None:
    committee_ids = load_committee_ids()
    http = session()

    windows = month_windows(since, as_of.strftime("%Y-%m") if as_of else None)
    # Refresh the newest two months here; the audit rotates older months.
    refresh = {w[0] for w in windows[-2:]}
    for label, first, last in windows:
        out = DATA_DIR / f"tx-{label}.json"
        if out.exists() and label not in refresh:
            continue
        rows, skip, expected, seen_ids, matched = _fetch_with_retries(
            http, committee_ids, first, last, label, attempts=3,
        )
        if not matched:
            raise RuntimeError(
                f"CFIS drift: {label} paged {skip} rows"
                f" ({len(seen_ids)} unique) but count said {expected}"
            )
        out.write_text(json.dumps(rows, indent=0), encoding="utf-8")
        print(f"{label}: {skip} scanned, {len(rows)} receipts kept -> {out.name}")
        time.sleep(DELAY)


def audit_archives(sample: int, as_of: date | None = None) -> None:
    """Refresh a rotating sample of older months for upstream amendments."""
    committee_ids = load_committee_ids()
    http = session()
    as_of = as_of or date.today()
    windows = month_windows("2008-01", as_of.strftime("%Y-%m"))
    newest = {w[0] for w in windows[-2:]}
    archived = [w for w in windows
                if w[0] not in newest and (DATA_DIR / f"tx-{w[0]}.json").exists()]
    if not archived:
        print("audit: no archived months to sample")
        return
    # deterministic rotation: full history gets covered over successive days
    offset = as_of.toordinal() * sample
    picks = [archived[(offset + i) % len(archived)] for i in range(min(sample, len(archived)))]
    drifted = 0
    for label, first, last in picks:
        rows, skip, expected, seen_ids, matched = _fetch_with_retries(
            http, committee_ids, first, last, f"audit {label}", attempts=3,
        )
        if not matched:
            raise RuntimeError(
                f"CFIS drift: audit {label} paged {skip} rows"
                f" ({len(seen_ids)} unique) but count said {expected}"
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
    as_of = date.fromisoformat(argv[argv.index("--as-of") + 1]) if "--as-of" in argv else None
    if argv[0] == "map":
        build_map(Path(argv[1]))
        return 0
    if argv[0] == "transactions":
        since = argv[argv.index("--since") + 1] if "--since" in argv else "2025-01"
        fetch_transactions(since, as_of)
        return 0
    if argv[0] == "audit":
        sample = int(argv[argv.index("--sample") + 1]) if "--sample" in argv else 3
        audit_archives(sample, as_of)
        return 0
    print(f"unknown command {argv[0]!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
