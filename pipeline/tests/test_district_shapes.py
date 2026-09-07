"""Frozen map outputs preserve projection, ring, and shared-viewBox behavior."""

import copy
import json

import pytest

from importer import district_shapes as ds
from importer import local_district_shapes as local


def square(x, y):
    return [[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]


CASES = [
    pytest.param(
        {"type": "Polygon", "coordinates": [square(-90, 0)]},
        "M0.0 420.0L420.0 420.0L420.0 0.0L0.0 0.0L0.0 420.0Z", "0 0 420 420",
        "M0.0 300.0L300.0 300.0L300.0 0.0L0.0 0.0L0.0 300.0Z", "0 0 300 300",
        id="equator-polygon",
    ),
    pytest.param(
        {"type": "MultiPolygon", "coordinates": [[square(0, 40)], [square(2, 40)]]},
        "M0.0 420.0L319.4 420.0L319.4 0.0L0.0 0.0L0.0 420.0Z"
        "M638.7 420.0L958.1 420.0L958.1 0.0L638.7 0.0L638.7 420.0Z", "0 0 958 420",
        "M0.0 300.0L228.1 300.0L228.1 0.0L0.0 0.0L0.0 300.0Z"
        "M456.2 300.0L684.3 300.0L684.3 0.0L456.2 0.0L456.2 300.0Z", "0 0 684 300",
        id="midlatitude-multipolygon",
    ),
]


@pytest.mark.parametrize("geometry,state_path,state_box,local_path,local_box", CASES)
def test_builders_preserve_frozen_paths_and_viewboxes(
    geometry, state_path, state_box, local_path, local_box, tmp_path, monkeypatch,
):
    # Expected paths and widths are from the pre-refactor generators.
    features = [
        {"type": "Feature", "geometry": copy.deepcopy(geometry),
         "properties": {"ad": i, "sd": 1, "slug": "example", "district": i}}
        for i in (1, 2, 3)
    ]
    source = tmp_path / "boundaries.json"
    source.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    original = source.read_bytes()
    monkeypatch.setattr(ds, "TOLERANCE", 0.6)
    monkeypatch.setattr(local, "SRC", source)
    monkeypatch.setattr(local, "DEST", tmp_path / "local.json")

    assert local.main([]) == 0
    assert json.loads(local.DEST.read_text()) == {
        **{f"example-{i}": local_path for i in (1, 2, 3)},
        "_example": local_path * 3, "_example_viewBox": local_box,
    }
    state_dest = tmp_path / "state.json"
    assert ds.main([str(source), str(state_dest)]) == 0
    assert json.loads(state_dest.read_text()) == {
        **{f"assembly-{i}": state_path for i in (1, 2, 3)},
        "senate-1": state_path * 3, "_state": state_path * 3, "_viewBox": state_box,
    }
    assert ds.TOLERANCE == 4.0  # Preserve the existing state-backdrop side effect.
    assert source.read_bytes() == original


def test_projection_keeps_inputs_and_city_bounds_independent(monkeypatch):
    geometry = {"type": "Polygon", "coordinates": [
        square(-90, 0),
        [[-89.8, 0.2], [-89.2, 0.2], [-89.2, 0.8], [-89.8, 0.8], [-89.8, 0.2]],
    ]}
    features = [{"geometry": geometry}]
    original = copy.deepcopy(features)
    first, first_width = ds.projection_for(features, 300.0)
    second, second_width = ds.projection_for([
        {"geometry": {"type": "MultiPolygon", "coordinates": [
            [square(0, 40)], [square(2, 40)],
        ]}},
    ], 420.0)
    monkeypatch.setattr(ds, "TOLERANCE", 0.6)

    assert first(-90, 1) == (0.0, 0.0)
    assert first(-90, 0) == (0.0, 300.0)
    assert second(0, 41) == (0.0, 0.0)
    assert second(0, 40) == (0.0, 420.0)
    assert f"{first_width:.0f}" == "300"
    assert f"{second_width:.0f}" == "958"
    assert ds.to_path(geometry, first) == (
        "M0.0 300.0L300.0 300.0L300.0 0.0L0.0 0.0L0.0 300.0Z"
    )
    assert features == original
