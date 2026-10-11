"""The executive-order listing is read as printed, and anything it doesn't
state fails the fetch.

fixtures/executive_orders/ holds reduced real captures of the docs.legis
archive (2026-10-11): the index, and Knowles' and Evers' folder pages cut
to their breadcrumb and a few listing entries.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from importer.import_executive_orders import run
from scraper.fetch_executive_orders import FORMAT, parse_folder, parse_index

FIXTURES = Path(__file__).parent / "fixtures" / "executive_orders"
PDF = "https://docs.legis.wisconsin.gov/document/executiveorders"


def page(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def folder(name="2019_tony_evers", governor="Tony Evers"):
    return {"folder": name, "start_year": int(name[:4]), "governor": governor}


def order(year, number, suffix="", name="2019_tony_evers", governor="Tony Evers"):
    return {"folder": name, "governor": governor, "year": year, "number": number,
            "suffix": suffix, "url": f"{PDF}/{year}/{number}{suffix.lower()}.pdf"}


def test_index_lists_every_governor_by_printed_name_in_order():
    governors = parse_index(page("index"))
    assert [(g["start_year"], g["governor"]) for g in governors] == [
        (1965, "Warren P. Knowles"), (1971, "Patrick J. Lucey"),
        (1977, "Martin J. Schreiber"), (1979, "Lee Sherman Dreyfus"),
        (1983, "Anthony Earl"), (1987, "Tommy Thompson"), (2001, "Scott McCallum"),
        (2003, "Jim Doyle"), (2011, "Scott Walker"), (2019, "Tony Evers")]
    assert governors[-1] == folder()


def test_each_order_is_its_labelled_pdf_link_once():
    assert parse_folder(page("2019_tony_evers"), folder()) == [
        order(2019, 1), order(2020, 72), order(2026, 305)]


def test_a_lettered_order_keeps_its_letter_beside_the_plain_number():
    knowles = ("1965_warren_p_knowles", "Warren P. Knowles")
    assert parse_folder(page("1965_warren_p_knowles"), folder(*knowles)) == [
        order(1965, 1, "", *knowles), order(1969, 12, "", *knowles),
        order(1969, 12, "A", *knowles)]


@pytest.mark.parametrize("label", ["2020 Executive Order 73", "Executive Order 72",
                                   "2020 Executive Order 72A"])
def test_a_label_that_disagrees_with_its_link_fails(label):
    listing = page("2019_tony_evers").replace(">2020 Executive Order 72</a>", f">{label}</a>")
    with pytest.raises(RuntimeError, match="disagrees"):
        parse_folder(listing, folder())


def test_an_order_with_only_an_icon_link_fails():
    listing = page("2019_tony_evers").replace(
        '<a href="/document/executiveorders/2020/72.pdf">2020 Executive Order 72</a>', "")
    with pytest.raises(RuntimeError, match="no printed label"):
        parse_folder(listing, folder())


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
    orders = parse_folder(page("2019_tony_evers"), folder())
    (archive / "orders.json").write_text(json.dumps({"format": FORMAT, "orders": orders}))
    run(archive, db)
    run(archive, db)  # a rerun replaces, never duplicates
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT number FROM executive_orders ORDER BY number").fetchall() \
            == [(1,), (72,), (305,)]
    (archive / "orders.json").write_text(json.dumps({"format": FORMAT, "orders": []}))
    with pytest.raises(RuntimeError, match="empty"):
        run(archive, db)
