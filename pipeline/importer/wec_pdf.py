"""Parse WEC's "Candidate Tracking by Office" (Appendix B of the ballot
access report PDF) into a normalized CSV.

Usage: python -m importer.wec_pdf <ballot_access.pdf> <candidates.csv>

Output columns: office, incumbent, incumbent_noncandidacy, candidate,
party, ballot_status. The CSV is the stable contract import_wec consumes;
whatever WEC publishes next cycle only has to be converted back to it.

Drift alarms (fail loud, never guess): the tracking header must be found,
every candidate row must end in a known ballot status, and at least 100
legislative offices must be present (99 Assembly + 17 Senate in a midterm).
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import pymupdf

STATUSES = {"Approve", "Deny", "Challenged"}
TRACKING_TITLE = "Candidate Tracking by Office"
LEGISLATIVE_RE = re.compile(
    r"^(STATE SENATOR DISTRICT|REPRESENTATIVE TO THE ASSEMBLY DISTRICT) (\d+)$"
)


def _lines(page: pymupdf.Page) -> list[list[tuple[float, str]]]:
    """Words grouped into visual rows: list of (x, text), sorted by x."""
    words = page.get_text("words")  # x0, y0, x1, y1, text, block, line, word
    rows: dict[int, list[tuple[float, str]]] = {}
    for x0, y0, _x1, _y1, text, *_ in words:
        rows.setdefault(round(y0), []).append((x0, text))
    return [sorted(rows[y]) for y in sorted(rows)]


def parse_tracking(pdf_path: Path) -> list[dict[str, str]]:
    doc = pymupdf.open(pdf_path)
    records: list[dict[str, str]] = []
    office = incumbent = ""
    noncandidacy = False
    pending: dict[str, str] | None = None
    party_x = status_x = campaign_x = None
    in_tracking = False

    def flush() -> None:
        nonlocal pending
        if pending:
            records.append(pending)
            pending = None

    remaining = 0
    for page in doc:
        text = page.get_text()
        if not in_tracking:
            if TRACKING_TITLE not in text:
                continue
            # the title appears only on the report's first page; its footer
            # ("Page 1 of N") tells us how many pages the section spans
            m = re.search(r"Page 1 of (\d+)", text)
            if not m:
                raise RuntimeError("WEC drift: tracking page-count footer not found")
            remaining = int(m.group(1))
            in_tracking = True
        if remaining <= 0:
            break
        remaining -= 1
        if party_x is None:
            # min() per label: header words sit leftmost in their columns and
            # data can echo them (a candidate's party 'Olive Party' contains
            # the literal word 'Party' further right)
            xs: dict[str, float] = {}
            for x0, _y0, _x1, _y1, word, *_ in page.get_text("words"):
                if word in ("Party", "Recommended", "Campaign"):
                    xs[word] = min(xs.get(word, x0), x0)
            if not {"Party", "Recommended", "Campaign"} <= set(xs):
                raise RuntimeError("WEC drift: tracking column headers not found")
            party_x, status_x, campaign_x = xs["Party"], xs["Recommended"], xs["Campaign"]

        for row in _lines(page):
            texts = [t for _, t in row]
            joined = " ".join(texts)
            if joined.startswith(("Wisconsin Elections Commission", "Printed ",
                                  "Receipt #", TRACKING_TITLE, "2026 General")):
                continue
            if "Office Subtotal" in joined:
                flush()
                office, incumbent, noncandidacy = "", "", False
                continue
            if texts[0] == "Office" and ":" in texts[1]:
                flush()
                office, incumbent, noncandidacy = "", "", False
                # same row: office name (left region) + 'Incumbent:' + name
                inc_idx = next(
                    (i for i, t in enumerate(texts) if t == "Incumbent:"), None
                )
                name_words = texts[2:inc_idx] if inc_idx else texts[2:]
                office = " ".join(name_words)
                if inc_idx is not None:
                    incumbent = " ".join(texts[inc_idx + 1:])
                    # the marker can wrap mid-phrase, so match its prefix
                    if "(Filed" in incumbent:
                        noncandidacy = True
                        incumbent = incumbent.split("(Filed")[0].strip()
                continue
            # continuation rows for wrapped office/incumbent names
            if office and not any(x >= status_x for x, _ in row) and all(
                x < party_x for x, _ in row
            ) and pending is None and not joined[:1].isdigit():
                candidate_words = [t for x, t in row if x < party_x]
                maybe = " ".join(candidate_words)
                if maybe.isupper() or maybe.isdigit():  # office names are ALL CAPS
                    office = f"{office} {maybe}".strip()
                    continue
            if "(Filed Notification" in joined or joined == "Noncandidacy)":
                noncandidacy = True
                continue
            if office:
                status_words = [t for x, t in row if x >= status_x - 2]
                name_words = [
                    t for x, t in row
                    if x < party_x and not re.fullmatch(r"\d+", t)
                ]
                party_words = [
                    t for x, t in row if party_x - 2 <= x < campaign_x - 2
                ]
                if status_words and status_words[0] in STATUSES and name_words:
                    flush()
                    records.append(
                        {
                            "office": office,
                            "incumbent": incumbent.split("(Filed")[0].strip(),
                            "incumbent_noncandidacy": str(int(noncandidacy)),
                            "candidate": " ".join(name_words),
                            "party": " ".join(party_words),
                            "ballot_status": status_words[0],
                        }
                    )
    flush()
    doc.close()

    if not records:
        raise RuntimeError("WEC drift: no candidate rows parsed")
    legislative = {r["office"] for r in records if LEGISLATIVE_RE.match(r["office"])}
    if len(legislative) < 100:
        raise RuntimeError(
            f"WEC drift: only {len(legislative)} legislative offices parsed"
            " (expected ~116 in a midterm cycle)"
        )
    return records


def main(argv: list[str]) -> int:
    pdf_path, csv_path = Path(argv[0]), Path(argv[1])
    records = parse_tracking(pdf_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    offices = len({r["office"] for r in records})
    print(f"parsed {len(records)} candidate rows across {offices} offices -> {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
