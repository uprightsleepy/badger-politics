"""Precompute SVG paths for the council districts, one drawing per city.

Reads the committed lookup file (site/public/data/local-districts.geojson)
and writes site/src/data/local-district-shapes.json: each district as a
path inside its city's own viewBox, plus the city's whole set of districts
as the backdrop, the way district_shapes.py draws a seat within the state.
Rerun after local_shapes.py; output committed.

    uv run python -m importer.local_district_shapes
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

from importer import district_shapes as ds

PIPELINE = Path(__file__).resolve().parents[1]
SRC = PIPELINE.parent / "site" / "public" / "data" / "local-districts.geojson"
DEST = PIPELINE.parent / "site" / "src" / "data" / "local-district-shapes.json"
HEIGHT = 300.0


def main(argv: list[str]) -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    by_city: dict[str, list[dict]] = {}
    for f in data["features"]:
        by_city.setdefault(f["properties"]["slug"], []).append(f)

    shapes: dict[str, str] = {}
    for slug, feats in by_city.items():
        lons = [c[0] for f in feats for r in ds.rings(f["geometry"]) for c in r]
        lats = [c[1] for f in feats for r in ds.rings(f["geometry"]) for c in r]
        x0, y0 = math.radians(min(lons)), ds.mercator_y(max(lats))
        scale = HEIGHT / (ds.mercator_y(max(lats)) - ds.mercator_y(min(lats)))
        width = (math.radians(max(lons)) - x0) * scale

        def project(lon: float, lat: float, x0=x0, y0=y0, scale=scale) -> tuple[float, float]:
            return (math.radians(lon) - x0) * scale, (y0 - ds.mercator_y(lat)) * scale

        for f in feats:
            shapes[f"{slug}-{f['properties']['district']}"] = ds.to_path(f["geometry"], project)
        shapes[f"_{slug}"] = "".join(ds.to_path(f["geometry"], project) for f in feats)
        shapes[f"_{slug}_viewBox"] = f"0 0 {width:.0f} {HEIGHT:.0f}"

    DEST.write_text(json.dumps(shapes, separators=(",", ":")) + "\n", encoding="utf-8")
    districts = sum(len(v) for v in by_city.values())
    print(f"council district shapes: {districts} districts in {len(by_city)} cities, "
          f"{DEST.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
