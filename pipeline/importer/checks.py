"""Integrity gates run after every import. A failure aborts the deploy.

Usage: python -m importer.checks <sqlite_path>

Implemented in Phase 1. Gates (never weaken one to make a run pass):
- Sum of per-legislator vote_records per event == stored yes/no/nv counts.
- Active-session bill count >= last run's count minus a small tolerance.
- Every vote_records.person_id resolves to a person; unmatched names fail
  the run and are logged.
"""

import sys


def main(argv: list[str]) -> int:
    raise NotImplementedError("Phase 1: integrity checks not yet implemented")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
