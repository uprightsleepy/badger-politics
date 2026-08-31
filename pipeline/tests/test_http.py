"""The shared session identifies itself and rides out transient failures."""

from scraper.http import USER_AGENT, cached_page, session


def test_session_identifies_and_retries() -> None:
    http = session()
    assert http.headers["User-Agent"] == USER_AGENT
    retry = http.get_adapter("https://example.test/").max_retries
    assert retry.total == 3
    assert 503 in retry.status_forcelist
    # the final response is handed back, so callers' own 404 probes still work
    assert retry.raise_on_status is False


def test_cached_page_serves_the_cache_without_a_session(tmp_path) -> None:
    class NoNetwork:
        def get(self, url, timeout):
            raise AssertionError("cache should have answered")

    cache = tmp_path / "cache"
    cache.mkdir()
    # same key derivation as a real first fetch would write
    import hashlib

    url = "https://docs.legis.wisconsin.gov/2025/proposals/ab1"
    (cache / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.html").write_text(
        "<p>hi</p>", encoding="utf-8"
    )
    assert cached_page(NoNetwork(), url, cache) == ("<p>hi</p>", True)
