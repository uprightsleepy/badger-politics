"""A ballot question is shown only when the notice, both enrolled resolutions
and the legislative record all agree; any disagreement stops the run."""

import pytest

from importer.import_amendments import ENROLLED, measures

QUESTION = ("Partial veto. Shall section 10 (1) (c) of article V of the constitution be amended"
            " to prohibit the governor from creating any tax?")
NOTICE = f"""TYPE A NOTICE
NOTICE IS HEREBY GIVEN, that at an election to be held in the several towns, on Tuesday,
November 3, 2026, the following questions will be submitted to a vote of the people:
QUESTION 1: “{QUESTION}”
This referendum ballot is a result of 2025 Senate Joint Resolution 116. The text of the joint
resolutions can be found at https://docs.legis.wisconsin.gov/2025/proposals."""


def div(cls, inner):
    return f'<div class="{cls}" data-path="/x">{inner}</div>'


def amendment(cls_action, cls_treat, inserted="or increase any tax", note="provision"):
    return (div(cls_action, '<a class="reference" href="#">SJR116,1</a><span>Section 1. </span>'
                '<span>Section 10 (1) (c) of article V of the constitution is amended to read:'
                '</span>')
            + div(cls_treat, '<span>[Article V] Section 10 (1) (c) the governor may not </span>'
                  '<span style="text-decoration: line-through">and</span>'
                  f'<span style="text-decoration: underline">{inserted}</span><span>.</span>')
            + div(cls_action, f"<span>Section 2. Numbering of new {note}. The chief shall"
                  " number it.</span>"))


def second(question=QUESTION, first="2023 Assembly Joint Resolution 112, which became"
           " 2023 Enrolled Joint Resolution 16", **text):
    return "<html><body>" + "".join([
        div("qsx_catalog", "To amend s. 10; relating to: the partial veto (second consideration)."),
        div("qstext_con2", f"Whereas, the 2023 legislature in regular session considered a proposed"
            f" amendment to the constitution in {first}, and agreed to it:"),
        amendment("qsaction_con_amend", "qstext_treat", **text),
        div("qsresolve_con2", "Resolved, That the foregoing proposed amendment be submitted to a"
            " vote of the people at the election to be held on the first Tuesday of"
            " November 2026;"),
        div("qsresolve_con2", f"Question 1 : “ {question}”"),
    ]) + "</body></html>"


def first_page(**text):
    return "<html><body>" + "".join([
        div("qs_x_catalog_", "To amend s. 10; relating to: partial veto (first consideration)."),
        div("qs_resolve_concur_", "Resolved by the assembly, the senate concurring, That:"),
        amendment("qs_action_con_amend_  level1", "qs_text_treat_", **text),
    ]) + "</body></html>"


@pytest.fixture
def conn(make_db):
    db = make_db(":memory:")
    db.executemany("INSERT INTO sessions (id, identifier) VALUES (?, ?)",
                   [("2023", "2023"), ("2025", "2025")])
    db.executemany(
        "INSERT INTO bills (id, session_id, identifier, title, status, latest_action_desc, source)"
        " VALUES (?, ?, ?, ?, 'adopted', ?, 'openstates')",
        [("2025-sjr116", "2025", "SJR 116", "Relating to: the partial veto (second consideration).",
          "Published.  Enrolled Joint Resolution 14"),
         ("2023-ajr112", "2023", "AJR 112", "Relating to: the partial veto (first consideration).",
          "Published.  Enrolled Joint Resolution 16")])
    db.executemany(
        "INSERT INTO vote_events (id, bill_id, chamber, motion, result, source_url)"
        " VALUES (?, ?, ?, ?, 'pass', 'https://docs.legis.wisconsin.gov/document/votes/x')",
        [(f"{b}-{c}", b, c, m) for b in ("2025-sjr116", "2023-ajr112")
         for c, m in (("upper", "ADOPTION"), ("lower", "CONCURRENCE AS AMENDED"))])
    return db


def pages(second_html, first_html):
    return {ENROLLED.format(year="2025", slug="sjr116"): second_html,
            ENROLLED.format(year="2023", slug="ajr112"): first_html}.__getitem__


def test_a_question_proved_by_every_record_is_kept_with_its_marked_text(conn):
    election, (measure,) = measures(conn, NOTICE, pages(second(note="provisions"), first_page()))
    assert election == "2026-11-03"
    assert (measure["number"], measure["title"], measure["first_bill_id"]) == \
        (1, "Partial veto", "2023-ajr112")
    (section,) = measure["changes"]  # the numbering note is not part of the amendment
    assert section["treatment"].startswith("Section 1. Section 10 (1) (c)")
    assert section["text"] == [[["same", "[Article V] Section 10 (1) (c) the governor may not "],
                                ["del", "and"], ["ins", "or increase any tax"], ["same", "."]]]


@pytest.mark.parametrize("second_html,match", [
    (second(inserted="or increase any fee"), "amendment text differs"),
    (second(question=QUESTION.replace("tax", "fee")), "not in the notice"),
    (second(first="2023 Assembly Joint Resolution 112, which became 2023 Enrolled Joint"
                  " Resolution 15"), "does not show Enrolled Joint Resolution 15"),
    (second(first="2021 Assembly Joint Resolution 112, which became 2021 Enrolled Joint"
                  " Resolution 16"), "not the preceding legislature"),
], ids=["text", "question", "enrolled-number", "legislature"])
def test_any_record_that_disagrees_stops_the_run(conn, second_html, match):
    with pytest.raises(RuntimeError, match=match):
        measures(conn, NOTICE, pages(second_html, first_page()))


def test_a_resolution_without_a_roll_call_in_each_chamber_stops_the_run(conn):
    conn.execute("DELETE FROM vote_events WHERE id = '2023-ajr112-lower'")
    with pytest.raises(RuntimeError, match="no passing roll call"):
        measures(conn, NOTICE, pages(second(), first_page()))


def test_a_notice_question_no_resolution_states_stops_the_run(conn):
    notice = NOTICE.replace("This referendum", "QUESTION 2: “Spare. Shall it?”\nThis referendum")
    with pytest.raises(RuntimeError, match=r"no resolution states: \[2\]"):
        measures(conn, notice, pages(second(), first_page()))
