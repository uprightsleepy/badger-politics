"""Static JSON API tree: /api/v1/... pre-generated at build time.

Layout (all CDN-served static files):
  /api/v1/meta.json                      freshness + session stats
  /api/v1/sessions.json
  /api/v1/bills/{session}/index.json     light per-session bill index
  /api/v1/bills/{session}/{ab656}.json   full bill + sponsors + actions + votes
  /api/v1/votes/{vote_id}.json           full roll call
  /api/v1/legislators/index.json
  /api/v1/legislators/{person_id}.json   profile + election + sponsorships + votes
  /api/v1/local/{body}/index.json        a city council's members
  /api/v1/local/{body}/{member}.json     one member + their latest votes
  /api/v1/elections/statewide.json       statewide races + certified results
  /api/v1/elections/us-house.json        U.S. House candidates on the ballot
  /api/v1/elections/seats/{seat}.json    assembly-15 / senate-5: holder, race, results
  /api/v1/committees/index.json          every committee + chair
  /api/v1/committees/{slug}.json         members + upcoming and past hearings
  /api/v1/hearings.json                  every hearing on record
  /api/v1/subjects/index.json            subject headings + bill counts
  /api/v1/subjects/{slug}.json           the bills filed under one heading
  /api/v1/federal/index.json             the Wisconsin delegation
  /api/v1/federal/{slug}.json            one member + every floor roll call
  /api/v1/money/legislators/{slug}.json  receipts summary (never beside votes)
  /api/v1/money/committees/index.json    committees that gave legislators $1,000+
  /api/v1/money/committees/{id}.json     what one gave, to whom, and its own money
  /api/v1/money/independent.json         every outside-spending filing, as filed

Money follows README mandate 5 like the site: individual donors only in
totals, never by name, and never in the same file as votes.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

from dataproducts import queries

_ensured_dirs: set[Path] = set()  # builds only add directories, never remove


def write_json(path: Path, payload: dict | list) -> None:
    if path.parent not in _ensured_dirs:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ensured_dirs.add(path.parent)
    path.write_text(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )


def bill_slug(identifier: str) -> str:
    return identifier.replace(" ", "").lower()


# The site and the data products have to agree on a person's slug, or the
# Atom feed a page links to does not exist. Both read this one committed
# map; see importer/person_slugs.py for why it is a file and not a rule.
_SLUGS_PATH = Path(__file__).resolve().parents[2] / "site" / "src" / "data" / "person-slugs.json"
try:
    _PERSON_SLUGS: dict[str, str] = json.loads(_SLUGS_PATH.read_text(encoding="utf-8"))
except (OSError, ValueError) as exc:
    # every feed and API URL would silently fall back to uuid tails, which
    # no page links to; say so where the build log will show it
    print(f"WARNING: person slugs unreadable ({exc}); URLs fall back to ids", file=sys.stderr)
    _PERSON_SLUGS = {}


def person_slug(person_id: str) -> str:
    """Name slug where one is on file, the old uuid tail otherwise."""
    return _PERSON_SLUGS.get(person_id) or person_id.rsplit("/", 1)[-1]


def committee_slug(committee_id: str) -> str:
    """site/src/lib/format.ts committeeSlug."""
    return committee_id.rsplit("/", 1)[-1]


def subject_slug(subject: str) -> str:
    """site/src/lib/subjects.ts subjectSlug: headings the index reprints with
    small differences share one slug, as they share one page."""
    return re.sub(r"[^a-z0-9]+", "-", subject.lower()).strip("-")


def seat_slug(chamber: str, district: int) -> str:
    """The district page's address: assembly-14 / senate-5."""
    return f"{'senate' if chamber == 'upper' else 'assembly'}-{district}"


