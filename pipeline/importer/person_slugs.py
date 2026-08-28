"""Generate the permanent person -> URL slug map.

Legislator URLs used the raw OCD uuid, which tells a reader nothing and
which Google's URL guidance advises against. Names are unique across all
346 people on record, so a name slug is unambiguous today.

The map is committed rather than derived at build time on purpose. A slug
has to outlive the name that produced it: if a member changes their name,
the record keeps its URL and the site keeps working. Regenerating only
ever *adds* entries; an existing id keeps whatever slug it was first
given. Run after an import that introduces new people:

    uv run python -m importer.person_slugs data/wi.sqlite \
        site/src/data/person-slugs.json
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path


def slugify(name: str) -> str:
    """'André Jacque' -> 'andre-jacque'. Accents fold to ASCII so the URL
    survives being typed, pasted and logged anywhere."""
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_only.lower())).strip("-")


def build(conn: sqlite3.Connection, existing: dict[str, str]) -> dict[str, str]:
    """Existing entries are never rewritten; only new people get a slug."""
    out = dict(existing)
    taken = set(out.values())
    rows = conn.execute("SELECT id, name FROM people ORDER BY name, id").fetchall()
    for person_id, name in rows:
        if person_id in out:
            continue
        base = slugify(name) or person_id.split("/")[-1]
        slug = base
        n = 2
        # two people sharing a name is possible in future even though none
        # do today; the second gets a numbered slug rather than a collision
        while slug in taken:
            slug = f"{base}-{n}"
            n += 1
        out[person_id] = slug
        taken.add(slug)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    db_path, out_path = Path(argv[0]), Path(argv[1])
    existing: dict[str, str] = {}
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
    conn = sqlite3.connect(db_path)
    mapping = build(conn, existing)
    conn.close()
    added = len(mapping) - len(existing)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(dict(sorted(mapping.items())), indent=0, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"person slugs: {len(mapping)} total, {added} added, {len(existing)} kept")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
