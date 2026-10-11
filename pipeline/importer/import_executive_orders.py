"""Load the archived executive-order listing into executive_orders.

Usage: python -m importer.import_executive_orders <archive_dir> <sqlite_path>

The listing comes from scraper.fetch_executive_orders. Each row is an
official link; no order text is stored. A missing, empty or older-format
archive fails the run rather than leaving the table silently empty.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from scraper.fetch_executive_orders import FORMAT

COLUMNS = ("folder", "governor", "year", "number", "title", "date", "url")


def run(archive_dir: Path, db_path: Path) -> int:
    path = archive_dir / "orders.json"
    if not path.exists():
        raise RuntimeError(f"no {path}; run scraper.fetch_executive_orders")
    archive = json.loads(path.read_text(encoding="utf-8"))
    if archive.get("format") != FORMAT or not archive.get("orders"):
        raise RuntimeError(f"{path}: empty or older-format archive; refetch it")
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("DELETE FROM executive_orders")
        conn.executemany(
            f"INSERT INTO executive_orders ({', '.join(COLUMNS)})"  # noqa: S608 - constant
            f" VALUES ({', '.join('?' * len(COLUMNS))})",
            [tuple(order[c] for c in COLUMNS) for order in archive["orders"]],
        )
    count, governors = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT folder) FROM executive_orders").fetchone()
    conn.close()
    print(f"executive_orders: {count} orders across {governors} governors")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_dir", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.archive_dir, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
