"""Council members get the same data products as legislators: a JSON
record and an Atom feed each, keyed by the tenant's ids."""

from pathlib import Path

from dataproducts import queries
from dataproducts.api import build_api
from dataproducts.feeds import build_feeds


def seed(db: Path, make_db) -> None:
    conn = make_db(db)
    conn.executescript("""
INSERT INTO local_bodies VALUES ('westalliswi', 'west-allis', 'West Allis',
  'West Allis Common Council', 'https://westalliswi.legistar.com', 5);
INSERT INTO local_members (tenant, person_id, name, slug, seat, member_type, is_current)
  VALUES ('westalliswi', 117, 'Kevin Haass', 'kevin-haass', 5, 'Member', 1),
         ('westalliswi', 9, 'Old Member', 'old-member', NULL, 'Member', 0);
INSERT INTO local_events VALUES ('westalliswi', 100, '2026-08-18', 'Final',
  'https://westalliswi.legistar.com/MeetingDetail.aspx?ID=100');
INSERT INTO local_actions (tenant, event_item_id, event_id, matter_file, title, action, matter_url)
  VALUES ('westalliswi', 7, 100, 'R-2026-5580', 'A TIF resolution', 'Adopted',
          'https://westalliswi.legistar.com/LegislationDetail.aspx?ID=1&GUID=X');
INSERT INTO local_votes VALUES ('westalliswi', 7, 117, 'No');
""")
    conn.commit()
    conn.close()


def test_member_json_and_feed(tmp_path: Path, make_db) -> None:
    db = tmp_path / "wi.sqlite"
    seed(db, make_db)
    conn = queries.connect(db)
    out = tmp_path / "public"
    build_api(conn, out)
    build_feeds(conn, out, hearings=[])
    api = out / "api" / "v1" / "local" / "west-allis"
    index = (api / "index.json").read_text(encoding="utf-8")
    assert '"slug":"kevin-haass"' in index
    member = (api / "kevin-haass.json").read_text(encoding="utf-8")
    assert '"value":"No"' in member and '"matter_file":"R-2026-5580"' in member
    # a former member with no votes gets no record or feed
    assert not (api / "old-member.json").exists()
    feed = (out / "feeds" / "local" / "west-allis" / "kevin-haass.xml").read_text(encoding="utf-8")
    assert "Voted 'No' on R-2026-5580" in feed
    assert "LegislationDetail.aspx?ID=1" in feed
