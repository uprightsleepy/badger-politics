"""Federal import: date parsing, document links, slugs."""

from importer.import_federal import document_url, parse_date, slugify


def test_senate_date_format():
    assert parse_date("August 8, 2026,  04:36 AM") == "2026-08-08"
    assert parse_date("January 3, 2025, 12:00 PM") == "2025-01-03"


def test_document_urls_only_for_known_types():
    assert (
        document_url(119, "S.", "5271")
        == "https://www.congress.gov/bill/119th-congress/senate-bill/5271"
    )
    assert (
        document_url(119, "H.R.", "1")
        == "https://www.congress.gov/bill/119th-congress/house-bill/1"
    )
    assert document_url(119, "PN", "123") is None  # nominations: no bill page
    assert document_url(119, None, None) is None


def test_slugify():
    assert slugify("Tammy Baldwin") == "tammy-baldwin"
    assert slugify("Thomas P. Tiffany") == "thomas-p-tiffany"
