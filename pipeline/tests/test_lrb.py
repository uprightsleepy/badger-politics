"""LRB analysis extraction: where the analysis stops."""

from importer.enrich_lrb import extract_analysis

ANALYSIS = (
    "This bill allows minors who are 12 and 13 years of age to provide caddy"
    " services without being employed by a golf course."
)


def page(*lines: str) -> str:
    """A bill-text page whose analysis is split across source lines, the way
    docs.legis wraps it."""
    body = "".join(f"<div>{line}</div>" for line in lines)
    return f"<html><body><p>Analysis by the Legislative Reference Bureau</p>{body}</body></html>"


def test_stops_before_boilerplate_split_across_lines():
    # the pointer to the fiscal estimate wraps mid-phrase, so no single line
    # contains it whole — the real docs.legis shape (2019 AB 699)
    html = page(
        ANALYSIS,
        "For further information see the",
        "state",
        "fiscal estimate, which will be printed as an appendix to this bill.",
    )
    assert extract_analysis(html) == ANALYSIS


def test_stops_before_boilerplate_on_one_line():
    html = page(
        ANALYSIS,
        "For further information see the state fiscal estimate, which will be"
        " printed as an appendix to this bill.",
    )
    assert extract_analysis(html) == ANALYSIS


def test_local_and_combined_boilerplate_variants():
    for variant in ("local", "state and local"):
        html = page(ANALYSIS, "For further information see the", variant,
                    "fiscal estimate.")
        assert extract_analysis(html) == ANALYSIS, variant


def test_stops_at_enacting_clause():
    html = page(
        ANALYSIS,
        "The people of the state of Wisconsin, represented in senate and",
        "assembly, do enact as follows:",
        "SECTION 1. 103.78 of the statutes is amended to read:",
    )
    assert extract_analysis(html) == ANALYSIS


def test_no_analysis_section_returns_none():
    html = "<html><body><p>Some other document entirely.</p></body></html>"
    assert extract_analysis(html) is None


def test_stops_before_resolution_body():
    # joint resolutions have no enacting clause; their text begins at the
    # document's own numbering marker (2025 SJR 2)
    html = page(
        "EXPLANATION OF PROPOSAL",
        ANALYSIS,
        "SJR2,2,4",
        "Whereas, the 2023 legislature in regular session considered a proposed",
        "Section 1m of article III of the constitution is created to read:",
    )
    assert extract_analysis(html) == f"EXPLANATION OF PROPOSAL\n{ANALYSIS}"


def test_marker_pattern_does_not_trip_on_prose():
    # a lowercase or mid-line lookalike must not terminate the analysis
    html = page(ANALYSIS, "The bill amends ch. 100, s. 12 of the statutes.",
                "For further information see the state fiscal estimate.")
    got = extract_analysis(html)
    assert "amends ch. 100" in got
