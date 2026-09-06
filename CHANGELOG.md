# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-09-01

### Added
- `flakeradar import-junit <path>`: import a JUnit XML report as a run in
  history. Works with any test runner that can emit JUnit-style XML (Jest,
  Go test, JUnit/Java, RSpec, and more), not just pytest, and can also be
  used to backfill history from old CI artifacts predating adoption of the
  pytest plugin.
- `flakeradar prune --keep N`: delete old run history beyond the N most
  recent runs, so the database doesn't grow unbounded on long-lived
  projects.
- `flakeradar report --webhook URL` (or a `webhook_url` in
  `flakeradar.toml` / `FLAKERADAR_WEBHOOK_URL`): posts a Slack-compatible
  summary of flaky and consistently-failing tests to a webhook after
  generating a report.
- HTML report now includes a trend section showing failing-test count per
  run over time, in addition to the existing per-test sparklines.

### Changed
- `Storage` now opens its SQLite connection in WAL mode with a busy
  timeout, so concurrent writers (e.g. multiple `pytest-xdist` workers
  each recording results) no longer risk "database is locked" errors.

## [1.1.1] - 2026-09-01

### Changed
- Renamed the PyPI distribution to `radarflake` - the `flakeradar` name on
  PyPI was already taken by an unrelated project. This is a packaging-only
  change: install with `pip install radarflake`, everything else (the
  `flakeradar` CLI command, `import flakeradar`, and the
  `pytest --flakeradar` flag) is unchanged.

## [1.1.0] - 2026-08-31

### Added
- GitHub Actions Job Summary integration: `pytest --flakeradar` now writes
  a Markdown table of this run's non-passing tests (with their historical
  classification - known flaky, consistently failing, or unexpectedly
  failing) directly to the Actions job summary tab when running in CI.
  No configuration needed - it activates automatically when
  `GITHUB_STEP_SUMMARY` is set.
- `flakeradar badge`: generates a self-contained SVG badge showing the
  current flaky test count, with no external network call or hosted
  service dependency. Colored green/yellow/red based on count.
- `flakeradar report --format json`: machine-readable JSON export of the
  same data shown in the HTML report, for custom dashboards or other
  tooling.
- `flakeradar report --max-flaky N` / `--max-broken N`: exit with a
  non-zero status if the number of flaky or consistently-failing tests
  exceeds a given budget, independent of per-test quarantine thresholds.
  Useful as a CI gate on overall suite health.
- `flakeradar quarantine sync --dry-run`: preview what would be added to
  or removed from the quarantine list without writing any changes.

### Fixed
- Moved the downstream-usage example GitHub Actions workflow out of
  `.github/workflows/` (it was being picked up and run as if it were
  this repo's own CI). It now lives in `examples/github-workflow-example.yml`
  as a copy-paste template only.

## [1.0.1] - 2026-08-31

### Fixed
- `Storage.start_run`: a run started at `started_at=0.0` was silently
  replaced with the current wall-clock time, because `0.0 or time.time()`
  treats zero as falsy in Python. This corrupted run ordering for any
  caller passing an explicit zero timestamp. Now only `None` triggers the
  wall-clock fallback.
- `sync_quarantine`: auto-quarantined tests that stabilized (no longer
  flaky) were correctly removed from the quarantine file, but the reported
  `removed` list stayed empty because of an ordering bug in how dropped
  entries were tracked. The list now correctly reports every auto-added
  test that was released.
- Added `__test__ = False` to the internal `TestResult` dataclass so
  pytest no longer emits a `PytestCollectionWarning` for it (it was being
  mistaken for a test class because of its name).

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
