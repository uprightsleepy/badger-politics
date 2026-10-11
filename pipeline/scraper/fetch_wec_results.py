"""Download WEC ward-by-ward canvass spreadsheets: general elections
(legislative and statewide offices), spring elections (Supreme Court, Court of
Appeals) and statewide referendum questions.

Usage: python -m scraper.fetch_wec_results

URLs are pinned per election (WEC posts one set of files per certified
election; they do not change after certification), so a present file is
never fetched again. Add each new election's files after certification.
Reviewed 2026-10-11 (scraper/README.md): robots.txt permits the files
paths. The results pages answer the project identity with a challenge, so
file names come from search-engine listings of those pages, and the importer
holds every file to its own election line (importer.import_wec_results).

File names are <ger|spring|primary><year>[-part].xlsx. Pre-2021 files sit
under legacy/ with a literally percent-encoded name ("Ward%20by%20Ward..."),
which the URL escapes again (%2520).
"""

import sys
from pathlib import Path

from scraper.http import session

DEST = Path(__file__).resolve().parents[1] / "_data" / "wec-results"
DOCS = "https://elections.wi.gov/sites/default/files/documents/"
LEGACY = "https://elections.wi.gov/sites/default/files/legacy/"


def _legacy(name: str) -> str:
    return LEGACY + name.replace(" ", "%2520")


FILES = {
    # general elections under the 2011 maps; 2014 is the G.A.B. all-offices report
    "ger2014.xlsx": _legacy("11.4.2014 Election Results - all offices w x w report.xlsx"),
    "ger2014-referendum.xlsx": _legacy("11.4.14 Election Results-Referendum-w x w report.xlsx"),
    "ger2016-assembly.xlsx": _legacy("Ward by Ward Report-Assembly.xlsx"),
    # the full report, not the earlier "(SD32 under recount)" one without SD 32
    "ger2016-senate.xlsx": _legacy("Ward by Ward Report-State Senate.xlsx"),
    "ger2018-assembly.xlsx": _legacy("Ward by Ward Report-Gen Election-Assembly.xlsx"),
    "ger2018-senate.xlsx": _legacy("Ward by Ward Report-Gen Election-State Senator.xlsx"),
    "ger2020-assembly.xlsx": _legacy(
        "Ward by Ward Report - Representative to the Assembly.xlsx"),
    "ger2020-senate.xlsx": _legacy("Ward by Ward Report - State Senate.xlsx"),
    "ger2024.xlsx": (
        DOCS + "Ward%20by%20Ward%20Report_November%205%202024%20General%20Election_"
        "Federal%20and%20State%20Contests.xlsx"
    ),
    "ger2022-assembly.xlsx": (
        DOCS + "Ward%20by%20Ward%20Report%20by%20Congressional%20District%20-%20"
        "Representative%20to%20the%20Assembly.xlsx"
    ),
    "ger2022-senate.xlsx": DOCS + "Ward%20by%20Ward%20Report_State%20Senator_0.xlsx",
    # statewide constitutional offices, certified Nov 30, 2022
    "ger2022-governor.xlsx": DOCS + "Ward%20by%20Ward%20Report_Governor_0.xlsx",
    "ger2022-attorney-general.xlsx": DOCS + "Ward%20by%20Ward%20Report_Attorney%20General_0.xlsx",
    "ger2022-secretary-of-state.xlsx": (
        DOCS + "Ward%20by%20Ward%20Report_Secretary%20of%20State_0.xlsx"),
    "ger2022-state-treasurer.xlsx": DOCS + "Ward%20by%20Ward%20Report_State%20Treasurer_0.xlsx",
    # spring elections, and the August 2024 primary's two amendment questions
    "spring2020-supreme-court.xlsx": _legacy("Ward by Ward Report_Supreme Court.xlsx"),
    "spring2020-court-of-appeals.xlsx": _legacy("Ward by Ward Report_Court of Appeals.xlsx"),
    "spring2023-statewide.xlsx": DOCS + "Ward%20by%20Ward%20Report%20statewide%20contests.xlsx",
    "spring2023-referenda.xlsx": DOCS + "Ward%20by%20Ward%20Report%20referendum%20questions.xlsx",
    "spring2024.xlsx": (
        DOCS + "Ward%20by%20Ward%20Report__April%202%202024%20Spring%20Election"
        "_All%20Contests.xlsx"
    ),
    "primary2024-referenda.xlsx": (
        DOCS + "Ward%20by%20Ward%20Report_August%202024%20Partisan%20Primary"
        "_Statewide%20Referendum.xlsx"
    ),
    "spring2025.xlsx": (
        DOCS + "April%201%202025%20Spring%20Election_Ward%20by%20Ward"
        "_State%20Level%20Contests%20and%20Referendum.xlsx"
    ),
    # Not pinned: the 2026 spring workbook ("Ward by Ward Report_Spring
    # Election 2026_All State Contests.xlsx") fails its own arithmetic. Its
    # Supreme Court County Totals sum to 905,510 for Chris Taylor, its Office
    # Totals to 905,490 (checked 2026-10-11). Add it once the Commission
    # reconciles the file.
}


def main(argv: list[str]) -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    http = session()
    for name, url in FILES.items():
        target = DEST / name
        if target.exists():
            print(f"{name}: already present")
            continue
        response = http.get(url, timeout=120)
        response.raise_for_status()
        if not response.content.startswith(b"PK"):  # xlsx = zip container
            raise RuntimeError(f"{url} did not return an xlsx")
        target.write_bytes(response.content)
        print(f"{name}: {len(response.content):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
