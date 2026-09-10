"""FEC cycle summaries and explicitly verified state campaigns of federal members."""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

CAMPAIGNS = json.loads(Path(__file__).with_name("federal_campaigns.json").read_text())
STATE_CAMPAIGNS = {c["entity_id"]: {**c, "bioguide": b} for b, c in CAMPAIGNS.items()}
AMOUNTS = {
    "receipts": 5, "transfers_in": 6, "disbursements": 7, "transfers_out": 8,
    "cash_start": 9, "cash_end": 10, "candidate_contributions": 11,
    "candidate_loans": 12, "other_loans": 13, "candidate_loan_repayments": 14,
    "other_loan_repayments": 15, "debts": 16, "individual_contributions": 17,
    "committee_contributions": 25, "party_contributions": 26,
    "individual_refunds": 28, "committee_refunds": 29,
}


def fec_url(cycle: int) -> str:
    if not 2000 <= cycle <= 2098 or cycle % 2:
        raise ValueError("Expected an even FEC cycle year")
    return f"https://www.fec.gov/files/bulk-downloads/{cycle}/weball{cycle % 100:02d}.zip"


def candidate_ids(roster: list[dict]) -> dict[str, str]:
    result = {}
    members = [p for p in roster if p["terms"][-1]["state"] == "WI"]
    if len(members) != 10:
        raise ValueError("FEC attribution requires all ten Wisconsin federal members")
    for person in members:
        chamber = "S" if person["terms"][-1]["type"] == "sen" else "H"
        ids = [i for i in person["id"].get("fec", []) if i.startswith(chamber)]
        if len(ids) != 1 or not re.fullmatch(r"[HS]\dWI\d{5}", ids[0]) or ids[0] in result:
            raise ValueError(f"Ambiguous FEC identity for {person['id']['bioguide']}")
        result[ids[0]] = person["id"]["bioguide"]
    return result


def cents(raw: str) -> int | None:
    if not raw.strip():
        return None
    try:
        value = Decimal(raw) * 100
        if not value.is_finite() or value != value.to_integral_value():
            raise ValueError("Invalid FEC dollar amount")
        return int(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid FEC dollar amount") from exc


def parse_summary(content: bytes, identities: dict[str, str], cycle: int) -> list[dict]:
    """Keep reported amounts in cents; blanks remain unknown, transfers stay separate."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        files = archive.infolist()
        if len(files) != 1 or files[0].file_size > 20_000_000:
            raise ValueError("Unexpected FEC summary archive")
        text = archive.read(files[0]).decode("utf-8-sig")
    found = {}
    for fields in csv.reader(io.StringIO(text), delimiter="|"):
        if not fields or fields[0] not in identities:
            continue
        if len(fields) != 30 or fields[18] != "WI" or fields[0] in found:
            raise ValueError("Invalid or duplicate FEC candidate summary")
        through = datetime.strptime(fields[27], "%m/%d/%Y").date() if fields[27] else None
        if through and not cycle - 1 <= through.year <= cycle:
            raise ValueError("FEC coverage date outside the file's cycle")
        found[fields[0]] = {
            "candidate_id": fields[0], "bioguide": identities[fields[0]], "cycle": cycle,
            "reported_name": fields[1], "coverage_end": through.isoformat() if through else None,
            **{name: cents(fields[index]) for name, index in AMOUNTS.items()},
        }
    # Missing records are coverage gaps, never manufactured zero-dollar summaries.
    return list(found.values())


def import_summaries(directory: Path, db_path: Path) -> None:
    files = sorted(directory.glob("finance-*.json"))
    if not files:
        raise ValueError("Missing FEC finance archive")
    with sqlite3.connect(db_path) as conn:
        known = {row[0] for row in conn.execute("SELECT bioguide FROM federal_members")}
        columns = ", ".join(f"{name} INTEGER" for name in AMOUNTS)
        conn.execute(f"""CREATE TABLE IF NOT EXISTS federal_finance (
            candidate_id TEXT, bioguide TEXT, cycle INTEGER, reported_name TEXT,
            coverage_end TEXT, {columns}, source_url TEXT, fetched_at TEXT,
            PRIMARY KEY(candidate_id, cycle))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS federal_finance_coverage (
            bioguide TEXT, candidate_id TEXT, cycle INTEGER, fetched_at TEXT,
            PRIMARY KEY(bioguide, cycle))""")
        conn.execute("DELETE FROM federal_finance")
        conn.execute("DELETE FROM federal_finance_coverage")
        for path in files:
            doc = json.loads(path.read_text(encoding="utf-8"))
            cycle = doc["cycle"]
            if doc["source_url"] != fec_url(cycle):
                raise ValueError("Unreviewed FEC archive source")
            datetime.fromisoformat(doc["fetched_at"])
            if path == files[-1] and set(doc["identities"].values()) != known:
                raise ValueError("FEC archive roster differs from imported federal roster")
            for cid, bioguide in doc["identities"].items():
                conn.execute("INSERT INTO federal_finance_coverage VALUES (?, ?, ?, ?)",
                             (bioguide, cid, cycle, doc["fetched_at"]))
            for row in doc["rows"]:
                if (row["cycle"] != cycle
                        or doc["identities"].get(row["candidate_id"]) != row["bioguide"]):
                    raise ValueError("FEC archive identity mismatch")
                if row["coverage_end"]:
                    date.fromisoformat(row["coverage_end"])
                for key in AMOUNTS:
                    if row[key] is not None and type(row[key]) is not int:
                        raise ValueError("FEC archive money must be integer cents")
                keys = ["candidate_id", "bioguide", "cycle", "reported_name", "coverage_end",
                        *AMOUNTS, "source_url", "fetched_at"]
                values = {**row, "source_url": doc["source_url"], "fetched_at": doc["fetched_at"]}
                conn.execute(f"INSERT INTO federal_finance ({', '.join(keys)})"
                             f" VALUES ({', '.join('?' for _ in keys)})",
                             [values[k] for k in keys])


if __name__ == "__main__":
    import sys
    import_summaries(Path(sys.argv[1]), Path(sys.argv[2]))
