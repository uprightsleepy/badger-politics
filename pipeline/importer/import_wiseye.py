"""Match archived WisconsinEye recordings to hearings.

Usage: python -m importer.import_wiseye <videos.json> <sqlite_path>

The whole design is the accuracy rule: a hearing links to a recording
only when exactly one video exists on that hearing's date whose
normalized title names the hearing's committee (with any leading
chamber word agreeing). Zero or several candidates: no link.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from importer.committees import normalize_name

CHAMBER_WORDS = {"assembly": "lower", "senate": "upper"}


def parse_title(title: str) -> tuple[str | None, str]:
    """'Assembly Committee on Health' -> ('lower', 'health')."""
    words = re.sub(r"[^a-z0-9]+", " ", title.lower()).split()
    hint = None
    if words and words[0] in CHAMBER_WORDS:
        hint = CHAMBER_WORDS[words[0]]
        words = words[1:]
    return hint, normalize_name(" ".join(words))


def run(videos_path: Path, db_path: Path) -> int:
    videos = json.loads(videos_path.read_text(encoding="utf-8"))
    by_date: dict[str, list[dict]] = defaultdict(list)
    for v in videos:
        by_date[v["date"]].append(v)

    conn = sqlite3.connect(db_path)
    committees = {
        row[0]: (row[1], row[2])
        for row in conn.execute("SELECT id, name, chamber FROM committees")
    }
    linked = ambiguous = 0
    with conn:
        conn.execute("DELETE FROM hearing_videos")
        for hearing_id, date, committee_id in conn.execute(
            "SELECT id, date, committee_id FROM hearings"
            " WHERE date IS NOT NULL AND committee_id IS NOT NULL"
        ).fetchall():
            name, chamber = committees.get(committee_id, (None, None))
            if name is None:
                continue
            key = normalize_name(name)
            candidates = []
            for v in by_date.get(date, []):
                hint, video_key = parse_title(v["title"])
                if video_key != key:
                    continue
                if hint and chamber and hint != chamber:
                    continue
                candidates.append(v)
            urls = {c["url"] for c in candidates}
            if len(urls) == 1:
                v = candidates[0]
                conn.execute(
                    "INSERT INTO hearing_videos (hearing_id, url, title) VALUES (?, ?, ?)",
                    (hearing_id, v["url"], v["title"]),
                )
                linked += 1
            elif len(urls) > 1:
                ambiguous += 1
    conn.close()
    note = f", {ambiguous} ambiguous (no link)" if ambiguous else ""
    print(f"hearing_videos: {linked} linked{note}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("videos_path", type=Path)
    parser.add_argument("db_path", type=Path)
    ns = parser.parse_args(argv)
    return run(ns.videos_path, ns.db_path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
