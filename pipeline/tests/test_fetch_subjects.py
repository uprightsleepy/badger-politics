"""Index entries belong to the heading their data-path names, however the
continuation pages overlap; headings are kept as printed."""

import json
import sqlite3

import pytest

from importer.import_subjects import run
from scraper.fetch_subjects import blocks, build

P = "/2025/related/subject_index/index"


def heading(slug, text, cls="qsSubject  level2"):
    return (f'<div class="{cls}" data-path="{P}/p/{slug}"   data-cites=\'[]\'>'
            f'<a class="reference" href="/document/subjectindex/{slug}">{slug}</a>{text}</div>')


def entry(slug, n, bill, cls="qsAbstract"):
    return (f'<div class="{cls}" data-path="{P}/p/{slug}/_{n}"   data-cites=\'[]\'>'
            f'Something - <a href="/document/session/2025/REG/{bill}">'
            f"{bill}</a></div>")


def index(*pages):
    merged = {}
    for page in pages:
        merged.update(blocks("".join(page)))
    return merged


def test_entries_repeated_across_overlapping_pages_keep_their_own_heading():
    page1 = [heading("police", "Police, see also Sheriff; Traffic officer"),
             entry("police", 1, "AB1"), entry("police", 2, "SB2"),
             heading("port", "Port"), entry("port", 1, "AB9")]
    # the next page starts back inside Police, before the Port heading
    page2 = [entry("police", 2, "SB2"),
             heading("port", "Port"), entry("port", 1, "AB9"),
             heading("zoning", "Zoning, see Municipality &#8212; Planning")]
    assert build(index(page1, page2), 2025) == {"Police": ["AB 1", "SB 2"], "Port": ["AB 9"]}


def test_printed_heading_replaces_the_url_key_in_every_markup_era():
    old = [heading("banking",
                   '<span class="qs_subjecthead_">Banking, Division of</span>',
                   "qs_subject_ level2"),
           entry("banking", 1, "ab224", "qs_entry_")]
    assert build(index(old), 2025) == {"Banking, Division of": ["AB 224"]}


def test_an_entry_without_its_heading_stops_the_fetch():
    with pytest.raises(RuntimeError, match="entry without a heading"):
        build(index([entry("police", 1, "AB1")]), 2025)


def test_old_archives_stay_out_until_refetched_but_the_current_one_must_be_new(make_db, tmp_path):
    db = tmp_path / "wi.sqlite"
    conn = make_db(db)
    conn.executemany("INSERT INTO sessions (id, identifier) VALUES (?, ?)",
                     [("2023", "2023"), ("2025", "2025")])
    conn.executemany("INSERT INTO bills (id, session_id, identifier, source) VALUES"
                     " (?, ?, ?, 'openstates')", [("2023-ab1", "2023", "AB 1"),
                                                   ("2025-ab1", "2025", "AB 1")])
    conn.commit()
    conn.close()
    archives = tmp_path / "subjects"
    archives.mkdir()
    (archives / "subjects-2023.json").write_text(json.dumps({"lfb": ["AB 1"]}))
    (archives / "subjects-2025.json").write_text(
        json.dumps({"format": 2, "subjects": {"Police": ["AB 1"]}}))
    run(archives, db)
    assert sqlite3.connect(db).execute("SELECT * FROM bill_subjects").fetchall() == [
        ("2025-ab1", "Police")]
    (archives / "subjects-2025.json").write_text(json.dumps({"police": ["AB 1"]}))
    with pytest.raises(RuntimeError, match="not a current subject archive"):
        run(archives, db)
