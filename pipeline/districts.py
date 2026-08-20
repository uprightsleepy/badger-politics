"""Build the client-side district-lookup GeoJSON from LTSB boundaries.

Usage: python -m districts [--out PATH] [--max-bytes N]
       python -m districts --lookup LAT LNG   (test a point against the artifact)

LTSB is the AUTHORITATIVE district source (Census SLD layers can lag WI's
2024 remedial maps — hard rule in CLAUDE.md). Downloads the 2024 Assembly
districts (which carry SEN2024 too), simplifies geometry until the artifact
fits the size budget (<300 KB), and writes features with {ad, sd} properties
for the browser's point-in-polygon lookup on /my-reps.

Every feature keeps ad and sd; sd is cross-checked against the statutory
rule (SD n = ADs 3n-2..3n) — a mismatch fails the build.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import requests
from shapely.geometry import mapping, shape

SERVICE = (
    "https://services1.arcgis.com/FDsAtKBk8Hy4cAH0/arcgis/rest/services/"
    "WI_Assembly_Districts_2024/FeatureServer/0/query"
)
USER_AGENT = "badgerpolitics.org data pipeline (contact: hphil.work@gmail.com)"
RAW_CACHE = Path(__file__).resolve().parent / "_data" / "districts" / "raw.geojson"
DEFAULT_OUT = (
    Path(__file__).resolve().parents[1] / "site" / "public" / "data"
    / "wi-districts-2024.geojson"
)
TOLERANCES = [0.0005, 0.001, 0.002, 0.004, 0.008, 0.016]


def fetch_raw() -> dict:
    if RAW_CACHE.exists():
        return json.loads(RAW_CACHE.read_text(encoding="utf-8"))
    params = {
        "where": "1=1",
        "outFields": "ASM2024,SEN2024",
        "outSR": "4326",
        "f": "geojson",
        # server-side generalization (~50 m) before our own simplification
        "maxAllowableOffset": "0.0005",
    }
    response = requests.get(
        SERVICE, params=params, headers={"User-Agent": USER_AGENT}, timeout=300
    )
    response.raise_for_status()
    data = response.json()
    if len(data.get("features", [])) != 99:
        raise RuntimeError(
            f"LTSB drift: expected 99 assembly districts, got"
            f" {len(data.get('features', []))}"
        )
    RAW_CACHE.parent.mkdir(parents=True, exist_ok=True)
    RAW_CACHE.write_text(json.dumps(data), encoding="utf-8")
    return data


def _round_coords(obj, ndigits: int = 4):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], float):
            return [round(v, ndigits) for v in obj]
        return [_round_coords(v, ndigits) for v in obj]
    return obj


def build(out_path: Path, max_bytes: int) -> None:
    raw = fetch_raw()
    districts = []
    for feature in raw["features"]:
        ad = int(feature["properties"]["ASM2024"])
        sd = int(feature["properties"]["SEN2024"])
        if sd != math.ceil(ad / 3):
            raise RuntimeError(f"LTSB drift: AD {ad} maps to SD {sd}, expected ceil(ad/3)")
        districts.append((ad, sd, shape(feature["geometry"])))
    districts.sort()

    for tolerance in TOLERANCES:
        features = []
        for ad, sd, geom in districts:
            simplified = geom.simplify(tolerance, preserve_topology=True)
            geometry = _round_coords(mapping(simplified))
            features.append(
                {
                    "type": "Feature",
                    "properties": {"ad": ad, "sd": sd},
                    "geometry": {"type": geometry["type"], "coordinates":
                                 geometry["coordinates"]},
                }
            )
        payload = json.dumps(
            {"type": "FeatureCollection", "features": features},
            separators=(",", ":"),
        )
        size = len(payload.encode("utf-8"))
        if size <= max_bytes:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(payload, encoding="utf-8")
            print(
                f"wrote {out_path} ({size:,} bytes, tolerance {tolerance},"
                f" {len(features)} districts)"
            )
            return
    raise RuntimeError(f"could not fit under {max_bytes:,} bytes; raise tolerance list")


def lookup(out_path: Path, lat: float, lng: float) -> int:
    from shapely.geometry import Point

    data = json.loads(out_path.read_text(encoding="utf-8"))
    point = Point(lng, lat)
    hits = [
        f["properties"]
        for f in data["features"]
        if shape(f["geometry"]).contains(point)
    ]
    if not hits:
        # border points can fall in simplification gaps; nearest wins (the
        # site does the same, with a 'near a boundary' caveat shown)
        nearest = min(
            data["features"], key=lambda f: shape(f["geometry"]).distance(point)
        )
        print(f"({lat}, {lng}) -> no direct hit; nearest: {nearest['properties']}")
        return 1
    print(f"({lat}, {lng}) -> {hits[0]}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--max-bytes", type=int, default=300_000)
    parser.add_argument("--lookup", nargs=2, type=float, metavar=("LAT", "LNG"))
    ns = parser.parse_args(argv)
    if ns.lookup:
        return lookup(ns.out, *ns.lookup)
    build(ns.out, ns.max_bytes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
