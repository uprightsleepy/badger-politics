"""Build every static data product from the SQLite database.

Usage: python -m dataproducts.build <sqlite_path> <site_public_dir>
                                    [--exports-dir DIR]

Generates the JSON API tree, Atom feeds, and iCal files into the site's
public directory (deployed with the site), and bulk CSV/SQLite exports into
data/exports/ (published via GitHub Releases in Phase 6).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dataproducts import queries
from dataproducts.api import build_api
from dataproducts.bulk import build_bulk
from dataproducts.feeds import build_feeds
from dataproducts.ical import build_ical


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("site_public", type=Path)
    parser.add_argument("--exports-dir", type=Path)
    ns = parser.parse_args(argv)
    exports_dir = ns.exports_dir or ns.db_path.parent / "exports"

    conn = queries.connect(ns.db_path)
    hearings = queries.hearings(conn)  # shared by feeds and ical
    api_files = build_api(conn, ns.site_public)
    feed_files = build_feeds(conn, ns.site_public, hearings)
    ical_files = build_ical(conn, ns.site_public, hearings)
    bulk_files = build_bulk(conn, ns.db_path, exports_dir)
    conn.close()

    print(
        f"dataproducts: {api_files} api files, {feed_files} feeds,"
        f" {ical_files} calendars -> {ns.site_public}"
    )
    print(f"dataproducts: {bulk_files} bulk exports -> {exports_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
