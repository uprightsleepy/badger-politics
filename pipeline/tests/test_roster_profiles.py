import pytest

from importer.import_local import attribute_profile
from scraper.fetch_local_profiles import roster_profiles


@pytest.mark.parametrize("layout,card", [
    ("directory", '''<div class="row"><div><h2>Pat Example, District 1</h2></div>
      <div class="rz-block-img" style="background: url('portraits/pat.jpg') center"></div>
      </div>'''),
    ("council", '''<div class="alderperson"><h3>Aldermanic District 1<br>Wards 1, 2</h3>
      <img src="portraits/pat.jpg"><h4>Pat Example</h4></div>'''),
])
def test_shared_profile_cards_resolve_base_and_require_name_and_district(layout, card):
    spec = {"tenant": "example", "seats": 1, "profile_layout": layout,
            "profile_url": "https://city.example/government/council"}
    page = '<base href="https://city.example/">' + card
    result = roster_profiles(page, spec)
    assert result == {"page": spec["profile_url"], "members": [
        {"name": "Pat Example", "seat": 1, "image": "https://city.example/portraits/pat.jpg"},
    ]}
    profiles = {"example": result}
    assert attribute_profile(spec, "Pat Example", 1, None, profiles, None)[:2] == (
        "https://city.example/portraits/pat.jpg", spec["profile_url"],
    )
    for name, seat in [("Other Example", 1), ("Pat Example", 2)]:
        assert attribute_profile(spec, name, seat, None, profiles, None)[:2] == (None, None)
    with pytest.raises(ValueError, match="incomplete profile roster"):
        roster_profiles(page, {**spec, "seats": 2})
    with pytest.raises(ValueError, match="incomplete profile roster"):
        roster_profiles(page + card, spec)
    foreign = page.replace('portraits/pat.jpg', 'https://unreviewed.example/pat.jpg')
    assert roster_profiles(foreign, spec)["members"][0]["image"] is None
