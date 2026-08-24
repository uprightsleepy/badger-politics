"""Attach official Capitol office contacts to sitting members.

Usage: python -m importer.import_contacts <contacts_json> <sqlite_path>

Contacts come from scraper.fetch_contacts (docs.legis member pages,
cross-checked against the people files). Office contacts only.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def run(contacts_path: Path, db_path: Path) -> int:
    contacts = json.loads(contacts_path.read_text(encoding="utf-8"))
    conn = sqlite3.connect(db_path)
    updated = 0
    with conn:
        conn.execute(
            "UPDATE people SET email=NULL, office_phone=NULL,"
            " office_address=NULL, contact_url=NULL"
        )
        for c in contacts:
            cur = conn.execute(
                "UPDATE people SET email=?, office_phone=?, office_address=?,"
                " contact_url=? WHERE id=?",
                (c["email"], c["phone"], c["address"], c["source_url"], c["person_id"]),
            )
            updated += cur.rowcount
    conn.close()
    if updated < len(contacts):
        print(
            f"ERROR: only {updated}/{len(contacts)} contacts matched a person",
            file=sys.stderr,
        )
        return 1
    print(f"contacts: {updated} members updated")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contacts_path", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.contacts_path, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