def build_api(
    conn: sqlite3.Connection, out: Path, hearings: list[dict] | None = None
) -> int:
    api = out / "api" / "v1"
    files = 0

    sessions = queries.sessions(conn)
    write_json(api / "sessions.json", sessions)
    write_json(api / "meta.json", queries.meta(conn))
    files += 2

    # one pass over all roll calls serves both the /votes/ tree and the
    # per-bill payloads; grouping preserves the query's (date, id) order.
    # One grouped scan replaces a per-event query; the lists live exactly
    # as long as events_by_bill kept them before (shared objects, no copy).
    records_by_event = dict(queries.vote_records_grouped(conn))
    events_by_bill: dict[str, list[dict]] = {}
    for event in queries.vote_events(conn):
        records = records_by_event.get(event["id"], [])
        write_json(api / "votes" / f"{event['id']}.json", {**event, "records": records})
        files += 1
        events_by_bill.setdefault(event["bill_id"], []).append(
            {
                "id": event["id"],
                "date": event["date"],
                "chamber": event["chamber"],
                "motion": event["motion"],
                "result": event["result"],
                "yes_count": event["yes_count"],
                "no_count": event["no_count"],
                "nv_count": event["nv_count"],
                "source_url": event["source_url"],
                "records": records,
            }
        )

    for session in sessions:
        session_id = session["id"]
        session_bills = queries.bills(conn, session_id)
        index = [
            {
                "id": b["id"],
                "identifier": b["identifier"],
                "title": b["title"],
                "status": b["status"],
                "latest_action_date": b["latest_action_date"],
                "died_without_hearing": b["died_without_hearing"],
            }
            for b in session_bills
        ]
        write_json(api / "bills" / session_id / "index.json", index)
        files += 1

        # two grouped scans per session replace two queries per bill
        session_sponsors = queries.sponsors_for_session(conn, session_id)
        session_actions = queries.actions_for_session(conn, session_id)
        session_versions = queries.links_for_session(conn, session_id, "bill_versions")
        session_documents = queries.links_for_session(conn, session_id, "bill_documents")
        companions: dict[str, list[dict]] = {}
        for row in conn.execute(
            f"""SELECT bc.bill_id, b.identifier, b.status FROM bill_companions bc
               JOIN bills b ON b.id = bc.companion_bill_id
               WHERE b.session_id = ? AND {queries.exportable("b.")}
               ORDER BY b.identifier""",
            (session_id,),
        ):
            companions.setdefault(row[0], []).append({"identifier": row[1], "status": row[2]})
        for bill in session_bills:
            payload = {
                **{k: bill[k] for k in bill.keys() if k != "session_id"},
                "session": session_id,
                "sponsors": session_sponsors.get(bill["id"], []),
                "actions": session_actions.get(bill["id"], []),
                "votes": events_by_bill.get(bill["id"], []),
                # official docs.legis links; the texts themselves are not rehosted
                "versions": session_versions.get(bill["id"], []),
                "documents": session_documents.get(bill["id"], []),
                "companions": companions.get(bill["id"], []),
            }
            write_json(
                api / "bills" / session_id / f"{bill_slug(bill['identifier'])}.json",
                payload,
            )
            files += 1

    write_json(
        api / "elections" / "statewide.json",
        {
            "races": queries.statewide_races(conn),
            "history": queries.statewide_history(conn),
            "counties": queries.statewide_counties(conn),
        },
    )
    files += 1

    people = queries.people(conn)
    write_json(
        api / "legislators" / "index.json",
        [
            {
                "id": person_slug(p["id"]),
                "name": p["name"],
                "party": p["party"],
                "chamber": p["chamber"],
                "district": p["district"],
            }
            for p in people
        ],
    )
    files += 1
    for person in people:
        payload = {
            **person,
            "id": person_slug(person["id"]),
            "election": queries.election_for(conn, person["id"]),
            "sponsorships": queries.sponsorships_by_person(conn, person["id"]),
            "votes": queries.votes_by_person(conn, person["id"]),
        }
        write_json(api / "legislators" / f"{person_slug(person['id'])}.json", payload)
        files += 1

    # city councils: the same record-first shape, keyed by the tenant's ids
    metadata = queries.meta(conn)
    for body in queries.local_bodies(conn):
        members = queries.local_members(conn, body["tenant"])
        raw_coverage = metadata.get(f"local_coverage_{body['tenant']}")
        coverage = {"coverage": json.loads(raw_coverage)} if raw_coverage else {}
        write_json(
            api / "local" / body["slug"] / "index.json",
            {
                "body": body,
                **coverage,
                "members": [
                    {k: m[k] for k in ("person_id", "name", "slug", "seat", "is_current",
                                       "image_url", "vote_count")}
                    for m in members
                ],
            },
        )
        files += 1
        for m in members:
            if not (m["is_current"] or m["vote_count"]):
                continue
            write_json(
                api / "local" / body["slug"] / f"{m['slug']}.json",
                {**m, "body": body["slug"], **coverage,
                 "votes": queries.local_member_votes(conn, body["tenant"], m["person_id"])},
            )
            files += 1

    files += _build_elections(conn, api)
    files += _build_committees(conn, api, queries.hearings(conn) if hearings is None else hearings)
    files += _build_subjects(conn, api)
    files += _build_federal(conn, api)
    files += _build_money(conn, api, people)
    return files


