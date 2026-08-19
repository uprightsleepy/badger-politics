"""Import openstates-scrapers JSON output into SQLite.

Usage: python -m importer.import_openstates <scrape_output_dir> <sqlite_path>

Implemented in Phase 1. openstates-scrapers is invoked only as a subprocess
CLI (os-update); its modules are never imported here (GPL boundary).
"""

import sys


def main(argv: list[str]) -> int:
    raise NotImplementedError("Phase 1: importer not yet implemented")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
