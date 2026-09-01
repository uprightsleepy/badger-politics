"""Generate the aldermanic-district boundary file the address lookup uses.

Usage: python -m importer.local_shapes

Manual tool, rerun after a redistricting, output committed. Sources, each
used per its site's rules (docs/research/local-votes-2026-08.md):

- Milwaukee: the Alder Districts 2024 shapefile from the city's open data
  portal (Creative Commons Attribution). The city's ArcGIS host disallows
  automated access in robots.txt, so the licensed download is the source,
  reprojected from the .prj's State Plane CRS with pyproj (a real datum
  shift; hand math would land tens of meters off).
- West Allis: the city's own ArcGIS Server, which publishes the five
  districts and serves WGS84 GeoJSON directly.

Coordinates round to 4 decimals (~11 m), matching district_shapes.py; the
file exists for point-in-polygon in the browser, not cartography.
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import pyproj
import shapefile

PIPELINE = Path(__file__).resolve().parents[1]
BOUNDARIES = PIPELINE / "_data" / "local" / "boundaries"
OUT = PIPELINE.parent / "site" / "public" / "data" / "local-districts.geojson"

DISTRICT_FIELDS = ("DISTRICT", "ALD", "ALD2024", "DIST")


def _round(coords, nd=4):
    if isinstance(coords, (int, float)):
        return round(coords, nd)
    return [_round(c, nd) for c in coords]


def milwaukee_features() -> list[dict]:
    z = zipfile.ZipFile(BOUNDARIES / "alderman.zip")
    prj = z.read("alderman.prj").decode()
    reader = shapefile.Reader(
        shp=io.BytesIO(z.read("alderman.shp")),
        dbf=io.BytesIO(z.read("alderman.dbf")),
        shx=io.BytesIO(z.read("alderman.shx")),
    )
    field = next(
        (f[0] for f in reader.fields[1:] if f[0].upper() in DISTRICT_FIELDS), None
    )
    if field is None:
        raise RuntimeError(f"no district field among {[f[0] for f in reader.fields[1:]]}")
    to_wgs84 = pyproj.Transformer.from_crs(
        pyproj.CRS.from_wkt(prj), "EPSG:4326", always_xy=True
    )
    features = []
    for record in reader.shapeRecords():
        geom = record.shape.__geo_interface__
        rings = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        polys = [
            [[list(to_wgs84.transform(x, y)) for x, y in ring] for ring in poly]
            for poly in rings
        ]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "tenant": "milwaukee",
                    "slug": "milwaukee",
                    "city": "Milwaukee",
                    "district": int(record.record[field]),
                },
                "geometry": {"type": "MultiPolygon", "coordinates": _round(polys)},
            }
        )
    if len(features) != 15:
        raise RuntimeError(f"expected 15 Milwaukee districts, parsed {len(features)}")
    return features


def west_allis_features() -> list[dict]:
    data = json.loads(
        (BOUNDARIES / "westallis_districts.geojson").read_text(encoding="utf-8")
    )
    features = []
    for f in data["features"]:
        geom = f["geometry"]
        coords = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "tenant": "westalliswi",
                    "slug": "west-allis",
                    "city": "West Allis",
                    "district": int(f["properties"]["DISTRICT"]),
                },
                "geometry": {"type": "MultiPolygon", "coordinates": _round(coords)},
            }
        )
    if len(features) != 5:
        raise RuntimeError(f"expected 5 West Allis districts, parsed {len(features)}")
    return features


def main(argv: list[str]) -> int:
    features = milwaukee_features() + west_allis_features()
    OUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features},
                   separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"{len(features)} districts -> {OUT} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
