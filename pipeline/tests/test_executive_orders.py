"""The executive-order listing is read as printed, and anything it doesn't
state fails the fetch.

These pages are a reduced, hand-built stand-in for the docs.legis archive
(docs.legis was unreachable from the build sandbox when this was written);
refresh them from a real capture of _data/subjects/executive_orders/pages/.
"""

import json
import sqlite3

import pytest

from importer.import_executive_orders import run
from scraper.fetch_executive_orders import FORMAT, parse_folder, parse_index

INDEX = """<ul>
<li><a href="/code/executive_orders/2011_scott_walker">2011 - 2019 Scott Walker</a></li>
<li><a href="/code/executive_orders/2001_scott_mccallum">2001 - 2003 Scott McCallum</a></li>
<li><a href="https://docs.legis.wisconsin.gov/code/executive_orders/2019_tony_evers">
2019 - Tony Evers</a></li>
<li><a href="/code/executive_orders/2019_tony_evers">Tony Evers</a></li>
<li><a href="/code/admin_code">Administrative Code</a></li>
</ul>"""

EVERS = """<a href="/code/executive_orders">Executive Orders</a>
<ul>
<li><a href="/code/executive_orders/2019_tony_evers/2020_72">Executive Order #72</a>
 Relating to Declaring a Health Emergency in Response to the COVID-19 Coronavirus
 (March 12, 2020) <a href="/code/executive_orders/2019_tony_evers/2020_72.pdf">PDF</a></li>
<li><a href="2019_tony_evers/2019_1.pdf">Executive Order No. 1 &#8211; Relating to Sexual
 Harassment Training</a></li>
</ul>"""


def folder(name="2019_tony_evers", governor="Tony Evers"):
    return {"folder": name, "start_year": int(name[:4]), "governor": governor}


def test_index_lists_each_governor_once_by_printed_name():
    assert parse_index(INDEX) == [
        folder("2001_scott_mccallum", "Scott McCallum"),
        folder("2011_scott_walker", "Scott Walker"),
        folder(),
    ]


def test_orders_merge_their_page_and_pdf_and_keep_the_printed_title():
    orders = parse_folder(EVERS, folder())
    base = "https://docs.legis.wisconsin.gov/code/executive_orders/2019_tony_evers"
    assert orders == [
        {"folder": "2019_tony_evers", "governor": "Tony Evers", "year": 2019, "number": 1,
         "title": "Relating to Sexual Harassment Training", "date": None,
         "url": f"{base}/2019_1.pdf"},
        {"folder": "2019_tony_evers", "governor": "Tony Evers", "year": 2020, "number": 72,
         "title": "Relating to Declaring a Health Emergency in Response to the COVID-19"
                  " Coronavirus",
         "date": "2020-03-12", "url": f"{base}/2020_72.pdf"},
    ]


def test_links_outside_the_folder_are_not_orders():
    page = ('<li><a href="/code/executive_orders/2011_scott_walker/2011_1.pdf">'
            'Executive Order #1</a></li>' + EVERS)
    assert [o["number"] for o in parse_folder(page, folder())] == [1, 72]


def test_an_order_without_a_stated_number_fails():
    page = '<li><a href="/code/executive_orders/2019_tony_evers/emergency.pdf">Order</a></li>'
    with pytest.raises(RuntimeError, match="no order number"):
        parse_folder(page, folder())


def test_a_folder_without_orders_fails():
    with pytest.raises(RuntimeError, match="no executive orders"):
        parse_folder("<p>Coming soon</p>", folder())


def test_an_index_without_governors_fails():
    with pytest.raises(RuntimeError, match="no governor folders"):
        parse_index("<p>maintenance</p>")


def test_import_replaces_the_table_and_rejects_an_empty_archive(tmp_path, make_db):
    db = tmp_path / "wi.sqlite"
    make_db(db).close()
    archive = tmp_path / "eo"
    archive.mkdir()
    orders = parse_folder(EVERS, folder())
    (archive / "orders.json").write_text(json.dumps({"format": FORMAT, "orders": orders}))
    run(archive, db)
    run(archive, db)  # a rerun replaces, never duplicates
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT number FROM executive_orders ORDER BY number").fetchall() \
            == [(1,), (72,)]
    (archive / "orders.json").write_text(json.dumps({"format": FORMAT, "orders": []}))
    with pytest.raises(RuntimeError, match="empty"):
        run(archive, db)
