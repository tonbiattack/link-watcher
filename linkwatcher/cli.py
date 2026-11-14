"""Command-line entry point: fetch, diff, notify, persist."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from . import __version__
from .config import Config, ConfigError
from .notify import LineNotifier, NotifyError
from .watcher import (
    Change,
    FetchError,
    StateError,
    WatchState,
    diff,
    extract_links,
    fetch_html,
    filter_links,
)

LOGGER = logging.getLogger("linkwatcher")

EXIT_OK = 0
EXIT_FAILURE = 1


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the ``link-watcher`` command."""
    parser = argparse.ArgumentParser(
        prog="link-watcher",
        description="Watch a page for new links and notify LINE when they appear.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="Configuration can also come from WATCH_* and LINE_* environment variables.",
    )
    parser.add_argument("url", nargs="?", help="Page to watch (falls back to $WATCH_URL)")
    parser.add_argument("--selector", help="CSS selector for tracked links ($WATCH_SELECTOR)")
    parser.add_argument("--state", help="Path of the JSON state file ($WATCH_STATE_PATH)")
    parser.add_argument("--timeout", type=float, help="HTTP timeout in seconds")
    parser.add_argument(
        "--ignore",
        action="append",
        metavar="REGEX",
        default=[],
        help="Skip links matching this regex. Repeatable.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without sending or saving anything.",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="On the very first run, notify about links that already exist.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="Increase log verbosity: -v for info, -vv for debug.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def configure_logging(verbosity: int) -> None:
    """Configure logging for CLI runs.

    Args:
        verbosity: Number of ``-v`` flags; 0 is WARNING, 1 is INFO, 2+ is DEBUG.
    """
    if verbosity > 1:
        level = logging.DEBUG
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.WARNING

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def resolve_config(args: argparse.Namespace, env: dict[str, str] | None = None) -> Config:
    """Merge CLI arguments over the environment-derived configuration.

    Args:
        args: Parsed command-line arguments.
        env: Environment mapping; defaults to ``os.environ``.

    Returns:
        The effective configuration.

    Raises:
        ConfigError: If no URL is given or ``--timeout`` is not positive.
    """
    config = Config.from_env(env, url_required=False)

    if args.url:
        config = replace(config, url=args.url)
    if args.selector:
        config = replace(config, selector=args.selector)
    if args.state:
        config = replace(config, state_path=Path(args.state))
    if args.ignore:
        config = replace(
            config,
            ignore=config.ignore + tuple(re.compile(pattern) for pattern in args.ignore),
        )
    if args.timeout is not None:
        if args.timeout <= 0:
            raise ConfigError("--timeout must be greater than zero.")
        config = replace(config, timeout=args.timeout)
    if args.dry_run:
        config = replace(config, dry_run=True)
    if args.no_seed:
        config = replace(config, seed=False)

    if not config.url:
        raise ConfigError("A URL is required: pass it as an argument or set WATCH_URL.")

    return config


def run(config: Config, notifier: LineNotifier | None = None) -> Change:
    """Execute one watch cycle.

    The notification is sent before the state is written, so a failed send
    leaves the previous snapshot in place and the same links are reported on
    the next run instead of being silently lost.

    Args:
        config: Effective configuration.
        notifier: Pre-built notifier, mainly for tests.

    Returns:
        The change that was detected.

    Raises:
        FetchError: If the page cannot be downloaded or yields no links.
        StateError: If the state file cannot be read or written.
        NotifyError: If LINE rejects the notification.
    """
    LOGGER.info("Fetching %s", config.url)
    html = fetch_html(config.url, timeout=config.timeout, user_agent=config.user_agent)

    current = filter_links(
        extract_links(html, base_url=config.url, selector=config.selector),
        config.ignore,
    )
    if not current:
        raise FetchError(
            f"No links matched selector {config.selector!r}. "
            "The page layout may have changed, or the selector needs updating."
        )

    state = WatchState.load(config.state_path, expected_url=config.url)
    previous = set(state.links) if state else set()
    change = diff(previous, current)

    if state is None and config.seed:
        LOGGER.info("First run: recorded %d links without notifying.", len(current))
        if not config.dry_run:
            WatchState(config.url, sorted(current)).save(config.state_path)
        return Change()

    if change.is_empty:
        LOGGER.info("No change: %d links unchanged.", len(current))
        return change

    LOGGER.info("Change detected: %d added, %d removed.", len(change.added), len(change.removed))

    if config.dry_run:
        for link in change.added:
            LOGGER.warning("would notify: %s", link)
        for link in change.removed:
            LOGGER.warning("no longer present: %s", link)
        return change

    if change.added:
        notifier = notifier or _build_notifier(config)
        notifier.send_lines(
            change.added,
            header=f"{len(change.added)} new link(s) on {config.url}",
        )

    WatchState(config.url, sorted(current)).save(config.state_path)
    LOGGER.info("State saved with %d links.", len(current))
    return change


def _build_notifier(config: Config) -> LineNotifier:
    """Create a notifier from the configuration.

    Args:
        config: Effective configuration.

    Returns:
        A notifier ready to send messages.

    Raises:
        NotifyError: If no channel access token is configured.
    """
    if not config.token:
        raise NotifyError(
            "Links changed but no LINE token is configured. "
            "Set LINE_CHANNEL_ACCESS_TOKEN (see README)."
        )
    return LineNotifier(token=config.token, recipient=config.recipient, timeout=config.timeout)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Argument list; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: 0 on success (including "no change"), 1 on failure.
    """
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)

    try:
        run(resolve_config(args))
    except (ConfigError, FetchError, StateError, NotifyError) as exc:
        LOGGER.error("%s", exc)
        return EXIT_FAILURE

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
