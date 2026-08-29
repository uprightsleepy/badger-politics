"""Import U.S. Senate roll calls and the Wisconsin federal delegation.

Reads the XML mirrored by scraper.fetch_federal_votes. Attribution is by
LIS member id, which the Senate's own files carry on every position --
there is no name matching anywhere in this module. The full chamber is
stored (party context needs it); Wisconsin's rows are just the ones
where state = 'WI'.

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


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


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
        counted = {"Yea": 0, "Nay": 0}
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
            if cast in counted:
                counted[cast] += 1
            if state == "WI":
                wi += 1
        # the same reconciliation the state importer enforces: the stated
        # tally and the counted positions must agree, or the run dies
        if counted["Yea"] != yeas or counted["Nay"] != nays:
            raise SystemExit(
                f"{vote_id}: stated {yeas}-{nays} but counted "
                f"{counted['Yea']}-{counted['Nay']}"
            )
        if wi != 2:
            raise SystemExit(f"{vote_id}: expected 2 WI senators, found {wi}")
        conn.executemany(
            "INSERT INTO federal_vote_records VALUES (?, ?, ?, ?, ?, ?)", member_rows
        )
        votes += 1
        records += len(member_rows)
    return votes, records


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
            vote_id       TEXT NOT NULL REFERENCES federal_votes (id),
            lis_member_id TEXT NOT NULL,
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
    conn.commit()
    conn.close()
    print(f"federal: 10 WI members, {votes} senate votes, {records} positions")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    return run(Path(argv[0]), Path(argv[1]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