def _person_ref(person_id: str | None, **fields) -> dict:
    """A person as other files link them: the slug their own file is under."""
    return {"id": person_slug(person_id) if person_id else None, **fields}


def _build_elections(conn: sqlite3.Connection, api: Path) -> int:
    write_json(api / "elections" / "us-house.json", {"races": queries.congressional_races(conn)})
    results: dict[tuple[str, int], dict[int, dict]] = {}
    for r in queries.election_history(conn):
        years = results.setdefault((r["chamber"], r["district"]), {})
        contest = years.setdefault(r["year"], {"year": r["year"], "total_cast": r["total_cast"],
                                               "candidates": []})
        contest["candidates"].append({k: r[k] for k in ("candidate", "party", "votes")})
    holders = {(p["chamber"], p["district"]): p for p in queries.sitting_legislators(conn)}
    seats = [("lower", d) for d in range(1, 100)] + [("upper", d) for d in range(1, 34)]
    for chamber, district in seats:
        holder = holders.get((chamber, district))
        write_json(api / "elections" / "seats" / f"{seat_slug(chamber, district)}.json", {
            "seat": seat_slug(chamber, district), "chamber": chamber, "district": district,
            "holder": holder and _person_ref(holder["id"], name=holder["name"],
                                             party=holder["party"]),
            "election": holder and queries.election_for(conn, holder["id"]),
            "results": list(results.get((chamber, district), {}).values()),
        })
    return 1 + len(seats)


def _build_committees(conn: sqlite3.Connection, api: Path, hearings: list[dict]) -> int:
    write_json(api / "hearings.json", hearings)
    today = date.today().isoformat()
    members = queries.committee_members(conn)
    by_committee: dict[str, list[dict]] = {}
    for h in hearings:
        by_committee.setdefault(h["committee_id"], []).append(h)
    index = []
    for c in queries.committees(conn):
        slug = committee_slug(c["id"])
        committee = {"id": slug, "name": c["name"], "chamber": c["chamber"],
                     "chair": c["chair_person_id"] and _person_ref(c["chair_person_id"],
                                                                  name=c["chair_name"])}
        roster = members.get(c["id"], [])
        index.append({**committee, "member_count": len(roster)})
        own = by_committee.get(c["id"], [])
        write_json(api / "committees" / f"{slug}.json", {
            **committee,
            "members": [_person_ref(m["person_id"], **{k: m[k] for k in m if k != "person_id"})
                        for m in roster],
            "upcoming_hearings": [h for h in own if (h["date"] or "") >= today],
            "past_hearings": [h for h in reversed(own) if (h["date"] or "") < today],
        })
    write_json(api / "committees" / "index.json", index)
    return 2 + len(index)


