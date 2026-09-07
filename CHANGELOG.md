# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [1.4.0] - 2026-09-01

### Added
- `flakeradar slow [--top N] [--min-runs N]`: shows the slowest tests by
  average recorded duration. Test durations were already being collected
  on every result but had no way to be surfaced until now.
- The HTML report now includes a "Slowest tests" section, and the JSON
  report includes `avg_duration_seconds` / `max_duration_seconds` per test,
  both using the same previously-unused duration data.
- `flakeradar init --with-ci`: also scaffolds a starter
  `.github/workflows/flakeradar.yml` (history caching, tracked test run,
  quarantine sync, report upload) so new projects don't have to hand-write
  a workflow from scratch. Existing files are left untouched unless
  `--force` is passed.
- `Config.validate()`: flags implausible configuration (thresholds outside
  0.0-1.0, quarantine threshold lower than the flakiness threshold,
  `min_runs` below 1, an unrecognized `llm_provider`). Surfaced via
  `flakeradar doctor`, which now prints config warnings alongside its
  other checks.
- `flakeradar quarantine list --stale-days N` (default 30): flags
  auto-quarantined tests that have sat unaddressed longer than N days, so
  they don't get silently forgotten.

## [1.3.0] - 2026-09-01

### Added
- `flakeradar diff --baseline BRANCH [--head BRANCH] [--fail-on-new]`:
  compares flakiness classification between two branches using the git
  branch already recorded with each run, reporting newly flaky/broken
  tests, fixed tests, and pre-existing (unchanged) flakiness. Informational
  by default; `--fail-on-new` makes it a CI gate.
- `flakeradar report --github-comment`: posts (and keeps updated) a
  summary comment directly on a GitHub pull request, using the token
  GitHub Actions already provides to the job - no secret to configure
  beyond `permissions: pull-requests: write`. See
  `examples/pr-comment-workflow.yml`.
- `flakeradar analyze --all [--out PATH]`: runs AI root-cause analysis on
  every currently flaky/broken test in one pass instead of one at a time,
  optionally writing a consolidated Markdown report.
- `flakeradar doctor [--live]`: checks git availability, pytest
  installation, history database state, quarantine file presence, and LLM
  provider configuration. `--live` additionally makes one real API call to
  confirm provider connectivity.
- `flakeradar import-junit` now also records the git branch (from
  `--git-branch` or auto-detected), so imported historical data can
  participate in `flakeradar diff` too.
- `Storage.history_for` and `Storage.all_nodeids` accept an optional
  `branch` filter, used internally by `diff` but also available for
  custom tooling.

### Fixed
- Tests skipped before they run (e.g. via `@pytest.mark.skip` or a
  `skipif` condition) are now recorded in history as "skipped". Previously
  only `pytest.skip()` called from inside a test body was captured, so
  marker-skipped tests silently never appeared in history at all.

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
