"""The See Also parser against the page shapes docs.legis actually serves."""

import json
import sqlite3

import requests

from importer import enrich_companions
from importer.enrich_companions import enrich, extract_companions, norm_identifier

REGULAR = """
<div><h2>See Also</h2>
    <ul class="docLinks">
        <li><p><a href="/2025/proposals/sb997">2025 Senate Bill 997</a>
        - S - Transportation</p></li>
    </ul>
</div>
<div class="propHistory"><h2>History</h2>
<a href="/2025/proposals/ab999">unrelated link outside the block</a></div>
"""

SPECIAL = """
<h2>See Also</h2><ul class="docLinks">
<li><p><a href="/2025/proposals/my6/sb1">May 2026 Special Session
Senate Bill 1</a> - S - Tabled</p></li>
</ul>
"""


def test_extracts_only_the_see_also_block():
    assert extract_companions(REGULAR) == ["SB 997"]


def test_special_session_short_urls():
    assert extract_companions(SPECIAL) == ["SB 1"]


def test_page_without_block_yields_nothing():
    assert extract_companions("<h2>History</h2><ul><li>x</li></ul>") == []


def test_identifier_normalization():
    assert norm_identifier("SB1") == "SB 1"
    assert norm_identifier("ajr045") == "AJR 45"
    assert norm_identifier("SB 997") == "SB 997"


def test_fetch_failure_fails_the_stage_but_keeps_resolved_edges(
    tmp_path, make_db, monkeypatch
):
    db = tmp_path / "wi.sqlite"
    conn = make_db(db)
    conn.execute("INSERT INTO sessions (id, identifier) VALUES ('2025', '2025')")
    scrape = tmp_path / "scrape"
    scrape.mkdir()
    for ident in ("AB 999", "SB 997", "AB 5"):
        slug = ident.replace(" ", "").lower()
        conn.execute(
            "INSERT INTO bills (id, session_id, identifier) VALUES (?, '2025', ?)",
            (f"2025-{slug}", ident),
        )
        (scrape / f"bill_{slug}.json").write_text(json.dumps({
            "legislative_session": "2025", "identifier": ident,
            "sources": [{"url": f"https://docs.legis.wisconsin.gov/2025/proposals/{slug}"}],
        }), encoding="utf-8")
    conn.commit()
    conn.close()

    def page(http, url, cache_dir):
        if url.endswith("ab5"):
            raise requests.HTTPError("503 Server Error")
        return (REGULAR if url.endswith("ab999") else ""), True

    monkeypatch.setattr(enrich_companions, "cached_page", page)
    assert enrich(db, [scrape], None, 0) == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM bill_companions").fetchone()[0] == 2