def _build_subjects(conn: sqlite3.Connection, api: Path) -> int:
    subjects: dict[str, dict] = {}
    for row in queries.subject_bills(conn):
        slug = subject_slug(row["subject"])
        # newest session first, so the first heading seen is how it prints now
        entry = subjects.setdefault(slug, {
            "slug": slug, "title": re.sub(r" (?:_|—|--) ", ": ", row["subject"]),
            "headings": [], "bills": {},
        })
        if row["subject"] not in entry["headings"]:
            entry["headings"].append(row["subject"])
        entry["bills"].setdefault(row["id"], {
            "id": row["id"], "identifier": row["identifier"], "session": row["session_id"],
            "title": row["title"], "status": row["status"],
        })
    index = []
    for entry in sorted(subjects.values(), key=lambda e: e["title"]):
        bills = list(entry["bills"].values())
        index.append({k: entry[k] for k in ("slug", "title", "headings")} | {"bills": len(bills)})
        write_json(api / "subjects" / f"{entry['slug']}.json", {**entry, "bills": bills})
    write_json(api / "subjects" / "index.json", index)
    return 1 + len(index)


def _build_federal(conn: sqlite3.Connection, api: Path) -> int:
    members = queries.federal_members(conn)
    write_json(api / "federal" / "index.json", [
        {k: m[k] for k in ("slug", "name", "party", "chamber", "district",
                           "term_start", "term_end", "bioguide")}
        for m in members
    ])
    for m in members:
        write_json(api / "federal" / f"{m['slug']}.json",
                   {**m, "votes": queries.federal_votes_for(conn, m)})
    return 1 + len(members)


# README mandate 5: the framing ships with the money
MONEY_NOTES = [
    "Corporations cannot contribute to Wisconsin candidates.",
    "A committee's (PAC's) money is its own, raised from its contributors; it is not a"
    " corporate payment, whatever its name mentions.",
    "Occupations are as donors reported them and say nothing about any employer.",
    "A contribution is not an endorsement of any vote.",
    "Individual donors appear only in totals, never by name.",
    "Receipts are broader than donations (loans, transfers, refunds, in-kind support),"
    " and receipts minus spending is not cash on hand.",
    "Source: the Wisconsin Ethics Commission's campaign finance system,"
    " https://campaignfinance.wi.gov",
]


def _build_money(conn: sqlite3.Connection, api: Path, people: list[dict]) -> int:
    money = api / "money"
    files = 0
    by_id = {p["id"]: p for p in people}
    for person_id in queries.money_people(conn):
        p = by_id[person_id]
        write_json(money / "legislators" / f"{person_slug(person_id)}.json", {
            "legislator": _person_ref(person_id, name=p["name"], party=p["party"],
                                      chamber=p["chamber"], district=p["district"]),
            **queries.legislator_money(conn, person_id), "notes": MONEY_NOTES,
        })
        files += 1
    committees = queries.donor_committees(conn)
    recipients = queries.donor_recipients(conn)
    write_json(money / "committees" / "index.json",
               {"committees": committees, "notes": MONEY_NOTES})
    for c in committees:
        write_json(money / "committees" / f"{c['entity_id']}.json", {
            **c,
            "recipients": [_person_ref(r["person_id"],
                                       **{k: r[k] for k in r if k != "person_id"})
                           for r in recipients.get(c["entity_id"], [])],
            "own_money": queries.committee_own_money(conn, c["entity_id"]),
            "notes": MONEY_NOTES,
        })
    write_json(money / "independent.json", {
        "filings": queries.independent_expenditures(conn),
        "notes": ["Every outside-spending (independent expenditure) filing, exactly as"
                  " filed with the Wisconsin Ethics Commission; nothing is added up.",
                  "Each filing carries the Commission's transaction ID and the report it"
                  " was filed on: https://campaignfinance.wi.gov/browse-data/report/<report_id>"],
    })
    return files + 2 + len(committees)
