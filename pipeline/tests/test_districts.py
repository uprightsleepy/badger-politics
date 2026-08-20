"""The committed district-lookup artifact stays valid and correct."""

import json
import math
from pathlib import Path

import pytest
from shapely.geometry import Point, shape

ARTIFACT = (
    Path(__file__).resolve().parents[2]
    / "site" / "public" / "data" / "wi-districts-2024.geojson"
)


@pytest.fixture(scope="module")
def features() -> list[dict]:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))["features"]


def test_artifact_committed_and_small() -> None:
    assert ARTIFACT.exists(), "run: python -m districts"
    assert ARTIFACT.stat().st_size <= 300_000


def test_all_99_districts_with_statutory_sd(features: list[dict]) -> None:
    ads = sorted(f["properties"]["ad"] for f in features)
    assert ads == list(range(1, 100))
    for f in features:
        assert f["properties"]["sd"] == math.ceil(f["properties"]["ad"] / 3)


def test_west_allis_point_resolves(features: list[dict]) -> None:
    point = Point(-88.0070, 43.0167)  # West Allis; LTSB server: AD 14 / SD 5
    hits = [f["properties"] for f in features if shape(f["geometry"]).contains(point)]
    assert hits == [{"ad": 14, "sd": 5}]


def test_madison_capitol_point_resolves(features: list[dict]) -> None:
    point = Point(-89.3841, 43.0747)  # WI State Capitol
    hits = [f["properties"] for f in features if shape(f["geometry"]).contains(point)]
    assert len(hits) == 1
    assert hits[0]["sd"] == math.ceil(hits[0]["ad"] / 3)
