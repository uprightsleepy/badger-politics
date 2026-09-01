"""InSite's Departments listing pages at 100 rows; every page is read."""

from scraper.fetch_local_votes import fetch_departments


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
