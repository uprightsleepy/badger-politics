"""Import U.S. Senate and House roll calls for Wisconsin's delegation.

Reads the XML mirrored by scraper.fetch_federal_votes. Attribution is by
the chambers' own stable ids -- the Senate's LIS member id, the House's
bioguide name-id -- so there is no name matching anywhere in this
module. Senate votes store the full chamber (100 rows each); House votes
store Wisconsin's rows only, because 435 rows across twenty years of
roll calls would swell the snapshot for context nothing displays. Both
chambers' tallies are reconciled against the full membership at import
time either way.

Hard checks, in the spirit of the state importer: a vote's stated yea
and nay counts must equal the counted positions, and every vote must
carry exactly two Wisconsin senators. Either failing aborts the run.

Usage: python -m importer.import_federal <data_dir> <sqlite>
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

# the same rule that names state legislators' pages, accents folded
from importer.person_slugs import slugify


def text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


def parse_date(raw: str) -> str:
    """'August 8, 2026,  04:36 AM' -> '2026-08-08'."""
    head = ",".join(raw.split(",")[:2])
    return datetime.strptime(head.strip(), "%B %d, %Y").date().isoformat()


# congress.gov path segment per Senate document type; anything unlisted
# (nominations, treaties, motions with no document) gets no bill link
DOC_PATHS = {
    "S.": "senate-bill",
    "S.Res.": "senate-resolution",
    "S.J.Res.": "senate-joint-resolution",
    "S.Con.Res.": "senate-concurrent-resolution",
    "H.R.": "house-bill",
    "H.Res.": "house-resolution",
    "H.J.Res.": "house-joint-resolution",
    "H.Con.Res.": "house-concurrent-resolution",
}


def document_url(congress: int, doc_type: str | None, doc_number: str | None) -> str | None:
    if not doc_type or not doc_number:
        return None
    path = DOC_PATHS.get(doc_type)
    if not path:
        return None
    return f"https://www.congress.gov/bill/{congress}th-congress/{path}/{doc_number}"


# the Clerk writes "H R 2913" / "H RES 518" / "S J RES 5"; normalized to
# the dotted forms the Senate files and congress.gov use
LEGIS_TYPES = {
    "HR": "H.R.", "HRES": "H.Res.", "HJRES": "H.J.Res.", "HCONRES": "H.Con.Res.",
    "S": "S.", "SRES": "S.Res.", "SJRES": "S.J.Res.", "SCONRES": "S.Con.Res.",
}


def normalize_legis_num(raw: str | None) -> str | None:
    if not raw:
        return None
    parts = raw.split()
    if not parts or not parts[-1].isdigit():
        return None
    kind = LEGIS_TYPES.get("".join(parts[:-1]).upper())
    return f"{kind} {int(parts[-1])}" if kind else None


def parse_house_date(raw: str) -> str:
    """'3-Jun-2026' -> '2026-06-03'."""
    return datetime.strptime(raw, "%d-%b-%Y").date().isoformat()


def import_roster(conn, data_dir: Path) -> None:
    people = json.loads((data_dir / "legislators-current.json").read_text(encoding="utf-8"))
    rows = []
    for p in people:
        term = p["terms"][-1]
        if term["state"] != "WI":
            continue
        rows.append(
            (
                p["id"]["bioguide"],
                p["id"].get("lis"),
                p["name"]["official_full"],
                slugify(p["name"]["official_full"]),
                term["party"],
                "senate" if term["type"] == "sen" else "house",
                term.get("district"),
                term["start"],
                term["end"],
            )
        )
    if len(rows) != 10:
        raise SystemExit(f"federal roster: expected 10 WI members, found {len(rows)}")
    conn.executemany(
        "INSERT INTO federal_members VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )


def import_votes(conn, data_dir: Path) -> tuple[int, int]:
    votes = records = 0
    vote_file = re.compile(r"^vote_\d+_\d+_\d+\.xml$")
    for path in sorted(p for p in (data_dir / "senate").iterdir() if vote_file.match(p.name)):
        root = ET.parse(path).getroot()
        congress = int(text(root.find("congress")))
        session = int(text(root.find("session")))
        number = int(text(root.find("vote_number")))
        vote_id = f"s{congress}-{session}-{number}"
        date = parse_date(text(root.find("vote_date")))
        count = root.find("count")
        yeas = int(text(count.find("yeas")) or 0)
        nays = int(text(count.find("nays")) or 0)
        doc = root.find("document")
        doc_type = text(doc.find("document_type")) if doc is not None else None
        doc_number = text(doc.find("document_number")) if doc is not None else None
        source_url = (
            "https://www.senate.gov/legislative/LIS/roll_call_votes/"
            f"vote{congress}{session}/vote_{congress}_{session}_{number:05d}.xml"
        )
        conn.execute(
            "INSERT INTO federal_votes VALUES (?, ?, ?, 'senate', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                vote_id, congress, session, number, date,
                text(root.find("vote_question_text")) or text(root.find("question")),
                text(root.find("vote_result")),
                text(root.find("vote_title")),
                yeas, nays,
                text(root.find("majority_requirement")),
                f"{doc_type} {doc_number}" if doc_type and doc_number else None,
                source_url,
            ),
        )
        # impeachment trials record Guilty / Not Guilty; the Senate's own
        # count block files them under yeas and nays respectively
        yea_set = YEA_CASTS
        nay_set = NAY_CASTS
        counted = {"yea": 0, "nay": 0}
        wi = 0
        member_rows = []
        for m in root.findall("members/member"):
            cast = text(m.find("vote_cast"))
            state = text(m.find("state"))
            member_rows.append(
                (
                    vote_id,
                    text(m.find("lis_member_id")),
                    text(m.find("last_name")),
                    text(m.find("party")),
                    state,
                    cast,
                )
            )
            if cast in yea_set:
                counted["yea"] += 1
            elif cast in nay_set:
                counted["nay"] += 1
            if state == "WI":
                wi += 1
        # the same reconciliation the state importer enforces: the stated
        # tally and the counted positions must agree, or the run dies
        if counted["yea"] != yeas or counted["nay"] != nays:
            raise SystemExit(
                f"{vote_id}: stated {yeas}-{nays} but counted "
                f"{counted['yea']}-{counted['nay']}"
            )
        if wi != 2:
            raise SystemExit(f"{vote_id}: expected 2 WI senators, found {wi}")
        conn.executemany(
            "INSERT INTO federal_vote_records VALUES (?, ?, ?, ?, ?, ?)", member_rows
        )
        votes += 1
        records += len(member_rows)
    return votes, records


YEA_CASTS = {"Yea", "Aye", "Guilty"}
NAY_CASTS = {"Nay", "No", "Not Guilty"}


def import_house_votes(conn, data_dir: Path) -> tuple[int, int, int]:
    votes = records = vacated = 0
    house_dir = data_dir / "house"
    if not house_dir.is_dir():
        return 0, 0, 0
    for path in sorted(house_dir.glob("roll_*.xml")):
        root = ET.parse(path).getroot()
        md = root.find("vote-metadata")
        # a vacated vote (e.g. 2011 roll 484, "vacated by unanimous
        # consent") has no recorded positions and no question or result:
        # the official record itself declares it void, so there is
        # nothing to attribute and nothing honest to display
        if not root.findall("vote-data/recorded-vote"):
            vacated += 1
            continue
        congress = int(text(md.find("congress")))
        session = int(text(md.find("session"))[0])  # "2nd" -> 2
        number = int(text(md.find("rollcall-num")))
        vote_id = f"h{congress}-{session}-{number}"
        date = parse_house_date(text(md.find("action-date")))
        totals = md.find("vote-totals/totals-by-vote")
        stated_yeas = int(text(totals.find("yea-total")) or 0) if totals is not None else None
        stated_nays = int(text(totals.find("nay-total")) or 0) if totals is not None else None

        counted_yea = counted_nay = 0
        wi_rows = []
        for rv in root.findall("vote-data/recorded-vote"):
            leg = rv.find("legislator")
            cast = text(rv.find("vote"))
            if cast in YEA_CASTS:
                counted_yea += 1
            elif cast in NAY_CASTS:
                counted_nay += 1
            if leg.get("state") == "WI":
                wi_rows.append(
                    (vote_id, leg.get("name-id"), leg.text or leg.get("sort-field"),
                     leg.get("party"), "WI", cast)
                )
        # Speaker elections and quorum calls carry no yea/nay totals; every
        # ordinary vote's stated totals must match the counted positions
        if stated_yeas is not None and (counted_yea != stated_yeas or counted_nay != stated_nays):
            raise SystemExit(
                f"{vote_id}: stated {stated_yeas}-{stated_nays} but counted "
                f"{counted_yea}-{counted_nay}"
            )
        if not 1 <= len(wi_rows) <= 10:
            raise SystemExit(f"{vote_id}: {len(wi_rows)} WI members on the roll")
        conn.execute(
            "INSERT INTO federal_votes VALUES (?, ?, ?, 'house', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                vote_id, congress, session, number, date,
                text(md.find("vote-question")),
                text(md.find("vote-result")),
                text(md.find("vote-desc")) or text(md.find("vote-question")),
                stated_yeas if stated_yeas is not None else counted_yea,
                stated_nays if stated_nays is not None else counted_nay,
                text(md.find("vote-type")),
                normalize_legis_num(text(md.find("legis-num"))),
                f"https://clerk.house.gov/evs/{date[:4]}/roll{number:03d}.xml",
            ),
        )
        conn.executemany(
            "INSERT INTO federal_vote_records VALUES (?, ?, ?, ?, ?, ?)", wi_rows
        )
        votes += 1
        records += len(wi_rows)
    return votes, records, vacated


def run(data_dir: Path, db_path: Path) -> int:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        DROP TABLE IF EXISTS federal_vote_records;
        DROP TABLE IF EXISTS federal_votes;
        DROP TABLE IF EXISTS federal_members;
        CREATE TABLE federal_members (
            bioguide   TEXT PRIMARY KEY,
            lis_id     TEXT,           -- senators only
            name       TEXT NOT NULL,
            slug       TEXT NOT NULL UNIQUE,
            party      TEXT NOT NULL,
            chamber    TEXT NOT NULL CHECK (chamber IN ('senate', 'house')),
            district   INTEGER,        -- house only
            term_start TEXT NOT NULL,
            term_end   TEXT NOT NULL
        );
        CREATE TABLE federal_votes (
            id                   TEXT PRIMARY KEY,  -- s119-2-231
            congress             INTEGER NOT NULL,
            session              INTEGER NOT NULL,
            chamber              TEXT NOT NULL,
            number               INTEGER NOT NULL,
            date                 TEXT NOT NULL,
            question             TEXT,
            result               TEXT,
            title                TEXT,
            yeas                 INTEGER NOT NULL,
            nays                 INTEGER NOT NULL,
            majority_requirement TEXT,
            document             TEXT,  -- 'S. 5271' when the vote has one
            source_url           TEXT NOT NULL
        );
        CREATE TABLE federal_vote_records (
            vote_id   TEXT NOT NULL REFERENCES federal_votes (id),
            -- LIS id for senate rows, bioguide for house rows
            member_id TEXT NOT NULL,
            last_name     TEXT NOT NULL,
            party         TEXT,
            state         TEXT NOT NULL,
            vote_cast     TEXT NOT NULL
        );
        CREATE INDEX idx_federal_records_vote ON federal_vote_records (vote_id);
        CREATE INDEX idx_federal_records_state ON federal_vote_records (state);
        """
    )
    import_roster(conn, data_dir)
    votes, records = import_votes(conn, data_dir)
    hvotes, hrecords, vacated = import_house_votes(conn, data_dir)
    conn.commit()
    conn.close()
    print(
        f"federal: 10 WI members, {votes} senate votes ({records} positions), "
        f"{hvotes} house votes ({hrecords} WI positions, {vacated} vacated skipped)"
    )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    return run(Path(argv[0]), Path(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
