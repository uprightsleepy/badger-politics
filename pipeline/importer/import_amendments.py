"""Statewide constitutional amendment questions for a November ballot.

Usage: python -m importer.import_amendments <sqlite_path> --cycle 2026

Nothing here is inferred. Every link is proved from two official records:
- the questions and their resolutions come from the Commission's Type A
  referendum notice (fetched by scraper.fetch_wec);
- a question belongs to a resolution only when the enrolled resolution
  states that exact question for that exact election;
- the first consideration is the resolution the enrolled text names, and
  its own history must carry the same enrolled number and title;
- the amendment text the voters decide must be word for word the text the
  preceding legislature agreed to (Wis. Const. art. XII, s. 1; joint rule
  57 (2)), compared run by run including struck and inserted words;
- both resolutions need a passing roll call in each chamber.
Any mismatch fails the run.
"""

from __future__ import annotations

import argparse
import calendar
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import pymupdf
from lxml import html as lxml_html

from scraper.fetch_wec import CYCLES, DATA_DIR
from scraper.http import cached_page, session

CACHE_DIR = Path(__file__).resolve().parents[1] / "_data" / "lrb_cache"
ENROLLED = "https://docs.legis.wisconsin.gov/{year}/related/enrolled/{slug}"
RESOLUTION_RE = re.compile(r"(\d{4}) (Senate|Assembly) Joint Resolution (\d+)")
CONSTITUTION_RE = re.compile(r"\bof article [IVXL]+ of the constitution\b")
PASSAGE_RE =re.compile(r"^(ADOPTION|CONCURRENCE)( AS AMENDED)?$")


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"“ ", "“", re.sub(r" ([,.;:?”])", r"\1", text))


def _bill_id(year: str, house: str, number: str) -> str:
    return f"{year}-{house[0].lower()}jr{number}"


def parse_notice(text: str) -> tuple[str, dict[int, str], list[str]]:
    """(ISO election date, {number: question}, [bill ids]) from the notice."""
    text = _clean(text)
    held = re.search(r"on Tuesday, (\w+ \d{1,2}, \d{4}), the following questions", text)
    questions = {int(n): q for n, q in re.findall(r"QUESTION (\d+): “(.+?)”", text)}
    source = re.search(r"This referendum ballot is a result of (.+?)\. The text", text)
    if not held or not questions or not source:
        raise RuntimeError("referendum notice: date, questions or resolutions not found")
    if sorted(questions) != list(range(1, len(questions) + 1)):
        raise RuntimeError(f"referendum notice: questions numbered {sorted(questions)}")
    bills = [_bill_id(*m) for m in RESOLUTION_RE.findall(source.group(1))]
    if not bills or len(set(bills)) != len(bills):
        raise RuntimeError(f"referendum notice: resolutions unreadable: {source.group(1)}")
    return datetime.strptime(held.group(1), "%B %d, %Y").date().isoformat(), questions, bills


def _segments(block) -> list[list[str]]:
    """[kind, text] runs of one block: 'del' struck, 'ins' underlined, 'same'."""
    runs: list[list[str]] = []
    for piece in block.xpath(".//text()"):
        owner = piece.getparent().getparent() if piece.is_tail else piece.getparent()
        chain = [owner, *owner.iterancestors()]
        chain = chain[: chain.index(block) + 1]
        if any(e.tag == "a" and "reference" in (e.get("class") or "") for e in chain):
            continue  # document anchors ("SJR116,1") are not constitution text
        styles = " ".join(e.get("style") or "" for e in chain)
        kind = "del" if "line-through" in styles else "ins" if "underline" in styles else "same"
        if runs and runs[-1][0] == kind:
            runs[-1][1] += piece
        else:
            runs.append([kind, str(piece)])
    runs = [[kind, re.sub(r"\s+", " ", text)] for kind, text in runs if text.strip()]
    if runs:  # block edges carry layout whitespace only
        runs[0][1] = runs[0][1].lstrip()
        runs[-1][1] = runs[-1][1].rstrip()
    return runs


def parse_enrolled(page: str) -> dict:
    """Title, first-consideration reference, election, questions and the
    amendment text (as treatment + marked runs) of an enrolled resolution."""
    tree = lxml_html.fromstring(page)
    blocks = tree.xpath("//div[@data-path]")
    text = [_clean(b.text_content()) for b in blocks]
    changes, current, title = [], None, None
    for block, line in zip(blocks, text, strict=True):
        cls = (block.get("class") or "").replace("_", "")  # 2023 pages spell qs_text_treat_
        if "qsxcatalog" in cls:
            title = line
        elif "qsactioncon" in cls:
            treatment = re.sub(r"^[A-Z]{2,3}\d+,\d+\s*", "", line)
            current = {"treatment": treatment, "text": []}
            changes.append(current)
        elif "qstexttreat" in cls:
            if current is None:
                raise RuntimeError("enrolled resolution: amendment text before its section")
            current["text"].append(_segments(block))
    if title is None:
        raise RuntimeError("enrolled resolution: no document body")
    body = " ".join(text)
    first = re.search(r"considered a proposed amendment to the constitution in "
                      + RESOLUTION_RE.pattern
                      + r", which became \1 Enrolled Joint Resolution (\d+)", body)
    held = re.search(r"at the election to be held on the first Tuesday of (\w+) (\d{4})", body)
    return {
        "title": title,
        "first": (_bill_id(*first.groups()[:3]), first.group(4)) if first else None,
        "election": held.groups() if held else None,
        "questions": re.findall(r"Question \d+: “(.+?)”", body),
        # sections that treat no article (a numbering note to the LRB, reworded
        # in 2025 AJR 102 s. 2) instruct drafters; they are not the amendment
        "changes": [c for c in changes if CONSTITUTION_RE.search(c["treatment"])],
    }


