"""InSite grids page; every page is read, for bodies and for meeting items."""

from scraper.fetch_local_votes import fetch_departments, fetch_links


def row(dept_id: int, name: str) -> str:
    return (f'<a href="DepartmentDetail.aspx?ID={dept_id}&amp;GUID=A{dept_id}&amp;M=D">'
            f"<span>{name}</span></a>")


def page_link(n: int) -> str:
    return (f'<a href="javascript:__doPostBack(&#39;grid$page{n}&#39;,&#39;&#39;)">'
            f"<span>{n}</span></a>")


PAGES = {
    1: '<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="v1" />'
       + row(10, "ARTS BOARD") + row(11, "Ethics &amp; Rules") + page_link(1) + page_link(2),
    2: '<input type="hidden" name="__VIEWSTATE" value="v2" />'
       + row(12, "ZONING COMMITTEE") + page_link(1) + page_link(2),
}


class FakeHttp:
    def __init__(self) -> None:
        self.posts: list[dict] = []

    def get(self, url, timeout):
        return FakeResponse(PAGES[1])

    def post(self, url, data, timeout):
        self.posts.append(data)
        return FakeResponse(PAGES[2])


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        pass


def test_every_page_is_read_through_the_forms_own_postback() -> None:
    http = FakeHttp()
    rows = fetch_departments(http, "https://x.legistar.com", 0)
    assert [r["name"] for r in rows] == ["ARTS BOARD", "Ethics & Rules", "ZONING COMMITTEE"]
    assert rows[0]["url"] == "https://x.legistar.com/DepartmentDetail.aspx?ID=10&GUID=A10"
    # page 2 was requested exactly once, carrying page 1's form state and its own link target
    assert http.posts == [{"__VIEWSTATE": "v1", "__EVENTTARGET": "grid$page2",
                           "__EVENTARGUMENT": ""}]


def leg(leg_id: int, file: str) -> str:
    return (f'<a href="LegislationDetail.aspx?ID={leg_id}&amp;GUID=AB{leg_id}&amp;Options=&amp;">'
            f"<span>{file}</span></a>")


def test_meeting_item_links_come_from_every_page_of_the_grid() -> None:
    PAGES[1] = ('<input type="hidden" name="__VIEWSTATE" value="m1" />'
                + leg(1, "081001") + page_link(1) + page_link(2))
    PAGES[2] = ('<input type="hidden" name="__VIEWSTATE" value="m2" />'
                + leg(2, "081002") + leg(3, "081002") + page_link(1) + page_link(2))
    http = FakeHttp()
    event = {"EventInSiteURL": "https://x.legistar.com/MeetingDetail.aspx?LEGID=1&GID=5&G=Z"}
    links = fetch_links(http, event, "https://x.legistar.com", 0)
    # one file across pages links; the file shown with two pages links nowhere
    assert links == {"081001": "https://x.legistar.com/LegislationDetail.aspx?ID=1&GUID=AB1"}
    assert http.posts == [{"__VIEWSTATE": "m1", "__EVENTTARGET": "grid$page2",
                           "__EVENTARGUMENT": ""}]
