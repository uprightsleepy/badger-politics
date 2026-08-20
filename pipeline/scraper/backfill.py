"""Historical backfill driver: walk sessions backward until the data breaks.

Usage: python -m scraper.backfill [--sessions ID [ID ...]] [--start-at ID]

For each session (newest -> oldest): scrape bills (archived to
_data/sessions/<slug>/), then run a cumulative import of the current
biennium plus every archived session, then the integrity checks. A session
whose scrape crashes or yields no bills marks the structural floor: the
walk stops and the floor is reported for documentation.

Historical sessions are immutable — each is scraped exactly once; re-running
skips sessions whose archive already contains bills.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
SESSIONS_DIR = PIPELINE_DIR / "_data" / "sessions"
CURRENT_DIR = PIPELINE_DIR / "_data" / "wi"
DB_PATH = PIPELINE_DIR.parent / "data" / "wi.sqlite"

# newest -> oldest; exact scraper identifiers (see scrapers/wi/__init__.py)
WALK = [
    "2023",
    "2021",
    "2019",
    "2017 Regular Session",
    "2015 Regular Session",
    "2013 Regular Session",
    "2011 Regular Session",
    "2009 Regular Session",
]


def slug(identifier: str) -> str:
    return identifier.replace(" ", "-").lower()


def archived_dirs() -> list[Path]:
    if not SESSIONS_DIR.exists():
        return []
    return sorted(
        d for d in SESSIONS_DIR.iterdir() if d.is_dir() and list(d.glob("bill_*.json"))
    )


def run(cmd: list[str]) -> int:
    print(f"+ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=PIPELINE_DIR, check=False).returncode


def cumulative_import() -> int:
    dirs = [str(CURRENT_DIR), *(str(d) for d in archived_dirs())]
    code = run([sys.executable, "-m", "importer.import_openstates", *dirs, str(DB_PATH)])
    if code != 0:
        return code
    return run([sys.executable, "-m", "importer.checks", str(DB_PATH)])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", nargs="+", default=WALK)
    parser.add_argument("--start-at", help="skip sessions before this one in the walk")
    ns = parser.parse_args(argv)
    sessions = list(ns.sessions)
    if ns.start_at:
        sessions = sessions[sessions.index(ns.start_at):]

    for identifier in sessions:
        archive = SESSIONS_DIR / slug(identifier)
        if list(archive.glob("bill_*.json")):
            print(f"=== {identifier}: already archived, skipping scrape ===")
        else:
            print(f"=== {identifier}: scraping ===", flush=True)
            code = run(
                [sys.executable, "-m", "scraper.scrape", "bills", "--session", identifier]
            )
            if code != 0 or not list(archive.glob("bill_*.json")):
                print(
                    f"STRUCTURAL FLOOR: {identifier} failed to scrape"
                    f" (exit {code}). Walk stops here — document this floor.",
                    file=sys.stderr,
                )
                return 2
        print(f"=== {identifier}: cumulative import + checks ===", flush=True)
        code = cumulative_import()
        if code != 0:
            print(
                f"IMPORT/CHECKS FAILED after adding {identifier} — fix the"
                " importer (roster/titles) and re-run; the archive is kept.",
                file=sys.stderr,
            )
            return code
    print("backfill walk complete")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
