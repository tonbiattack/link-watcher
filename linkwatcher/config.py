"""Application configuration, read from environment variables and CLI arguments."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_SELECTOR = "a[href]"
DEFAULT_STATE_PATH = Path(".linkwatch/state.json")
DEFAULT_TIMEOUT = 30.0
DEFAULT_USER_AGENT = (
    "link-watcher/1.0 (+https://github.com/tonbiattack/link-watcher) "
    "Mozilla/5.0 (compatible; link-watcher)"
)


class ConfigError(ValueError):
    """Raised when the configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    """Runtime configuration for a single watch run.

    Attributes:
        url: Page to watch.
        selector: CSS selector whose matched elements provide the tracked links.
        state_path: JSON file holding the previously seen links.
        token: LINE Messaging API channel access token.
        recipient: LINE user, group or room ID. ``None`` broadcasts.
        timeout: HTTP timeout in seconds.
        user_agent: User-Agent header sent to the watched page.
        dry_run: Log what would happen without sending or writing anything.
        seed: On first run, record links without notifying.
        ignore: Regular expressions; matching URLs are dropped.
    """

    url: str = ""
    selector: str = DEFAULT_SELECTOR
    state_path: Path = DEFAULT_STATE_PATH
    token: str | None = None
    recipient: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    user_agent: str = DEFAULT_USER_AGENT
    dry_run: bool = False
    seed: bool = True
    ignore: tuple[re.Pattern[str], ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, *, url_required: bool = True) -> Config:
        """Build a configuration from ``WATCH_*`` and ``LINE_*`` environment variables.

        Args:
            env: Mapping to read from. Defaults to ``os.environ``.
            url_required: Whether ``WATCH_URL`` must be present. The CLI passes
                ``False`` when the URL is supplied as an argument instead.

        Returns:
            The parsed configuration.

        Raises:
            ConfigError: If required values are missing or malformed.
        """
        source = os.environ if env is None else env
        url = (source.get("WATCH_URL") or "").strip()
        if url_required and not url:
            raise ConfigError("WATCH_URL is required (the page to watch).")

        raw_timeout = (source.get("WATCH_TIMEOUT") or "").strip()
        try:
            timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT
        except ValueError as exc:
            raise ConfigError(f"WATCH_TIMEOUT must be a number, got {raw_timeout!r}.") from exc
        if timeout <= 0:
            raise ConfigError("WATCH_TIMEOUT must be greater than zero.")

        patterns = tuple(
            re.compile(p) for p in (source.get("WATCH_IGNORE") or "").splitlines() if p.strip()
        )

        return cls(
            url=url,
            selector=(source.get("WATCH_SELECTOR") or DEFAULT_SELECTOR).strip(),
            state_path=Path(source.get("WATCH_STATE_PATH") or DEFAULT_STATE_PATH),
            token=(source.get("LINE_CHANNEL_ACCESS_TOKEN") or "").strip() or None,
            recipient=(source.get("LINE_TO") or "").strip() or None,
            timeout=timeout,
            user_agent=(source.get("WATCH_USER_AGENT") or DEFAULT_USER_AGENT).strip(),
            dry_run=_as_bool(source.get("WATCH_DRY_RUN")),
            seed=not _as_bool(source.get("WATCH_NO_SEED")),
            ignore=patterns,
        )


def _as_bool(value: str | None) -> bool:
    """Interpret common truthy strings from the environment."""
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}
