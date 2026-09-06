# flakeradar

Flaky test detection, historical tracking, and AI-assisted root cause analysis for pytest.

[![CI](https://github.com/Lethe044/flakeradar/actions/workflows/ci.yml/badge.svg)](https://github.com/Lethe044/flakeradar/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/radarflake.svg)](https://pypi.org/project/radarflake/)
[![Python versions](https://img.shields.io/pypi/pyversions/radarflake.svg)](https://pypi.org/project/radarflake/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A test that fails one run in twenty and passes the other nineteen is worse
than a test that always fails. The always-failing test gets fixed the same
day. The occasional failure gets re-run, ignored, and eventually nobody
trusts a red CI run again.

flakeradar tracks every test run over time, tells you which tests are
actually flaky versus just plain broken, clusters the failures by root
cause, and can optionally ask a free-tier LLM to explain what's probably
going wrong, all without requiring a paid API key or a hosted service.

## Why not just re-run failed tests?

Retrying failures hides the problem instead of measuring it. flakeradar
takes a different approach:

- **It measures flakiness properly.** A test that fails 100% of the time
  isn't flaky, it's broken. flakeradar's scoring is based on how often a
  test's outcome *flips* between runs, not just its raw failure rate, so
  real bugs and genuine flakiness get classified differently.
- **It keeps history, not just the current run.** Flakiness usually only
  becomes obvious over dozens of runs. flakeradar persists results to a
  local SQLite database so trends build up across CI runs, not just within
  one `pytest` invocation.
- **It doesn't require an API key to be useful.** The scoring, clustering,
  quarantine list, and HTML report all work with zero configuration. AI
  root cause analysis is an optional layer on top, and it works with free
  tiers (Groq, Gemini) or a fully local model (Ollama), not just paid APIs.
- **It stays out of your way in CI.** Quarantined tests are skipped, not
  deleted or silently ignored. The quarantine list is a plain text file
  meant to be reviewed in code review, with auto-added and manually pinned
  entries kept clearly separate.

## Installation

```bash
pip install radarflake
```

The PyPI distribution is named `radarflake` (the original `flakeradar` name
was already taken by an unrelated project). Everything else - the CLI
command, the `import flakeradar` module name, and the `pytest --flakeradar`
flag - is unaffected.

Requires Python 3.9 or newer and pytest 7 or newer. No other required
dependencies beyond `requests` for optional AI calls.

## Quickstart

```bash
# 1. Scaffold a config file (optional but recommended)
flakeradar init

# 2. Run your test suite with tracking enabled
pytest --flakeradar

# Run it a few more times (or let it run over a few days of CI) so there's
# enough history to classify tests confidently.
pytest --flakeradar
pytest --flakeradar

# 3. See what's flaky
flakeradar report --open
```

The report is a single self-contained HTML file. No CDN calls, no external
JavaScript, safe to attach to a ticket or open with no internet connection.

### Don't want to wait for CI history to build up?

Stress-test a specific test right now by running it repeatedly:

```bash
flakeradar stress tests/test_checkout.py -k test_apply_discount -n 30 --analyze
```

This runs the test 30 times in a row, records the outcomes, prints a
flakiness score immediately, and (with `--analyze` and a provider
configured) asks an LLM for a root cause hypothesis.

Try it on the bundled example file to see the whole flow without touching
your own test suite:

```bash
flakeradar stress examples/demo_flaky_tests.py -k test_race_condition -n 30
flakeradar report --open
```

## How flakiness is scored

Each test gets a score from 0.0 to 1.0, combining two signals:

- **Transition rate**: how often the outcome flips from one run to the
  next. A test that alternates pass, fail, pass, fail has a transition
  rate of 1.0. A test that's always green (or always red) has a
  transition rate of 0.0.
- **Balance**: how close the pass/fail split is to 50/50, which is the
  pattern most associated with genuine non-determinism.

```
score = 0.6 x transition_rate + 0.4 x balance
```

Tests are then classified as:

| Classification     | Meaning                                                        |
|---------------------|------------------------------------------------------------------|
| `stable`            | Consistently passing (or consistently skipped)                  |
| `flaky`              | Score at or above the threshold (default `0.15`)                |
| `broken`             | Fails almost every run with little to no flipping - likely a real bug, not flakiness |
| `insufficient_data` | Fewer recorded runs than `min_runs` (default `5`)                |

Both thresholds are configurable in `flakeradar.toml`.

## AI-assisted root cause analysis

Statistics tell you *that* a test is flaky. The AI layer is an optional
extra step that tries to explain *why*, by looking at the clustered
failure tracebacks and (if you point it at the source file) the test code
itself.

```bash
flakeradar analyze tests/test_checkout.py::test_apply_discount --source tests/test_checkout.py
```

Example output:

```
tests/test_checkout.py::test_apply_discount
  runs=24 fail_rate=29% score=0.41 -> flaky
  2 distinct failure cluster(s)

AI root cause analysis (confidence: high)
  Category:    Race condition
  Explanation: The two failure clusters both involve the discount total
               being read before the async cart update finishes, which
               matches an unawaited coroutine in apply_discount().
  Suggested fix: Await cart.update() before reading cart.total in the
                 discount calculation, or add an explicit synchronization
                 point in the test fixture.
```

### Supported providers

| Provider    | Cost                          | Setup                                              |
|-------------|--------------------------------|-----------------------------------------------------|
| `groq`      | Free tier                      | `FLAKERADAR_LLM_PROVIDER=groq`, `GROQ_API_KEY=...`   |
| `gemini`    | Free tier                      | `FLAKERADAR_LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...` |
| `ollama`    | Free, fully local, no API key  | `FLAKERADAR_LLM_PROVIDER=ollama` (Ollama running locally) |
| `openai`    | Paid, bring your own key       | `FLAKERADAR_LLM_PROVIDER=openai`, `OPENAI_API_KEY=...` |
| `anthropic` | Paid, bring your own key       | `FLAKERADAR_LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=...` |

If `llm_provider` is left as `none` (the default), everything except
`flakeradar analyze`'s AI section still works normally, the statistical
output is always shown regardless of whether AI analysis succeeds.

Got more than one flaky test piling up? Analyze all of them in one pass
instead of calling `analyze` repeatedly:

```bash
flakeradar analyze --all --out flaky-analysis.md
```

## Quarantining flaky tests

Once a test is confirmed flaky, you usually don't want it blocking merges
while someone investigates. flakeradar can auto-manage a quarantine list:

```bash
flakeradar quarantine sync     # add/remove tests based on current scores
flakeradar quarantine list     # see what's currently quarantined and why
```

Then, in CI, skip quarantined tests instead of letting them fail the build:

```bash
pytest --flakeradar --flakeradar-quarantine
```

The quarantine file (`.flakeradar/quarantine.txt`) is plain text and meant
to be committed to version control:

```
tests/test_payments.py::test_webhook_retry  # score=0.42, auto-added 2026-08-20
tests/test_upload.py::test_large_file       # manually pinned, see #482
```

Entries with an `auto-added` comment are managed automatically by
`flakeradar quarantine sync` and get removed once a test stabilizes.
Entries without that marker are treated as manually pinned and are never
touched by `sync`, so a human decision to hold a test back doesn't get
silently reverted.

Preview changes before committing to them:

```bash
flakeradar quarantine sync --dry-run
```

## Visibility in CI

Two lightweight extras help flakiness stay visible without anyone having
to remember to open the HTML report.

**Job summaries.** When `pytest --flakeradar` runs inside GitHub Actions,
it automatically writes a short Markdown summary of that run's failing
tests - flagged as known-flaky, consistently-failing, or unexpectedly
failing - to the job summary tab. No configuration needed; it activates
whenever `GITHUB_STEP_SUMMARY` is set.

**A status badge.** Generate a small, self-contained SVG badge showing the
current flaky test count:

```bash
flakeradar badge --out flakeradar-badge.svg
```

The badge has no external service dependency, it's rendered entirely
locally. Commit it or upload it as a CI artifact and reference it from
your README:

```markdown
![flaky tests](flakeradar-badge.svg)
```

**A CI health gate.** Separate from per-test quarantine, you can fail a
build outright if overall flakiness crosses a budget:

```bash
flakeradar report --max-flaky 5 --max-broken 0
```

**Machine-readable output.** For custom dashboards or other tooling:

```bash
flakeradar report --format json --out flakeradar-report.json
```

**Chat notifications.** Post a summary to Slack (or any Slack-compatible
incoming webhook, which also covers Discord and Mattermost) whenever you
generate a report:

```bash
flakeradar report --webhook https://hooks.slack.com/services/...
```

Set it once in `flakeradar.toml` (`webhook_url = "..."`) or via
`FLAKERADAR_WEBHOOK_URL` and it applies automatically to every
`flakeradar report` run, no flag needed.

**PR comments.** Post (and keep updated) a summary comment directly on the
pull request that's being tested:

```bash
flakeradar report --github-comment
```

This only activates when running inside a GitHub Actions job triggered by
a `pull_request` event, using the token GitHub already provides to the
job (`github.token` / `GITHUB_TOKEN` - not a secret you have to create).
The job needs `permissions: pull-requests: write`. See
[`examples/pr-comment-workflow.yml`](examples/pr-comment-workflow.yml) for
a complete example. Re-running on the same PR updates the existing
comment instead of piling up new ones.

## Comparing branches

Separate from historical trend tracking, `flakeradar diff` answers a more
specific question: did *this* branch introduce flakiness that doesn't
exist on the baseline? It compares classification per test between two
branches using the git branch already recorded with each run:

```bash
flakeradar diff --baseline main --head my-feature-branch --fail-on-new
```

This reports newly flaky or newly broken tests (present on `--head` but
not on `--baseline`), tests that were flaky on the baseline but are fixed
on `--head`, and pre-existing flakiness that's unchanged on both. Without
`--head`, it uses the current git branch. `--fail-on-new` is opt-in - by
default the command is informational only and always exits 0, so it's
safe to try without risking an unexpected CI failure.

Note this needs history recorded under both branch names already (from
`pytest --flakeradar` runs, or `flakeradar import-junit`), so it's most
useful once your baseline branch has accumulated some runs.

## Working with non-pytest suites and old CI logs

flakeradar's live tracking (`pytest --flakeradar`) is pytest-specific, but
its history database isn't. `flakeradar import-junit` reads a JUnit XML
report and records it as a run, which works with anything that can emit
JUnit-style XML - Jest, Go test, JUnit/Java, RSpec, and most other test
runners - and also lets you backfill history from old CI artifacts that
predate adopting flakeradar:

```bash
flakeradar import-junit path/to/junit-results.xml
flakeradar report --open
```

Run it once per historical CI run you want counted (e.g. loop over
archived JUnit XML artifacts from the last few weeks) to seed enough
history for meaningful scores immediately, instead of waiting for new
runs to accumulate.

## Keeping the database tidy

On a long-lived project, the history database grows by one row per test
per run. Trim it periodically (e.g. in a scheduled CI job) if that
matters to you:

```bash
flakeradar prune --keep 500
```

This keeps the 500 most recent runs and drops everything older.

## CI integration

flakeradar's own database is per-machine by default, so in CI you need to
persist it between runs (otherwise every run starts from zero history).
Here's a minimal GitHub Actions example; a fuller version with quarantine
sync and report upload lives in
[`examples/github-workflow-example.yml`](examples/github-workflow-example.yml)
(copy it into your own project's `.github/workflows/`, it is not an active
workflow in this repo).

```yaml
- name: Restore flaky-test history
  uses: actions/cache@v4
  with:
    path: .flakeradar/history.db
    key: flakeradar-history-${{ github.ref_name }}
    restore-keys: flakeradar-history-main

- name: Run tests with tracking
  run: pytest --flakeradar --flakeradar-quarantine

- name: Save updated history
  uses: actions/cache/save@v4
  if: always()
  with:
    path: .flakeradar/history.db
    key: flakeradar-history-${{ github.ref_name }}-${{ github.run_id }}
```

## Configuration reference

flakeradar reads configuration from, in order of priority (highest first):

1. CLI flags
2. Environment variables (`FLAKERADAR_*`)
3. `flakeradar.toml` in the project root
4. `[tool.flakeradar]` in `pyproject.toml`
5. Built-in defaults

See [`flakeradar.toml.example`](flakeradar.toml.example) for every
available option with comments.

## CLI reference

```
flakeradar init                          Scaffold a flakeradar.toml config file
flakeradar report [--open] [--out PATH] [--format html|json] [--max-flaky N] [--max-broken N]
                                          Generate the flakiness report
flakeradar history <nodeid>              Print raw pass/fail history for one test
flakeradar stress <path> [-k EXPR] [-n N] [--analyze]
                                          Run a test repeatedly right now
flakeradar analyze <nodeid> [--source PATH]
                                          AI root cause analysis for one test
flakeradar analyze --all [--out PATH]    AI root cause analysis for every flaky/broken test
flakeradar quarantine list|sync [--dry-run]|add|remove
                                          Manage the quarantine list
flakeradar badge [--out PATH] [--label TEXT]
                                          Generate an SVG flaky-test-count badge
flakeradar prune --keep N                Delete run history beyond the N most recent runs
flakeradar import-junit <path> [--run-id ID] [--git-sha SHA] [--git-branch BRANCH]
                                          Import a JUnit XML report as a run
flakeradar diff --baseline BRANCH [--head BRANCH] [--fail-on-new]
                                          Compare flakiness between two branches
flakeradar doctor [--live]                Check your setup (git, pytest, history db, LLM config)
```

Run `flakeradar <command> --help` for the full set of flags on any
subcommand.

## Troubleshooting your setup

```bash
flakeradar doctor
```

Checks that git is available, whether pytest is installed, the state and
size of your history database, whether a quarantine file exists, and
whether your configured LLM provider looks correctly set up (add `--live`
to make one real API call and confirm connectivity, rather than just
checking that a key is present).

## FAQ

**Does this slow down my test suite?**
`pytest --flakeradar` only adds an in-memory hook that records outcomes and
writes them once at the end of the session. The overhead is negligible for
any suite where the tests themselves take more than a few milliseconds
each.

**Does it work with `pytest-xdist`?**
Yes. `Storage` opens SQLite in WAL mode with a busy timeout, so multiple
worker processes recording results concurrently don't hit "database is
locked" errors. Note that `--flakeradar-quarantine` marks are applied at
collection time on each worker, so quarantine changes made mid-run by
another process won't retroactively apply within that same session.

**Where is the data stored?**
Locally, in a SQLite file at `.flakeradar/history.db` by default. Nothing
is sent anywhere unless you explicitly enable an AI provider, in which
case only the specific failure tracebacks and test name for the test
you're analyzing are sent to that provider, never your whole suite.

**What happens if I don't configure an LLM provider?**
Everything works except the AI explanation text. Scoring, history,
reports, and quarantine management have no dependency on AI at all.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for how
to get set up and what to keep in mind before opening a pull request.

## License

MIT. See [LICENSE](LICENSE).
