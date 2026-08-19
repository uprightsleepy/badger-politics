"""Overlay WEC certified candidate lists (CSV) onto the elections table.

Usage: python -m importer.import_wec <wec_csv> <sqlite_path>

Implemented in Phase 2. Fills on_ballot and opponents_json for the active
cycle. WI cycle rules: Assembly = all 99 districts every even year; Senate =
odd districts in midterm years, even districts in presidential years.
"""

import sys


def main(argv: list[str]) -> int:
    raise NotImplementedError("Phase 2: WEC candidate import not yet implemented")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
