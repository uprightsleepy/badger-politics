"""Parse WEC's "Candidate Tracking by Office" PDF into the normalized CSV
that import_wec consumes. Drift alarms fail loud, never guess.

Usage: python -m importer.wec_pdf <ballot_access.pdf> <candidates.csv>
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

CONGRESS_RE = re.compile(r"^REPRESENTATIVE IN CONGRESS DISTRICT (\d+)$")


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
    office_x = 0.0
    subtotaled: set[str] = set()
    noncandidacy = False
    party_x = status_x = campaign_x = None
    in_tracking = False
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
                parsed = sum(r["office"] == office for r in records)
                if office and str(parsed) != texts[-1]:
                    raise RuntimeError(f"WEC drift: {office} subtotal {texts[-1]}, parsed {parsed}")
                subtotaled.add(office)
                office, incumbent, noncandidacy = "", "", False
                continue
            if texts[0] == "Office" and ":" in texts[1]:
                office, incumbent, noncandidacy = "", "", False
                # same row: office name (left region) + 'Incumbent:' + name
                inc_idx = next(
                    (i for i, t in enumerate(texts) if t == "Incumbent:"), None
                )
                name_words = texts[2:inc_idx] if inc_idx else texts[2:]
                office = " ".join(name_words)
                office_x = row[2][0]
                if inc_idx is not None:
                    incumbent = " ".join(texts[inc_idx + 1:])
                    # the marker can wrap mid-phrase, so match its prefix
                    if "(Filed" in incumbent:
                        noncandidacy = True
                        incumbent = incumbent.split("(Filed")[0].strip()
                continue
            if "(Filed Notification" in joined or joined == "Noncandidacy)":
                noncandidacy = True
                continue
            if not office:
                continue
            status_words = [t for x, t in row if x >= status_x - 2]
            name_words = [t for x, t in row if x < party_x and not re.fullmatch(r"\d+", t)]
            if not (status_words and status_words[0] in STATUSES and name_words):
                # a wrapped office name continues in the office column, where a
                # receipt number never sits ("REPRESENTATIVE IN CONGRESS DISTRICT" / "1")
                if all(office_x - 2 <= x < party_x for x, _ in row) and (
                        joined.isupper() or joined.isdigit()):
                    office = f"{office} {joined}"
                    continue
                # a wrapped party label continues the row above ("Wisconsin" / "Green")
                if records and records[-1]["office"] == office and all(
                        party_x - 2 <= x < campaign_x - 2 for x, _ in row):
                    records[-1]["party"] = f"{records[-1]['party']} {joined}"
                    continue
                raise RuntimeError(f"WEC drift: unparsed tracking row under {office}: {joined!r}")
            party_words = [t for x, t in row if party_x - 2 <= x < campaign_x - 2]
            records.append({
                "office": office,
                "incumbent": incumbent,
                "incumbent_noncandidacy": str(int(noncandidacy)),
                "candidate": " ".join(name_words),
                "party": " ".join(party_words),
                "ballot_status": status_words[0],
            })
    doc.close()

    if not records:
        raise RuntimeError("WEC drift: no candidate rows parsed")
    unchecked = {r["office"] for r in records} - subtotaled
    if unchecked:
        raise RuntimeError(f"WEC drift: no office subtotal to check for {sorted(unchecked)}")
    congress = {r["office"] for r in records if "IN CONGRESS" in r["office"]}
    if any(not CONGRESS_RE.match(o) for o in congress):
        raise RuntimeError(f"WEC drift: House office without a district: {sorted(congress)}")
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
