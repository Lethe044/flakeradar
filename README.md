# flakeradar

Flaky test detection, historical tracking, and AI-assisted root cause analysis for pytest.

[![CI](https://github.com/Lethe044/flakeradar/actions/workflows/ci.yml/badge.svg)](https://github.com/Lethe044/flakeradar/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/flakeradar.svg)](https://pypi.org/project/flakeradar/)
[![Python versions](https://img.shields.io/pypi/pyversions/flakeradar.svg)](https://pypi.org/project/flakeradar/)
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
pip install flakeradar
```

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
flakeradar report [--open] [--out PATH]  Generate the HTML flakiness report
flakeradar history <nodeid>              Print raw pass/fail history for one test
flakeradar stress <path> [-k EXPR] [-n N] [--analyze]
                                          Run a test repeatedly right now
flakeradar analyze <nodeid> [--source PATH]
                                          AI root cause analysis for one test
flakeradar quarantine list|sync|add|remove
                                          Manage the quarantine list
```

Run `flakeradar <command> --help` for the full set of flags on any
subcommand.

## FAQ

**Does this slow down my test suite?**
`pytest --flakeradar` only adds an in-memory hook that records outcomes and
writes them once at the end of the session. The overhead is negligible for
any suite where the tests themselves take more than a few milliseconds
each.

**Does it work with `pytest-xdist`?**
Yes, results from parallel workers are recorded the same way as a
sequential run. Note that `--flakeradar-quarantine` marks are applied at
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
