"""Bulk exports: per-session CSVs + a provenance-filtered SQLite snapshot.

Written to data/exports/ (NOT the site tree — large files publish to GitHub
Releases so the site origin never serves them; plan §11). `package` turns
them into the release assets deploy.yml publishes:

  python -m dataproducts.bulk <exports_dir> <release_dir>

The SQLite snapshot is a copy with LegiScan rows and all Eye on Lobbying
registrations deleted, individual donors' identities cleared, and VACUUMed.
Private archived records must not be recoverable from the downloadable
file's free pages.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import shutil
import sqlite3
import sys
import zipfile
from pathlib import Path

from dataproducts import queries

CSV_TABLES = {
    "bills": f"SELECT * FROM bills WHERE {queries.EXPORTABLE} AND session_id = ?",
    "actions": (
        "SELECT a.* FROM actions a JOIN bills b ON b.id = a.bill_id"
        f" WHERE {queries.exportable('b.')} AND b.session_id = ?"
    ),
    "sponsorships": (
        "SELECT s.* FROM sponsorships s JOIN bills b ON b.id = s.bill_id"
        f" WHERE {queries.exportable('b.')} AND b.session_id = ?"
    ),
    "vote_events": (
        "SELECT e.* FROM vote_events e JOIN bills b ON b.id = e.bill_id"
        f" WHERE {queries.exportable('e.')} AND {queries.exportable('b.')}"
        " AND b.session_id = ?"
    ),
    "vote_records": (
        "SELECT r.* FROM vote_records r"
        " JOIN vote_events e ON e.id = r.vote_event_id"
        " JOIN bills b ON b.id = e.bill_id"
        f" WHERE {queries.exportable('e.')} AND {queries.exportable('b.')}"
        " AND b.session_id = ?"
    ),
}


# every table that references bills or vote_events
BILL_CHILDREN = (
    "actions", "sponsorships", "bill_subjects", "bill_documents", "bill_versions",
    "bill_companions",
    "ballot_measures", "vote_events", "vote_records", "lobbying_interests",
)


def _dump_csv(cursor: sqlite3.Cursor, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([d[0] for d in cursor.description])
        writer.writerows(cursor)


def export_csvs(conn: sqlite3.Connection, exports_dir: Path) -> int:
    files = 0
    for session in queries.sessions(conn):
        session_dir = exports_dir / session["id"]
        session_dir.mkdir(parents=True, exist_ok=True)
        for table, query in CSV_TABLES.items():
            cursor = conn.execute(query, (session["id"],))
            _dump_csv(cursor, session_dir / f"{table}.csv")
            files += 1
    # people are session-independent
    _dump_csv(conn.execute("SELECT * FROM people"), exports_dir / "people.csv")
    return files + 1


def export_sqlite(db_path: Path, exports_dir: Path) -> Path:
    exports_dir.mkdir(parents=True, exist_ok=True)
    snapshot = exports_dir / "wi-filtered.sqlite"
    shutil.copyfile(db_path, snapshot)
    conn = sqlite3.connect(snapshot)
    with conn:
        # Eye on Lobbying disallows collection. Retain its archive privately,
        # but do not publish even previously collected registrations.
        conn.execute("DELETE FROM lobbying_interests")
        legiscan_bills = "(SELECT id FROM bills WHERE source = 'legiscan')"
        # an openstates roll call on a legiscan bill goes with its bill
        withheld_events = (
            "(SELECT id FROM vote_events WHERE source = 'legiscan'"
            f" OR bill_id IN {legiscan_bills})"
        )
        conn.execute(f"DELETE FROM vote_records WHERE vote_event_id IN {withheld_events}")
        conn.execute(f"DELETE FROM vote_events WHERE id IN {withheld_events}")
        for table in ("actions", "sponsorships", "bill_subjects", "bill_documents",
                      "bill_versions"):
            if queries.has_table(conn, table):
                conn.execute(f"DELETE FROM {table} WHERE bill_id IN {legiscan_bills}")  # noqa: S608
        conn.execute(
            f"DELETE FROM bill_companions WHERE bill_id IN {legiscan_bills}"
            f" OR companion_bill_id IN {legiscan_bills}"
        )
        conn.execute(
            f"DELETE FROM ballot_measures WHERE bill_id IN {legiscan_bills}"
            f" OR first_bill_id IN {legiscan_bills}"
        )
        conn.execute("DELETE FROM bills WHERE source = 'legiscan'")
        conn.execute("DELETE FROM elections WHERE source = 'legiscan'")
        # Individual donors appear only in aggregate (README mandate 5): the
        # receipt stays so totals still add up; who gave it does not.
        conn.execute(
            "UPDATE contributions SET from_name = NULL, from_entity_id = NULL,"
            f" occupation = NULL WHERE NOT {queries.named_donor('from_type')}"
        )
        for table in ("cf_transactions", "state_campaign_transactions"):
            conn.execute(
                f"UPDATE {table} SET other_name = NULL, other_entity_id = NULL"  # noqa: S608
                f" WHERE NOT {queries.named_donor('other_type')}"
            )
    conn.execute("VACUUM")
    remaining = conn.execute(
        "SELECT (SELECT COUNT(*) FROM bills WHERE source='legiscan')"
        " + (SELECT COUNT(*) FROM vote_events WHERE source='legiscan')"
        " + (SELECT COUNT(*) FROM elections WHERE source='legiscan')"
        " + (SELECT COUNT(*) FROM lobbying_interests)"
        " + (SELECT COUNT(*) FROM contributions WHERE from_name IS NOT NULL"
        f" AND NOT {queries.named_donor('from_type')})"
        " + (SELECT COUNT(*) FROM cf_transactions WHERE other_name IS NOT NULL"
        f" AND NOT {queries.named_donor('other_type')})"
    ).fetchone()[0]
    # scoped to what the deletes above touch, so an unrelated pre-existing
    # orphan elsewhere can't fail the export
    orphans = [
        row
        for table in BILL_CHILDREN
        if queries.has_table(conn, table)
        for row in conn.execute(f"PRAGMA foreign_key_check({table})")
    ]
    conn.close()
    if remaining:
        raise RuntimeError(f"provenance filter failed: {remaining} withheld rows remain")
    if orphans:
        raise RuntimeError(f"provenance filter left rows pointing at withheld ones: {orphans[:5]}")
    return snapshot


def build_bulk(conn: sqlite3.Connection, db_path: Path, exports_dir: Path) -> int:
    files = export_csvs(conn, exports_dir)
    export_sqlite(db_path, exports_dir)
    return files + 1


RELEASE_README = """\
Badger Politics bulk downloads
==============================