def _first_tuesday(month: str, year: str) -> str:
    m = list(calendar.month_name).index(month)
    day = next(d for d in range(1, 8) if date(int(year), m, d).weekday() == calendar.TUESDAY)
    return date(int(year), m, day).isoformat()


def _bill(conn: sqlite3.Connection, bill_id: str, stage: str) -> dict:
    row = conn.execute("SELECT id, session_id, identifier, title, status, latest_action_desc"
                       " FROM bills WHERE id = ? AND source = 'openstates'", (bill_id,)).fetchone()
    if row is None:
        raise RuntimeError(f"{bill_id}: not in the legislative record")
    bill = dict(zip(("id", "session", "identifier", "title", "status", "enrolled"), row,
                    strict=True))
    if bill["status"] != "adopted" or \
            not (bill["title"] or "").endswith(f"({stage} consideration)."):
        raise RuntimeError(f"{bill_id}: not an adopted {stage}-consideration resolution")
    return bill


def _require_passage(conn: sqlite3.Connection, bill_id: str) -> None:
    rows = conn.execute("SELECT chamber, motion FROM vote_events WHERE bill_id = ?"
                        " AND result = 'pass' AND source_url LIKE '%/votes/%'",
                        (bill_id,)).fetchall()
    missing = {"upper", "lower"} - {c for c, motion in rows if PASSAGE_RE.match(motion or "")}
    if missing:
        raise RuntimeError(f"{bill_id}: no passing roll call recorded in {missing}")


def measures(conn: sqlite3.Connection, notice_text: str, fetch) -> tuple[str, list[dict]]:
    election, questions, bill_ids = parse_notice(notice_text)
    by_question: dict[str, int] = {q: n for n, q in questions.items()}
    found = []
    for bill_id in bill_ids:
        second = _bill(conn, bill_id, "second")
        year, slug = bill_id.split("-")
        enrolled = parse_enrolled(fetch(ENROLLED.format(year=year, slug=slug)))
        if enrolled["election"] is None or _first_tuesday(*enrolled["election"]) != election:
            raise RuntimeError(f"{bill_id}: enrolled text sets an election other than {election}")
        if enrolled["first"] is None:
            raise RuntimeError(f"{bill_id}: enrolled text names no first consideration")
        first_id, first_enrolled = enrolled["first"]
        if int(first_id[:4]) != int(year) - 2:
            raise RuntimeError(f"{bill_id}: {first_id} is not the preceding legislature")
        first = _bill(conn, first_id, "first")
        if not re.search(rf"Enrolled Joint Resolution {first_enrolled}\b", first["enrolled"] or ""):
            raise RuntimeError(
                f"{first_id}: history does not show Enrolled Joint Resolution {first_enrolled}")
        if first["title"].replace("(first consideration)", "") != \
                second["title"].replace("(second consideration)", ""):
            raise RuntimeError(f"{first_id}: title differs from {bill_id}")
        fy, fslug = first_id.split("-")
        original = parse_enrolled(fetch(ENROLLED.format(year=fy, slug=fslug)))
        if not enrolled["changes"] or original["changes"] != enrolled["changes"]:
            raise RuntimeError(f"{bill_id}: amendment text differs from {first_id}")
        if not enrolled["questions"]:
            raise RuntimeError(f"{bill_id}: enrolled text states no ballot question")
        for question in enrolled["questions"]:
            number = by_question.pop(question, None)
            if number is None:
                raise RuntimeError(f"{bill_id}: its question is not in the notice: {question[:60]}")
            lead = re.match(r"(.+?\.) (Shall .+\?)$", question)
            if lead is None:
                raise RuntimeError(f"{bill_id}: question has no title sentence: {question[:60]}")
            found.append({"number": number, "title": lead.group(1).rstrip("."),
                          "question": question, "bill_id": bill_id, "first_bill_id": first_id,
                          "changes": enrolled["changes"]})
        for bid in (bill_id, first_id):
            _require_passage(conn, bid)
    if by_question:
        raise RuntimeError(f"notice questions no resolution states: {sorted(by_question.values())}")
    return election, sorted(found, key=lambda m: m["number"])


def run(db_path: Path, cycle: int) -> int:
    name, url = next((n, u) for n, u in CYCLES[cycle].items() if n.startswith("referendum-"))
    with pymupdf.open(DATA_DIR / name) as pdf:
        notice = "\n".join(page.get_text() for page in pdf)
    http = session()
    conn = sqlite3.connect(db_path)
    election, found = measures(conn, notice, lambda u: cached_page(http, u, CACHE_DIR)[0])
    if not election.startswith(str(cycle)):
        raise RuntimeError(f"referendum notice is for {election}, not the {cycle} cycle")
    with conn:
        conn.execute("DELETE FROM ballot_measures WHERE election_date = ?", (election,))
        conn.executemany(
            "INSERT INTO ballot_measures (election_date, number, title, question, bill_id,"
            " first_bill_id, changes_json, notice_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(election, m["number"], m["title"], m["question"], m["bill_id"], m["first_bill_id"],
              json.dumps(m["changes"]), url) for m in found])
    conn.close()
    print(f"{len(found)} constitutional amendment questions verified for {election}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db_path", type=Path)
    ap.add_argument("--cycle", type=int, required=True)
    ns = ap.parse_args(argv)
    return run(ns.db_path, ns.cycle)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
