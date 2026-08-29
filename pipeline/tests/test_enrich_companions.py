"""The See Also parser against the page shapes docs.legis actually serves."""

from importer.enrich_companions import extract_companions, norm_identifier

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
