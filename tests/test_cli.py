"""Tests for configuration parsing and the watch cycle."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from linkwatcher import cli
from linkwatcher.config import Config, ConfigError
from linkwatcher.notify import NotifyError
from linkwatcher.watcher import FetchError

BASE = "https://example.com/blog/"

PAGE_ONE = """
<a href="/post-1.html">one</a>
<a href="/post-2.html">two</a>
"""

PAGE_TWO = """
<a href="/post-1.html">one</a>
<a href="/post-2.html">two</a>
<a href="/post-3.html">three</a>
"""


def make_config(tmp_path: Path, **overrides: object) -> Config:
    values = {
        "url": BASE,
        "selector": "a[href]",
        "state_path": tmp_path / "state.json",
        "token": "test-token",
        "timeout": 5.0,
    }
    values.update(overrides)
    return Config(**values)  # type: ignore[arg-type]


class RecordingNotifier:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.headers: list[str | None] = []

    def send_lines(self, lines: list[str], *, header: str | None = None) -> int:
        self.batches.append(list(lines))
        self.headers.append(header)
        return 1


def use_page(monkeypatch: pytest.MonkeyPatch, html: str) -> None:
    monkeypatch.setattr(cli, "fetch_html", lambda *a, **k: html)


def test_config_requires_url() -> None:
    with pytest.raises(ConfigError, match="WATCH_URL"):
        Config.from_env({})


def test_config_defaults() -> None:
    config = Config.from_env({"WATCH_URL": BASE})

    assert config.selector == "a[href]"
    assert config.timeout == 30.0
    assert config.seed is True
    assert config.dry_run is False


def test_config_parses_environment() -> None:
    config = Config.from_env(
        {
            "WATCH_URL": BASE,
            "WATCH_SELECTOR": "h2 a",
            "WATCH_TIMEOUT": "5",
            "LINE_CHANNEL_ACCESS_TOKEN": "tok",
            "LINE_TO": "U123",
            "WATCH_DRY_RUN": "true",
            "WATCH_NO_SEED": "1",
            "WATCH_IGNORE": "/tag/\n/privacy/",
        }
    )

    assert config.selector == "h2 a"
    assert config.timeout == 5.0
    assert config.token == "tok"
    assert config.recipient == "U123"
    assert config.dry_run is True
    assert config.seed is False
    assert len(config.ignore) == 2


def test_config_rejects_bad_timeout() -> None:
    with pytest.raises(ConfigError, match="WATCH_TIMEOUT"):
        Config.from_env({"WATCH_URL": BASE, "WATCH_TIMEOUT": "soon"})


def test_first_run_seeds_without_notifying(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_page(monkeypatch, PAGE_ONE)
    notifier = RecordingNotifier()

    change = cli.run(make_config(tmp_path), notifier=notifier)  # type: ignore[arg-type]

    assert notifier.batches == []
    assert change.added == []
    assert (tmp_path / "state.json").exists()


def test_second_run_reports_new_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_page(monkeypatch, PAGE_ONE)
    cli.run(make_config(tmp_path))

    use_page(monkeypatch, PAGE_TWO)
    notifier = RecordingNotifier()
    change = cli.run(make_config(tmp_path), notifier=notifier)  # type: ignore[arg-type]

    assert change.added == ["https://example.com/post-3.html"]
    assert notifier.batches == [["https://example.com/post-3.html"]]


def test_no_change_skips_notification(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_page(monkeypatch, PAGE_ONE)
    cli.run(make_config(tmp_path))

    notifier = RecordingNotifier()
    change = cli.run(make_config(tmp_path), notifier=notifier)  # type: ignore[arg-type]

    assert change.is_empty
    assert notifier.batches == []


def test_failed_notification_keeps_previous_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_page(monkeypatch, PAGE_ONE)
    cli.run(make_config(tmp_path))
    before = (tmp_path / "state.json").read_text(encoding="utf-8")

    use_page(monkeypatch, PAGE_TWO)

    class FailingNotifier(RecordingNotifier):
        def send_lines(self, lines: list[str], *, header: str | None = None) -> int:
            raise NotifyError("line is down")

    with pytest.raises(NotifyError):
        cli.run(make_config(tmp_path), notifier=FailingNotifier())  # type: ignore[arg-type]

    assert (tmp_path / "state.json").read_text(encoding="utf-8") == before


def test_removed_links_are_recorded_without_notification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_page(monkeypatch, PAGE_TWO)
    cli.run(make_config(tmp_path))

    use_page(monkeypatch, PAGE_ONE)
    notifier = RecordingNotifier()
    change = cli.run(make_config(tmp_path), notifier=notifier)  # type: ignore[arg-type]

    assert change.removed == ["https://example.com/post-3.html"]
    assert notifier.batches == []


def test_empty_page_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_page(monkeypatch, "<html><body>no links</body></html>")

    with pytest.raises(FetchError, match="No links matched"):
        cli.run(make_config(tmp_path))


def test_dry_run_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_page(monkeypatch, PAGE_ONE)
    cli.run(make_config(tmp_path, dry_run=True))

    assert not (tmp_path / "state.json").exists()


def test_missing_token_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_page(monkeypatch, PAGE_ONE)
    cli.run(make_config(tmp_path))

    use_page(monkeypatch, PAGE_TWO)
    with pytest.raises(NotifyError, match="LINE_CHANNEL_ACCESS_TOKEN"):
        cli.run(make_config(tmp_path, token=None))


def test_ignore_patterns_are_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    html = '<a href="/post/1">a</a><a href="/tag/x">b</a>'
    use_page(monkeypatch, html)

    cli.run(make_config(tmp_path, ignore=(re.compile(r"/tag/"),)))

    state = (tmp_path / "state.json").read_text(encoding="utf-8")
    assert "/tag/" not in state
    assert "/post/1" in state


def test_cli_returns_failure_on_fetch_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_page(monkeypatch, "<html></html>")
    monkeypatch.setenv("WATCH_URL", BASE)
    monkeypatch.setenv("WATCH_STATE_PATH", str(tmp_path / "state.json"))

    assert cli.main([]) == 1


def test_cli_resolve_config_prefers_arguments(tmp_path: Path) -> None:
    args = cli.build_parser().parse_args(
        [BASE, "--selector", "h2 a", "--timeout", "3", "--dry-run", "--ignore", "/tag/"]
    )
    config = cli.resolve_config(args, env={"WATCH_URL": "https://ignored.example"})

    assert config.url == BASE
    assert config.selector == "h2 a"
    assert config.timeout == 3.0
    assert config.dry_run is True
    assert len(config.ignore) == 1


def test_cli_rejects_non_positive_timeout(tmp_path: Path) -> None:
    args = cli.build_parser().parse_args([BASE, "--timeout", "0"])

    with pytest.raises(ConfigError, match="greater than zero"):
        cli.resolve_config(args, env={})
