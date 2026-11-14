"""Tests for the LINE Messaging API client."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from linkwatcher.notify import (
    BROADCAST_URL,
    MAX_TEXT_LENGTH,
    PUSH_URL,
    LineNotifier,
    NotifyError,
)


class FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "{}") -> None:
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(
        self, response: FakeResponse | None = None, error: Exception | None = None
    ) -> None:
        self.response = response or FakeResponse()
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error:
            raise self.error
        return self.response


def test_requires_token() -> None:
    with pytest.raises(NotifyError, match="channel access token"):
        LineNotifier(token="")


def test_rejects_invalid_recipient() -> None:
    with pytest.raises(NotifyError, match="LINE_TO"):
        LineNotifier(token="t", recipient="not-an-id")


def test_broadcasts_without_recipient() -> None:
    session = FakeSession()
    notifier = LineNotifier(token="t", session=session)  # type: ignore[arg-type]

    assert notifier.send("hello") is True
    assert session.calls[0]["url"] == BROADCAST_URL
    assert "to" not in session.calls[0]["json"]
    assert session.calls[0]["json"]["messages"][0] == {"type": "text", "text": "hello"}


def test_pushes_to_recipient() -> None:
    session = FakeSession()
    notifier = LineNotifier(token="t", recipient="U1234", session=session)  # type: ignore[arg-type]

    notifier.send("hello")

    assert session.calls[0]["url"] == PUSH_URL
    assert session.calls[0]["json"]["to"] == "U1234"


def test_raises_on_api_error() -> None:
    session = FakeSession(FakeResponse(status_code=401, text="invalid token"))
    notifier = LineNotifier(token="t", session=session)  # type: ignore[arg-type]

    with pytest.raises(NotifyError, match="401"):
        notifier.send("hello")


def test_raises_on_network_error() -> None:
    session = FakeSession(error=requests.ConnectionError("boom"))
    notifier = LineNotifier(token="t", session=session)  # type: ignore[arg-type]

    with pytest.raises(NotifyError, match="boom"):
        notifier.send("hello")


def test_rejects_empty_message() -> None:
    notifier = LineNotifier(token="t", session=FakeSession())  # type: ignore[arg-type]

    with pytest.raises(NotifyError, match="empty"):
        notifier.send("   ")


def test_rejects_overlong_message() -> None:
    notifier = LineNotifier(token="t", session=FakeSession())  # type: ignore[arg-type]

    with pytest.raises(NotifyError, match="limit"):
        notifier.send("x" * (MAX_TEXT_LENGTH + 1))


def test_send_lines_batches_within_limit() -> None:
    session = FakeSession()
    notifier = LineNotifier(token="t", session=session)  # type: ignore[arg-type]
    lines = ["https://example.com/" + "a" * 900 for _ in range(10)]

    sent = notifier.send_lines(lines, header="header")

    assert sent == len(session.calls)
    assert sent > 1
    for call in session.calls:
        assert len(call["json"]["messages"][0]["text"]) <= MAX_TEXT_LENGTH


def test_send_lines_is_noop_for_empty_input() -> None:
    session = FakeSession()
    notifier = LineNotifier(token="t", session=session)  # type: ignore[arg-type]

    assert notifier.send_lines([]) == 0
    assert session.calls == []
