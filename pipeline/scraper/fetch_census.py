"""Fetch the pinned ACS 5-year profile for every Assembly and Senate district.

Usage: python -m scraper.fetch_census [--out PATH]

Runs at most once per ACS release: the response is committed as
importer/census_acs.json (public-domain federal statistics, a few KB) and
this exits without a request while that file holds ACS_YEAR. Bump ACS_YEAR
and MAP_YEAR together, after checking which district map the new release
tabulates (scraper/README.md), then run this once and commit the file.

CENSUS_API_KEY is sent when set. The API has refused keyless data requests
since at least 2026-10-11 (it redirects to missing_key.html); metadata
requests still work without one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from scraper.http import save_json, session

# The 2020-2024 release. Census's 2024 state legislative district collection,
# which this release tabulates, carries Wisconsin's 2024 maps (2023 Wis. Act 94);
# the 2022 and 2023 releases describe the 2022 maps. Each row's NAME repeats
# the map year, and the importer refuses any other.
ACS_YEAR = 2024
MAP_YEAR = 2024
DATASET = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/profile"
# measure: estimate variable, margin variable, the label the release must give it
MEASURES = {
    "population": ("DP05_0001E", "DP05_0001M",
                   "Estimate!!SEX AND AGE!!Total population"),
    "median_age": ("DP05_0018E", "DP05_0018M",
                   "Estimate!!SEX AND AGE!!Total population!!Median age (years)"),
    "age_65_plus_pct": ("DP05_0024PE", "DP05_0024PM",
                        "Percent!!SEX AND AGE!!Total population!!65 years and over"),
    "median_household_income": (
        "DP03_0062E", "DP03_0062M",
        f"Estimate!!INCOME AND BENEFITS (IN {ACS_YEAR} INFLATION-ADJUSTED DOLLARS)!!"
        "Total households!!Median household income (dollars)"),
    "bachelors_pct": ("DP02_0068PE", "DP02_0068PM",
                      "Percent!!EDUCATIONAL ATTAINMENT!!Population 25 years and over!!"
                      "Bachelor's degree or higher"),
    "owner_occupied_pct": ("DP04_0046PE", "DP04_0046PM",
                           "Percent!!HOUSING TENURE!!Occupied housing units!!Owner-occupied"),
}
GEOGRAPHIES = {"lower": "state legislative district (lower chamber)",
               "upper": "state legislative district (upper chamber)"}
OUT = Path(__file__).resolve().parents[1] / "importer" / "census_acs.json"


def get_json(http, url: str, params: dict | None = None):
    """Errors name the path, never the query: it may carry the key."""
    response = http.get(url, params=params, timeout=60, allow_redirects=False)
    if response.is_redirect or response.headers.get("X-DataWebAPI-KeyError"):
        raise RuntimeError(
            f"Census API refused {url} without a valid key; set CENSUS_API_KEY"
            " (free: https://api.census.gov/data/key_signup.html)")
    if response.status_code != 200:
        raise RuntimeError(f"Census API answered HTTP {response.status_code} for {url}")
    return response.json()


def fetch() -> dict:
    http = session()
    labels = {}
    for estimate, _, label in MEASURES.values():
        found = get_json(http, f"{DATASET}/variables/{estimate}.json").get("label")
        if found != label:
            raise RuntimeError(f"{estimate} in ACS {ACS_YEAR} is {found!r}, expected {label!r}")
        labels[estimate] = found
    variables = ",".join(["NAME", *(v for pair in MEASURES.values() for v in pair[:2])])
    key = {"key": os.environ["CENSUS_API_KEY"]} if os.environ.get("CENSUS_API_KEY") else {}
    tables = {
        chamber: get_json(http, DATASET, {"get": variables, "for": f"{geography}:*",
                                          "in": "state:55", **key})
        for chamber, geography in GEOGRAPHIES.items()
    }
    return {"acs_year": ACS_YEAR, "map_year": MAP_YEAR, "dataset": DATASET,
            "measures": {m: list(pair[:2]) for m, pair in MEASURES.items()},
            "labels": labels, "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "tables": tables}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    if args.out.exists() and json.loads(args.out.read_text(encoding="utf-8")).get(
            "acs_year") == ACS_YEAR:
        print(f"census: ACS {ACS_YEAR} already fetched ({args.out.name})")
        return 0
    payload = fetch()
    save_json(args.out, payload)
    counts = {c: len(t) - 1 for c, t in payload["tables"].items()}
    print(f"census: ACS {ACS_YEAR} profile rows {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
