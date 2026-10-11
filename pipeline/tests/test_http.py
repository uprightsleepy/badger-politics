"""The shared session identifies itself and rides out transient failures."""

from pathlib import Path

import pytest

from scraper.http import USER_AGENT, PolicyAdapter, cached_page, session


def test_session_identifies_and_retries() -> None:
    http = session()
    assert http.headers["User-Agent"] == USER_AGENT
    adapter = http.get_adapter("https://example.test/")
    assert isinstance(adapter, PolicyAdapter)
    # Retries must return through the policy/pacing gate, not run inside urllib3.
    assert adapter.max_retries.total == 0


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


def test_cached_page_never_leaves_a_partial_page(tmp_path, monkeypatch) -> None:
    class Page:
        def get(self, url, timeout):
            return self

        def raise_for_status(self):
            pass

        text = "<p>full page</p>"

    real_write = Path.write_text

    def killed_mid_write(self, data, **kwargs):
        real_write(self, data[:3], **kwargs)
        raise KeyboardInterrupt

    monkeypatch.setattr(Path, "write_text", killed_mid_write)
    cache = tmp_path / "cache"
    with pytest.raises(KeyboardInterrupt):
        cached_page(Page(), "https://docs.legis.wisconsin.gov/x", cache)
    monkeypatch.undo()
    # the next run refetches instead of trusting a truncated page
    assert not list(cache.glob("*.html"))
    assert cached_page(Page(), "https://docs.legis.wisconsin.gov/x", cache) == (
        "<p>full page</p>", False
    )
