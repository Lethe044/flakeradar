# Contributing to flakeradar

Thanks for considering a contribution. This project is small on purpose, so
even a modest change is usually visible and appreciated.

## Getting set up

```bash
git clone https://github.com/Lethe044/flakeradar.git
cd flakeradar
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest -v
```

Try the CLI against the bundled demo tests:

```bash
flakeradar init
flakeradar stress examples/demo_flaky_tests.py -k test_race_condition -n 30
flakeradar report --open
```

## Project layout

```
src/flakeradar/
  cli.py          entry point for the `flakeradar` command
  plugin.py       the pytest plugin (--flakeradar, --flakeradar-quarantine)
  storage.py      SQLite history storage
  scoring.py      flakiness scoring algorithm
  clustering.py   failure fingerprinting/clustering
  quarantine.py   quarantine list read/write/sync
  report.py       self-contained HTML report generation
  config.py       config file / env var resolution
  llm/            provider implementations (groq, gemini, ollama, openai, anthropic)
```

## Guidelines

- **No required paid dependency.** Anything that needs a paid API key must
  be optional, with the tool remaining fully useful (statistics, reports,
  quarantine) without it.
- **Keep the HTML report self-contained.** No CDN links, no external JS
  frameworks - it should render correctly with zero network access.
- **New LLM providers** should live in `src/flakeradar/llm/` and implement
  the `LLMProvider` interface in `llm/base.py`. Register them in
  `llm/__init__.py`.
- Add tests for new behavior. The test suite doesn't need to be exhaustive,
  but a change with zero test coverage is unlikely to be merged as-is.
- Keep pull requests focused. Larger changes are easier to review (and more
  likely to get merged) when split into smaller, self-contained PRs.

## Reporting bugs

Please include:
- flakeradar version (`flakeradar --version`)
- Python version and OS
- The command you ran and what you expected vs. what happened
- If relevant, the contents of `flakeradar.toml` (redact any API keys)

## Feature ideas

Open an issue before starting significant work on a new feature so we can
discuss the approach first. Small fixes and clear bugs don't need this step.

## Code of conduct

Be respectful. Assume good faith. Disagreements about code are fine;
personal attacks are not.
