"""The ballot-access report is read row by row: wrapped office and party
names are rejoined, and a row the parser cannot place, or an office whose
subtotal disagrees, stops the run instead of dropping a candidate."""

import pymupdf
import pytest

from importer.wec_pdf import parse_tracking

X = {"receipt": 99, "name": 120, "party": 267, "campaign": 338, "status": 706}


def report(tmp_path, congress_rows, subtotal=None):
    """100 one-candidate Assembly offices (the drift floor) plus one House race."""
    rows = [[(9, "Office"), (40, ":"), (120, "REPRESENTATIVE IN CONGRESS DISTRICT"),
             (409, "Incumbent:"), (492, "Bryan Steil")], [(120, "1")], *congress_rows,
            [(39, "Office Subtotal"), (113, ":"), (120, str(subtotal or 2))]]
    for d in range(1, 101):
        rows += [[(9, "Office"), (40, ":"), (120, f"REPRESENTATIVE TO THE ASSEMBLY DISTRICT {d}")],
                 [(99, "100"), (120, f"Pat Seat{d}"), (267, "Democratic"), (706, "Approve")],
                 [(39, "Office Subtotal"), (113, ":"), (120, "1")]]
    doc = pymupdf.open()
    per_page = 40
    pages = [rows[i:i + per_page] for i in range(0, len(rows), per_page)]
    for n, chunk in enumerate(pages, 1):
        page = doc.new_page(width=800, height=40 * 14 + 100)
        page.insert_text((9, 20), "Candidate Tracking by Office" if n == 1 else "2026 General")
        page.insert_text((X["receipt"], 34), "Receipt #")
        page.insert_text((X["party"], 34), "Party")
        page.insert_text((X["campaign"], 34), "Campaign")
        page.insert_text((X["status"], 34), "Recommended")
        for i, row in enumerate(chunk):
            for x, text in row:
                page.insert_text((x, 50 + 14 * i), text, fontsize=8)
        page.insert_text((9, 40 * 14 + 90), f"Printed 6/8/2026 Page {n} of {len(pages)}",
                         fontsize=8)
    path = tmp_path / "report.pdf"
    doc.save(path)
    return path


STEIL = [(99, "244"), (120, "Bryan"), (149, "Steil"), (267, "Republican"), (706, "Approve")]
FOLLMER = [(120, "Adam"), (149, "Follmer"), (267, "The"), (287, "Common"), (706, "Deny")]


def test_wrapped_district_and_party_rejoin_their_rows(tmp_path):
    records = parse_tracking(report(tmp_path, [FOLLMER, [(267, "Class")], STEIL]))
    house = [r for r in records if "CONGRESS" in r["office"]]
    assert [(r["office"], r["candidate"], r["party"]) for r in house] == [
        ("REPRESENTATIVE IN CONGRESS DISTRICT 1", "Adam Follmer", "The Common Class"),
        ("REPRESENTATIVE IN CONGRESS DISTRICT 1", "Bryan Steil", "Republican")]


@pytest.mark.parametrize("rows,subtotal,match", [
    ([FOLLMER, [(409, "stray note")], STEIL], None, "unparsed tracking row"),
    ([FOLLMER, STEIL], 3, "subtotal 3, parsed 2"),
], ids=["unplaced-row", "subtotal"])
def test_rows_the_parser_cannot_account_for_stop_the_run(tmp_path, rows, subtotal, match):
    with pytest.raises(RuntimeError, match=match):
        parse_tracking(report(tmp_path, rows, subtotal))
