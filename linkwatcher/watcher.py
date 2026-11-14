"""Fetch a page, extract its links and compare them with the previous snapshot."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

SKIPPED_SCHEMES = frozenset({"javascript", "mailto", "tel", "data", "sms", "blob"})


class FetchError(RuntimeError):
    """Raised when the watched page cannot be downloaded."""


class StateError(RuntimeError):
    """Raised when the state file is unreadable or corrupt."""


def fetch_html(url: str, *, timeout: float, user_agent: str) -> str:
    """Download ``url`` and return its HTML.

    Args:
        url: Page to download.
        timeout: HTTP timeout in seconds.
        user_agent: User-Agent header value.

    Returns:
        The decoded HTML document.

    Raises:
        FetchError: If the request fails or the server returns an error status.
    """
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - scheme checked by caller
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise FetchError(f"GET {url} failed: {exc}") from exc


def extract_links(html: str, *, base_url: str, selector: str) -> set[str]:
    """Collect absolute, de-duplicated link targets from an HTML document.

    Fragments are removed so that ``#anchor`` variations of one page are not
    reported as separate links, and non-navigable schemes are skipped.

    Args:
        html: HTML document.
        base_url: URL used to resolve relative links.
        selector: CSS selector. Elements are matched and their ``href`` read.

    Returns:
        The set of absolute link targets found in the document.
    """
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()

    for element in soup.select(selector):
        href = element.get("href")
        if not href or not isinstance(href, str):
            continue

        absolute = urljoin(base_url, href.strip())
        absolute, _ = urldefrag(absolute)
        parsed = urlparse(absolute)

        if parsed.scheme not in {"http", "https"} or parsed.scheme in SKIPPED_SCHEMES:
            continue
        if not parsed.netloc:
            continue

        links.add(
            urlunparse(parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower()))
        )

    return links


def filter_links(links: Iterable[str], patterns: Iterable[re.Pattern[str]]) -> set[str]:
    """Drop links matching any of ``patterns``.

    Args:
        links: Candidate links.
        patterns: Compiled regular expressions matched against each link.

    Returns:
        The links that matched no pattern.
    """
    compiled = list(patterns)
    if not compiled:
        return set(links)
    return {link for link in links if not any(p.search(link) for p in compiled)}


@dataclass(frozen=True)
class Change:
    """The difference between two snapshots of a page."""

    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Whether both snapshots contained exactly the same links."""
        return not self.added and not self.removed


@dataclass
class WatchState:
    """Persisted snapshot of the links seen on the previous run."""

    url: str
    links: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path, *, expected_url: str) -> WatchState | None:
        """Read the state file.

        Args:
            path: State file location.
            expected_url: URL the state is expected to belong to.

        Returns:
            The stored state, or ``None`` when the file does not exist yet.

        Raises:
            StateError: If the file is not valid state for this URL.
        """
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StateError(f"Cannot read {path}: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StateError(f"{path} is not valid JSON: {exc}") from exc

        if not isinstance(data, dict) or not isinstance(data.get("links"), list):
            raise StateError(f"{path} does not contain a 'links' list.")

        stored_url = data.get("url")
        if stored_url and stored_url != expected_url:
            raise StateError(
                f"{path} belongs to {stored_url!r}, but the configured URL is "
                f"{expected_url!r}. Delete the file to start over."
            )

        links = [link for link in data["links"] if isinstance(link, str)]
        return cls(url=expected_url, links=sorted(set(links)))

    def save(self, path: Path) -> None:
        """Write the state atomically so a crash cannot leave a partial file.

        Args:
            path: State file location.

        Raises:
            StateError: If the file cannot be written.
        """
        payload = json.dumps(
            {"url": self.url, "links": sorted(set(self.links))},
            ensure_ascii=False,
            indent=2,
        )
        temporary = path.with_name(path.name + ".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(payload + "\n", encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            raise StateError(f"Cannot write {path}: {exc}") from exc


def diff(previous: Iterable[str], current: Iterable[str]) -> Change:
    """Compare two link sets.

    Args:
        previous: Links seen on the previous run.
        current: Links seen now.

    Returns:
        The added and removed links, each sorted for stable output.
    """
    before, now = set(previous), set(current)
    return Change(added=sorted(now - before), removed=sorted(before - now))
