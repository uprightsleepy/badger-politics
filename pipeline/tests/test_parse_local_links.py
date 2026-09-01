"""Item links come from the meeting's own page, one per file number."""

from scraper.fetch_local_votes import parse_links

INSITE = "https://x.legistar.com"


def link(leg_id: int, guid: str, label: str) -> str:
    return (f'<a href="LegislationDetail.aspx?ID={leg_id}&amp;GUID={guid}&amp;Options=&amp;'
            f'Search=" class="x"><span>{label}</span></a>')


def test_file_numbers_map_to_their_own_page_and_conflicts_map_to_none() -> None:
    page = "".join([
        link(4913721, "C91F", "201705"), link(4913721, "C91F", "201705"),  # listed twice
        link(11, "AAAA", "26-2"), link(12, "BBBB", "26-2"),                 # two pages, one file
        link(13, "CCCC", "R-2026-5575"),
        '<a href="Legislation.aspx?G=08FE">Legislation</a>',
    ])
    assert parse_links(page, INSITE) == {
        "201705": f"{INSITE}/LegislationDetail.aspx?ID=4913721&GUID=C91F",
        "R-2026-5575": f"{INSITE}/LegislationDetail.aspx?ID=13&GUID=CCCC",
    }
