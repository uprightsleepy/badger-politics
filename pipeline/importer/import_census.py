"""Load the committed ACS district profile into district_demographics.

Usage: python -m importer.import_census <sqlite_path> [--source PATH]

Figures are stored only when the release tabulates the district map now in
force (CURRENT_MAP, the LTSB maps the site draws). A release on another map
loads nothing, so no page puts one map's people beside another map's lines.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

SOURCE = Path(__file__).with_name("census_acs.json")
CURRENT_MAP = 2024  # 2023 Wis. Act 94, first used in the 2024 elections
SEATS = {"lower": 99, "upper": 33}
CONTROLLED = -555555555  # Census: estimate is controlled, so it has no sampling error


def rows_for(doc: dict) -> list[tuple]:
    rows = []
    for chamber, seats in SEATS.items():
        header, *records = doc["tables"][chamber]
        geo = header[-1]
        found = set()
        for record in records:
            r = dict(zip(header, record, strict=True))
            if r[geo] == "ZZZ":  # Lake Michigan / Superior water: no district
                continue
            district = int(r[geo])
            year = re.search(r"\((\d{4})\)", r["NAME"])
            if not year or year.group(1) != str(doc["map_year"]):
                raise ValueError(f"{r['NAME']!r} is not on the {doc['map_year']} map")
            found.add(district)
            for measure, (est_var, moe_var) in doc["measures"].items():
                estimate, moe = float(r[est_var]), float(r[moe_var])
                if moe == CONTROLLED:
                    moe = 0.0
                if estimate < 0 or moe < 0:
                    raise ValueError(f"{chamber} {district} {measure}: Census marks the value"
                                     f" unavailable ({r[est_var]}, {r[moe_var]})")
                rows.append((chamber, district, doc["acs_year"], doc["map_year"],
                             measure, estimate, moe))
        if found != set(range(1, seats + 1)):
            raise ValueError(f"{chamber}: ACS districts {sorted(found)} are not 1-{seats}")
    return rows


def run(db_path: Path, source: Path = SOURCE) -> int:
    doc = json.loads(source.read_text(encoding="utf-8"))
    rows = rows_for(doc) if doc["map_year"] == CURRENT_MAP else []
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM district_demographics")
        conn.executemany("INSERT INTO district_demographics VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        # what was imported, so the integrity gate knows what to demand
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('census_acs', ?)", (json.dumps(
            {"acs_year": doc["acs_year"], "map_year": doc["map_year"]}),))
    if not rows:
        print(f"census: ACS {doc['acs_year']} describes the {doc['map_year']} map, not the"
              f" {CURRENT_MAP} map; no district figures loaded")
    else:
        print(f"census: ACS {doc['acs_year']}, {len(rows)} figures for 132 districts")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db_path", type=Path)
    parser.add_argument("--source", type=Path, default=SOURCE)
    ns = parser.parse_args(argv)
    return run(ns.db_path, ns.source)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
