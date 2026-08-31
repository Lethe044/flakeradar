# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-08-31

### Added
- pytest plugin: `pytest --flakeradar` records every test outcome (pass,
  fail, error, skip) into a local SQLite history database.
- `--flakeradar-quarantine` flag skips tests currently on the quarantine
  list instead of running them, so known-flaky tests don't block CI.
- Flakiness scoring based on outcome transition rate and pass/fail balance,
  distinguishing genuinely flaky tests from consistently broken ones.
- Failure clustering: groups failures of the same test by a normalized
  exception fingerprint, so recurring root causes are easy to spot.
- AI-assisted root cause analysis (`flakeradar analyze`) with pluggable
  providers: Groq, Gemini, and Ollama (all free/no-cost options), plus
  optional OpenAI and Anthropic support for users with their own paid keys.
  Works with zero configuration when no provider is set - statistics and
  reports never require an API key.
- `flakeradar stress` - repeatedly runs a single test right now to get an
  immediate flakiness read, without waiting on historical CI data.
- Self-contained HTML report (`flakeradar report`) with per-test sparkline
  history, sortable columns, and no external CDN or JS dependencies.
- Quarantine management CLI (`flakeradar quarantine list/sync/add/remove`)
  with a human-readable, git-friendly text file format that preserves
  manually pinned entries separately from auto-managed ones.
- `flakeradar init` scaffolds a `flakeradar.toml` config file and updates
  `.gitignore`.
- `flakeradar history <nodeid>` prints the raw pass/fail history for a
  single test.
- Configuration resolution across `flakeradar.toml`, `[tool.flakeradar]` in
  `pyproject.toml`, environment variables, and CLI flags.
- GitHub Actions example workflow demonstrating history persistence across
  CI runs via `actions/cache`.
- Full test suite covering scoring, clustering, storage, config resolution,
  quarantine sync, report generation, the AI analyzer, and the pytest
  plugin itself (via `pytester`).
