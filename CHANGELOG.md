# Changelog

All notable changes to this project are documented in this file.<br>
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-11-14

### Added

- `link-watcher` CLI and installable `linkwatcher` package
- Link extraction from any CSS selector, with absolute-URL normalization and fragment removal
- JSON snapshot diffing that reports added and removed links
- LINE Messaging API notifications via `push` or `broadcast`, batched under the 5000 character limit
- Configuration through `WATCH_*` and `LINE_*` environment variables or CLI flags
- `--dry-run` to preview changes without sending or saving
- Seed behaviour on first run, so a new setup does not notify about every existing link
- Scheduled GitHub Actions workflow that keeps its snapshot in the Actions cache
- CI workflow running ruff and pytest on Python 3.10, 3.11, 3.12 and 3.13
- 40 unit tests covering extraction, state handling, diffing, notification and the CLI

### Changed

- **BREAKING**: replaced the site-specific `main.py` and `notify.py` with a generic package
- **BREAKING**: state is now `.linkwatch/state.json` instead of `links.csv`
- **BREAKING**: configuration moved from `LINE_TOKEN` to `LINE_CHANNEL_ACCESS_TOKEN` and `LINE_TO`
- Notifications are sent before the snapshot is saved, so a failed send is retried rather than lost
- Notification and fetch failures now exit non-zero instead of being logged and ignored

### Removed

- LINE Notify support, discontinued upstream on 2025-03-31
- The three duplicated monitoring workflows and `runtime.txt`

## [0.1.0] - 2023-12-16

### Added

- Initial script that scraped one hard-coded site and notified LINE Notify about new links
