"""Tests for link extraction, state handling and diffing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from linkwatcher.watcher import (
    FetchError,
    StateError,
    WatchState,
    diff,
    extract_links,
    fetch_html,
    filter_links,
)

BASE = "https://example.com/blog/"

HTML = """
<html><body>
  <a href="post-1.html">one</a>
  <a href="/post-2.html">two</a>
  <a href="https://other.example.org/x">external</a>
  <a href="post-1.html#comments">anchor variant</a>
  <a href="javascript:void(0)">js</a>
  <a href="mailto:me@example.com">mail</a>
  <a>no href</a>
  <p class="item">not a link</p>
</body></html>
"""


def test_extract_links_resolves_and_normalises() -> None:
    links = extract_links(HTML, base_url=BASE, selector="a[href]")

    assert links == {
        "https://example.com/blog/post-1.html",
        "https://example.com/post-2.html",
        "https://other.example.org/x",
    }


def test_extract_links_skips_anchor_duplicates() -> None:
    links = extract_links(HTML, base_url=BASE, selector="a[href]")

    assert "https://example.com/blog/post-1.html#comments" not in links


def test_extract_links_honours_selector() -> None:
    html = '<div class="t"><a href="/a">a</a></div><div><a href="/b">b</a></div>'

    assert extract_links(html, base_url=BASE, selector="div.t a") == {"https://example.com/a"}


def test_extract_links_returns_empty_for_bad_selector_target() -> None:
    assert extract_links("<html></html>", base_url=BASE, selector="a") == set()


def test_filter_links_drops_matches() -> None:
    import re

    links = {"https://example.com/tag/a", "https://example.com/post/1"}
    patterns = [re.compile(r"/tag/")]

    assert filter_links(links, patterns) == {"https://example.com/post/1"}


def test_filter_links_without_patterns_is_identity() -> None:
    links = {"https://example.com/a"}

    assert filter_links(links, []) == links


def test_diff_reports_added_and_removed_sorted() -> None:
    change = diff(["b", "a"], ["c", "a"])

    assert change.added == ["c"]
    assert change.removed == ["b"]
    assert not change.is_empty


def test_diff_empty_when_identical() -> None:
    assert diff(["a", "b"], ["b", "a"]).is_empty


def test_state_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    WatchState(url=BASE, links=["https://example.com/b", "https://example.com/a"]).save(path)

    loaded = WatchState.load(path, expected_url=BASE)

    assert loaded is not None
    assert loaded.links == ["https://example.com/a", "https://example.com/b"]


def test_state_load_missing_file_returns_none(tmp_path: Path) -> None:
    assert WatchState.load(tmp_path / "absent.json", expected_url=BASE) is None


def test_state_rejects_other_url(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"url": "https://other.example.org", "links": []}), encoding="utf-8")

    with pytest.raises(StateError, match="belongs to"):
        WatchState.load(path, expected_url=BASE)


def test_state_rejects_corrupt_json(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(StateError, match="not valid JSON"):
        WatchState.load(path, expected_url=BASE)


def test_state_rejects_missing_links_key(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"url": BASE}), encoding="utf-8")

    with pytest.raises(StateError, match="links"):
        WatchState.load(path, expected_url=BASE)


def test_fetch_html_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("network down")

    monkeypatch.setattr("linkwatcher.watcher.urlopen", boom)

    with pytest.raises(FetchError, match="network down"):
        fetch_html(BASE, timeout=1, user_agent="test")
