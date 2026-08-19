"""Backfill fallback: LegiScan datasets -> SQLite (local use only).

Usage: python -m importer.import_legiscan <session> <sqlite_path>

Implemented in Phase 4, and only for sessions the self-scrape backfill cannot
cover. Rows are written with source='legiscan' and are display-only: they must
never appear in any bulk export or the static JSON API (ToS boundary).
"""

import sys


def main(argv: list[str]) -> int:
    raise NotImplementedError("Phase 4: LegiScan backfill fallback not yet implemented")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