badger-politics-csv.zip  one folder per legislative session (bills, actions,
                         sponsorships, vote_events, vote_records) and people.csv
wi-filtered.sqlite.gz    the site's whole SQLite database, filtered as below;
                         its tables are described in pipeline/importer/schema.sql
SHA256SUMS               checksums: sha256sum --check SHA256SUMS

The newest files are always at the same address:
  https://github.com/uprightsleepy/badger-politics/releases/latest/download/<file>

Left out: rows that came from LegiScan, and every Eye on Lobbying
registration. Individual campaign donors appear only in aggregate: their
receipts keep the amount, date and recipient, but no name, occupation or
filer id.

The records are Wisconsin public records (the Legislature, the Elections
Commission, the Ethics Commission's campaign finance system, city clerks) and
U.S. government works (Senate and House roll calls), each row linked to or
traceable to its official source. Check a figure against that source before
relying on it. The code that builds these files is Apache-2.0:
https://github.com/uprightsleepy/badger-politics

Badger Politics is an independent project, not affiliated with the State of
Wisconsin.
"""

# GitHub refuses release assets of 2 GiB or more
RELEASE_ASSET_LIMIT = 2 * 1024**3


def package(exports_dir: Path, release_dir: Path) -> list[Path]:
    """Release assets from build_bulk's output, plus their SHA256SUMS."""
    release_dir.mkdir(parents=True, exist_ok=True)
    csv_zip = release_dir / "badger-politics-csv.zip"
    with zipfile.ZipFile(csv_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(exports_dir.rglob("*.csv")):
            zf.write(path, path.relative_to(exports_dir).as_posix())
    sqlite_gz = release_dir / "wi-filtered.sqlite.gz"
    with (exports_dir / "wi-filtered.sqlite").open("rb") as src, sqlite_gz.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
    readme = release_dir / "README.txt"
    readme.write_text(RELEASE_README, encoding="utf-8")
    sums = []
    for path in (csv_zip, sqlite_gz, readme):
        if path.stat().st_size >= RELEASE_ASSET_LIMIT:
            raise RuntimeError(f"{path.name} is too large for a GitHub release asset")
        with path.open("rb") as fh:
            sums.append(f"{hashlib.file_digest(fh, 'sha256').hexdigest()}  {path.name}\n")
    (release_dir / "SHA256SUMS").write_text("".join(sums), encoding="utf-8")
    return [csv_zip, sqlite_gz, readme, release_dir / "SHA256SUMS"]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Package bulk exports as release assets.")
    parser.add_argument("exports_dir", type=Path)
    parser.add_argument("release_dir", type=Path)
    ns = parser.parse_args(argv)
    for path in package(ns.exports_dir, ns.release_dir):
        print(f"{path.name}: {path.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
