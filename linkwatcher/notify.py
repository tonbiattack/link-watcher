"""Send notifications through the LINE Messaging API."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

LOGGER = logging.getLogger("linkwatcher.notify")

PUSH_URL = "https://api.line.me/v2/bot/message/push"
BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
MAX_TEXT_LENGTH = 5000
LINE_USER_ID = "U"
LINE_GROUP_ID = "C"
LINE_ROOM_ID = "R"


class NotifyError(RuntimeError):
    """Raised when LINE rejects a message or cannot be reached."""


@dataclass
class LineNotifier:
    """Minimal client for the LINE Messaging API.

    Attributes:
        token: Channel access token.
        recipient: Target user, group or room ID. ``None`` broadcasts to every
            friend of the official account.
        timeout: HTTP timeout in seconds.
        session: Reused ``requests`` session, useful for tests.
    """

    token: str
    recipient: str | None = None
    timeout: float = 30.0
    session: requests.Session | None = None

    def __post_init__(self) -> None:
        if not self.token:
            raise NotifyError("A LINE channel access token is required to send notifications.")
        if self.recipient and not self.recipient.startswith(
            (LINE_USER_ID, LINE_GROUP_ID, LINE_ROOM_ID)
        ):
            raise NotifyError(
                f"LINE_TO must start with U (user), C (group) or R (room). Got {self.recipient!r}."
            )
        self._session = self.session or requests.Session()

    def send(self, text: str) -> bool:
        """Send one text message.

        Args:
            text: Message body. Must be within LINE's 5000 character limit.

        Returns:
            ``True`` once LINE accepted the message.

        Raises:
            NotifyError: If the message is too long, LINE rejects it, or the
                request fails. Callers should treat notification failure as
                fatal so that the run is retried instead of silently skipped.
        """
        if not text.strip():
            raise NotifyError("Refusing to send an empty message.")
        if len(text) > MAX_TEXT_LENGTH:
            raise NotifyError(f"Message is {len(text)} characters; the limit is {MAX_TEXT_LENGTH}.")

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, object] = {"messages": [{"type": "text", "text": text}]}
        url = BROADCAST_URL
        if self.recipient:
            url = PUSH_URL
            payload["to"] = self.recipient

        try:
            response = self._session.post(url, headers=headers, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise NotifyError(f"POST {url} failed: {exc}") from exc

        if response.status_code != 200:
            raise NotifyError(
                f"LINE rejected the message: HTTP {response.status_code} {response.text[:300]}"
            )

        LOGGER.info("Notification sent (%d chars).", len(text))
        return True

    def send_lines(self, lines: list[str], *, header: str | None = None) -> int:
        """Send lines as few messages as possible, splitting on the size limit.

        Args:
            lines: Message lines, one per link.
            header: Optional first line, e.g. a summary.

        Returns:
            The number of messages that were sent.

        Raises:
            NotifyError: If any message is rejected.
        """
        body = [header] if header else []
        body.extend(lines)
        if not body:
            return 0

        batches: list[str] = []
        current: list[str] = []
        current_length = 0

        for line in body:
            addition = len(line) + (1 if current else 0)
            if current and current_length + addition > MAX_TEXT_LENGTH:
                batches.append("\n".join(current))
                current, current_length = [line], len(line)
            else:
                current.append(line)
                current_length += addition

        if current:
            batches.append("\n".join(current))

        for batch in batches:
            self.send(batch)
        return len(batches)
