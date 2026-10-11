"""ACS district figures load only on the current map and stay complete and sane."""

import json
import sqlite3
from pathlib import Path

import pytest

from importer import import_census
from importer.checks import check_demographics
from scraper import fetch_census

VALUES = {"population": ("59500", "1800"), "median_age": ("41.2", "1.1"),
          "age_65_plus_pct": ("19.4", "1.2"), "median_household_income": ("74210", "3900"),
          "bachelors_pct": ("31.0", "2.4"), "owner_occupied_pct": ("68.3", "2.6")}


def release(map_year: int = 2024, name_year: int = 2024) -> dict:
    measures = {m: list(pair[:2]) for m, pair in fetch_census.MEASURES.items()}
    tables = {}
    for chamber, geography in fetch_census.GEOGRAPHIES.items():
        header = ["NAME", *(v for pair in measures.values() for v in pair), "state", geography]
        rows = []
        for d in range(1, import_census.SEATS[chamber] + 1):
            values = [x for m in measures for x in VALUES[m]]
            if chamber == "upper":
                values[0:2] = ["178500", "3100"]
            rows.append([f"District {d} ({name_year}); Wisconsin", *values, "55", f"{d:03d}"])
        rows.append(["District ZZZ; Wisconsin", *(["0"] * 12), "55", "ZZZ"])
        tables[chamber] = [header, *rows]
    return {"acs_year": 2024, "map_year": map_year, "measures": measures, "tables": tables}


@pytest.fixture()
def db(tmp_path: Path, make_db):
    path = tmp_path / "wi.sqlite"
    make_db(path).close()
    return path


def load(db: Path, tmp_path: Path, doc: dict):
    source = tmp_path / "census.json"
    source.write_text(json.dumps(doc), encoding="utf-8")
    import_census.run(db, source)
    return sqlite3.connect(db)


def test_current_map_loads_every_district_and_passes(db, tmp_path):
    conn = load(db, tmp_path, release())
    assert conn.execute("SELECT COUNT(*) FROM district_demographics").fetchone()[0] == 132 * 6
    assert conn.execute("SELECT estimate, moe FROM district_demographics WHERE chamber='upper'"
                        " AND district=5 AND measure='population'").fetchone() == (178500, 3100)
    assert check_demographics(conn) == []


def test_another_map_loads_nothing(db, tmp_path):
    conn = load(db, tmp_path, release(map_year=2022, name_year=2022))
    assert conn.execute("SELECT COUNT(*) FROM district_demographics").fetchone()[0] == 0
    assert check_demographics(conn) == []


def test_rows_naming_another_map_are_refused(db, tmp_path):
    with pytest.raises(ValueError, match="not on the 2024 map"):
        load(db, tmp_path, release(name_year=2022))


def test_unavailable_value_is_refused(db, tmp_path):
    doc = release()
    doc["tables"]["lower"][3][4] = "-666666666"
    with pytest.raises(ValueError, match="unavailable"):
        load(db, tmp_path, doc)


@pytest.mark.parametrize("sql, message", [
    ("DELETE FROM district_demographics WHERE chamber='lower' AND district=14"
     " AND measure='median_age'", "lack figures"),
    ("UPDATE district_demographics SET estimate=12 WHERE measure='median_age'"
     " AND district=3", "outside"),
    ("UPDATE district_demographics SET estimate=59500 WHERE chamber='upper'"
     " AND measure='population'", "outside"),
    ("UPDATE district_demographics SET moe=-1 WHERE district=7", "margin"),
])
def test_gate_catches_gaps_and_implausible_values(db, tmp_path, sql, message):
    conn = load(db, tmp_path, release())
    conn.execute(sql)
    assert any(message in f for f in check_demographics(conn))


class Redirect:
    is_redirect = True
    headers = {"X-DataWebAPI-KeyError": "1"}
    status_code = 302


def test_keyless_refusal_names_the_fix_but_never_the_query():
    class Http:
        def get(self, url, **kwargs):
            return Redirect()

    with pytest.raises(RuntimeError, match="CENSUS_API_KEY") as raised:
        fetch_census.get_json(Http(), fetch_census.DATASET, {"key": "SECRET"})
    assert "SECRET" not in str(raised.value)


def test_pinned_release_is_fetched_once(tmp_path, monkeypatch):
    out = tmp_path / "census.json"
    out.write_text(json.dumps({"acs_year": fetch_census.ACS_YEAR}), encoding="utf-8")
    monkeypatch.setattr(fetch_census, "fetch", lambda: pytest.fail("refetched"))
    assert fetch_census.main(["--out", str(out)]) == 0
