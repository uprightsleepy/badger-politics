"""Precompute simplified SVG paths for every legislative district.

The LTSB GeoJSON is 284 KB and holds 99 Assembly polygons at full survey
precision, which is far more detail than a thumbnail map needs and far too
much to parse on every one of 132 district pages. Boundaries change once a
decade, so the paths are generated once and committed.

Every district is projected into one shared viewBox, so a district's
position and size on the page are true relative to the rest of the state
rather than each being fitted to its own box.

    uv run python -m importer.district_shapes \
        site/public/data/wi-districts-2024.geojson \
        site/src/data/district-shapes.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HEIGHT = 420.0
# The viewBox width is derived from the projection, never fixed: stretching
# each axis to fill a box chosen in advance is what drew Wisconsin at three
# quarters of its true width.
# A point every ~0.6 viewBox units is plenty at thumbnail size; the full
# precision is a survey artefact, not something a reader can see.
TOLERANCE = 0.6


def mercator_y(lat: float) -> float:
    """Web Mercator's y, in the same units as longitude in radians.

    Meridians converge toward the pole, so degrees of longitude and
    latitude are not interchangeable units of distance. Mercator is
    conformal, which is what an outline needs: local shape is preserved
    everywhere, so the state and every district keep their real form.
    """
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def rings(geometry: dict) -> list[list[list[float]]]:
    """Outer rings only. Interior holes are invisible at this size."""
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"][0]]
    return [poly[0] for poly in geometry["coordinates"]]


def simplify(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop points that land within TOLERANCE of the one already kept."""
    out = [points[0]]
    for x, y in points[1:]:
        px, py = out[-1]
        if abs(x - px) + abs(y - py) >= TOLERANCE:
            out.append((x, y))
    if out[-1] != points[0]:
        out.append(points[0])
    return out


def to_path(geometry: dict, project) -> str:
    parts = []
    for ring in rings(geometry):
        pts = simplify([project(lon, lat) for lon, lat in ring])
        if len(pts) < 3:
            continue
        head = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
        rest = "".join(f"L{x:.1f} {y:.1f}" for x, y in pts[1:])
        parts.append(head + rest + "Z")
    return "".join(parts)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    src, dest = Path(argv[0]), Path(argv[1])
    data = json.loads(src.read_text(encoding="utf-8"))
    feats = data["features"]

    lons = [c[0] for f in feats for r in rings(f["geometry"]) for c in r]
    lats = [c[1] for f in feats for r in rings(f["geometry"]) for c in r]
    min_lon, max_lon, min_lat, max_lat = min(lons), max(lons), min(lats), max(lats)

    # one scale for both axes, so the drawing keeps the projection's shape
    x0, y0 = math.radians(min_lon), mercator_y(max_lat)
    scale = HEIGHT / (mercator_y(max_lat) - mercator_y(min_lat))
    width = (math.radians(max_lon) - x0) * scale

    def project(lon: float, lat: float) -> tuple[float, float]:
        return (math.radians(lon) - x0) * scale, (y0 - mercator_y(lat)) * scale

    shapes: dict[str, str] = {}
    senate: dict[int, list[dict]] = {}
    for f in feats:
        ad = f["properties"]["ad"]
        shapes[f"assembly-{ad}"] = to_path(f["geometry"], project)
        senate.setdefault(f["properties"]["sd"], []).append(f["geometry"])

    # a Senate district is exactly three Assembly districts; drawing all
    # three outlines is honest and needs no polygon union
    for sd, geoms in senate.items():
        shapes[f"senate-{sd}"] = "".join(to_path(g, project) for g in geoms)

    # The state outline is context behind the highlighted district, so it
    # is drawn far coarser: at full tolerance it was 69 KB, which is not
    # worth inlining on 132 pages to show a silhouette.
    global TOLERANCE
    TOLERANCE = 4.0
    shapes["_state"] = "".join(to_path(f["geometry"], project) for f in feats)
    shapes["_viewBox"] = f"0 0 {width:.0f} {HEIGHT:.0f}"

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(shapes, separators=(",", ":")) + "\n", encoding="utf-8")
    kb = dest.stat().st_size / 1024
    src_kb = src.stat().st_size / 1024
    print(
        f"district shapes: {len(shapes) - 2} districts, "
        f"{kb:.0f} KB (source {src_kb:.0f} KB)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
