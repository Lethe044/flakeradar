"""flakeradar command-line interface."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import uuid
import webbrowser
from pathlib import Path
from typing import List, Optional

from . import __version__
from .badge import badge_for_flaky_count
from .clustering import cluster_failures
from .config import Config, load_config
from .gitinfo import current_branch, current_sha
from .llm import LLMError, build_provider, provider_names
from .llm.analyzer import try_analyze_test
from .quarantine import QuarantineEntry, read_quarantine, sync_quarantine, write_quarantine
from .report import generate_html_report, generate_json_report, write_report
from .scoring import FlakinessResult, score_test
from .storage import Storage, TestResult

_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_DIM = "\033[2m"


def _color(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{code}{text}{_RESET}"


def _compute_all_scores(store: Storage, config: Config) -> List[FlakinessResult]:
    results = []
    for nodeid in store.all_nodeids():
        history = store.history_for(nodeid)
        outcomes = [h.outcome for h in history]
        results.append(
            score_test(
                nodeid,
                outcomes,
                min_runs=config.min_runs,
                flakiness_threshold=config.flakiness_threshold,
            )
        )
    return results


# -- subcommands ------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    root = Path.cwd()
    toml_path = root / "flakeradar.toml"
    if toml_path.exists() and not args.force:
        print(f"{toml_path} already exists. Use --force to overwrite.")
        return 1
    toml_path.write_text(
        "# flakeradar configuration\n"
        "# https://github.com/Lethe044/flakeradar\n\n"
        "min_runs = 5\n"
        "flakiness_threshold = 0.15\n"
        "quarantine_threshold = 0.30\n\n"
        "# Leave llm_provider as \"none\" to use flakeradar with zero AI cost.\n"
        "# Options: none, groq, gemini, ollama, openai, anthropic\n"
        "llm_provider = \"none\"\n"
        "# llm_model = \"llama-3.1-8b-instant\"\n\n"
        "report_out = \"flakeradar-report.html\"\n",
        encoding="utf-8",
    )
    gitignore = root / ".gitignore"
    entry = ".flakeradar/history.db\n"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if ".flakeradar/history.db" not in content:
            gitignore.write_text(content.rstrip("\n") + "\n\n# flakeradar\n" + entry, encoding="utf-8")
    else:
        gitignore.write_text("# flakeradar\n" + entry, encoding="utf-8")

    print(f"Created {toml_path}")
    print("Added .flakeradar/history.db to .gitignore (the db is per-machine; commit quarantine.txt instead).")
    print("\nNext steps:")
    print("  1. Run your suite with tracking on:   pytest --flakeradar")
    print("  2. Generate a report:                 flakeradar report --open")
    print("  3. (optional) Configure a free-tier LLM provider for AI root-cause analysis.")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    config = load_config(min_runs=args.min_runs)
    db_path = config.resolve_db_path()
    if not db_path.exists():
        print(f"No history database found at {db_path}. Run 'pytest --flakeradar' first.")
        return 1

    store = Storage(db_path)
    results = _compute_all_scores(store, config)
    histories = {r.nodeid: store.history_for(r.nodeid) for r in results}
    run_count = store.run_count()
    store.close()

    if not results:
        print("No recorded test results yet. Run 'pytest --flakeradar' first.")
        return 1

    if args.format == "json":
        content = generate_json_report(results, run_count, config.flakiness_threshold)
        out_path = Path(args.out or "flakeradar-report.json")
    else:
        content = generate_html_report(
            results, histories, run_count, config.flakiness_threshold, window=args.window
        )
        out_path = Path(args.out or config.report_out)

    write_report(out_path, content)
    print(f"Report written to {out_path.resolve()}")

    flaky = [r for r in results if r.classification == "flaky"]
    broken = [r for r in results if r.classification == "broken"]
    if flaky:
        print(_color(f"\n{len(flaky)} flaky test(s):", _YELLOW))
        for r in sorted(flaky, key=lambda r: -r.score)[:10]:
            print(f"  {_color(f'{r.score:.2f}', _YELLOW)}  {r.nodeid}")
    if broken:
        print(_color(f"\n{len(broken)} consistently failing test(s) (not flaky - likely a real bug):", _RED))
        for r in sorted(broken, key=lambda r: -r.fail_rate)[:10]:
            print(f"  {_color(f'{r.fail_rate:.0%}', _RED)}  {r.nodeid}")

    if args.open and args.format == "html":
        webbrowser.open(out_path.resolve().as_uri())

    exit_code = 0
    if args.max_flaky is not None and len(flaky) > args.max_flaky:
        print(_color(f"\nFAIL: {len(flaky)} flaky test(s) exceeds --max-flaky {args.max_flaky}", _RED))
        exit_code = 1
    if args.max_broken is not None and len(broken) > args.max_broken:
        print(_color(f"FAIL: {len(broken)} broken test(s) exceeds --max-broken {args.max_broken}", _RED))
        exit_code = 1
    return exit_code


def cmd_history(args: argparse.Namespace) -> int:
    config = load_config()
    db_path = config.resolve_db_path()
    if not db_path.exists():
        print(f"No history database found at {db_path}.")
        return 1
    store = Storage(db_path)
    entries = store.history_for(args.nodeid)
    store.close()
    if not entries:
        print(f"No history for '{args.nodeid}'. Check the nodeid (e.g. tests/test_x.py::test_y).")
        return 1
    for e in entries:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.started_at))
        sha = e.git_sha or "-"
        marker = _color("PASS", _GREEN) if e.outcome == "passed" else _color(e.outcome.upper(), _RED)
        print(f"{ts}  {sha:>10}  {marker:<12}  {e.duration:.2f}s")
    outcomes = [e.outcome for e in entries]
    result = score_test(args.nodeid, outcomes, config.min_runs, config.flakiness_threshold)
    print(f"\n{result.total_runs} runs, fail rate {result.fail_rate:.0%}, score {result.score:.2f} -> {result.classification}")
    return 0


def _run_pytest_once(pytest_args: List[str]) -> str:
    """Run pytest once, return the raw outcome ('passed'|'failed'|'error')."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *pytest_args, "-q"],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return "error", "Timed out after 600s"
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0:
        return "passed", output
    return "failed", output


def cmd_stress(args: argparse.Namespace) -> int:
    config = load_config()
    db_path = config.resolve_db_path()
    store = Storage(db_path)

    pytest_args = [args.path]
    if args.k:
        pytest_args += ["-k", args.k]

    run_id = f"stress-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    store.start_run(run_id=run_id, git_sha=current_sha(), git_branch=current_branch(), source="stress")

    print(f"Running {pytest_args} {args.n} time(s)...")
    outcomes = []
    last_failure_output = ""
    for i in range(args.n):
        outcome, output = _run_pytest_once(pytest_args)
        outcomes.append(outcome)
        if outcome != "passed":
            last_failure_output = output
        sys.stdout.write(_color("+", _GREEN) if outcome == "passed" else _color("x", _RED))
        sys.stdout.flush()
    print()

    nodeid = args.k or args.path
    results = [
        TestResult(nodeid=nodeid, outcome=o, duration=0.0, longrepr=last_failure_output if o != "passed" else None)
        for o in outcomes
    ]
    store.record_results(run_id, results)

    history = store.history_for(nodeid)
    all_outcomes = [h.outcome for h in history]
    stats = score_test(nodeid, all_outcomes, config.min_runs, config.flakiness_threshold)

    print(f"\n{stats.pass_count} passed / {stats.fail_count} failed out of {stats.total_runs} total run(s)")
    print(f"Flakiness score: {stats.score:.2f} -> {_color(stats.classification.upper(), _YELLOW)}")

    if args.analyze and stats.classification in ("flaky", "broken"):
        longreprs = [h.longrepr for h in history if h.longrepr]
        clusters = cluster_failures(longreprs)
        provider = build_provider(config)
        analysis, error = try_analyze_test(provider, nodeid, stats, clusters)
        if analysis:
            _print_analysis(analysis)
        elif error:
            print(f"\n(AI analysis skipped: {error})")

    store.close()
    return 0 if stats.classification == "stable" else 1


def cmd_analyze(args: argparse.Namespace) -> int:
    config = load_config(llm_provider=args.llm_provider)
    db_path = config.resolve_db_path()
    if not db_path.exists():
        print(f"No history database found at {db_path}.")
        return 1
    store = Storage(db_path)
    history = store.history_for(args.nodeid)
    store.close()
    if not history:
        print(f"No history for '{args.nodeid}'.")
        return 1

    outcomes = [h.outcome for h in history]
    stats = score_test(args.nodeid, outcomes, config.min_runs, config.flakiness_threshold)
    longreprs = [h.longrepr for h in history if h.longrepr]
    clusters = cluster_failures(longreprs)

    print(f"{args.nodeid}")
    print(f"  runs={stats.total_runs} fail_rate={stats.fail_rate:.0%} score={stats.score:.2f} -> {stats.classification}")
    print(f"  {len(clusters)} distinct failure cluster(s)")

    source_snippet = None
    if args.source:
        src_path = Path(args.source)
        if src_path.is_file():
            source_snippet = src_path.read_text(encoding="utf-8", errors="replace")

    try:
        provider = build_provider(config)
    except LLMError as exc:
        print(f"\nCould not build LLM provider: {exc}")
        return 1

    analysis, error = try_analyze_test(provider, args.nodeid, stats, clusters, source_snippet)
    if analysis:
        _print_analysis(analysis)
        return 0
    print(f"\nAI analysis unavailable: {error}")
    print("(Statistical data above is still valid without AI analysis.)")
    return 1 if not clusters else 0


def _print_analysis(analysis) -> None:
    print(f"\n{_color('AI root cause analysis', _BOLD)} (confidence: {analysis.confidence})")
    print(f"  Category:    {analysis.category_label}")
    print(f"  Explanation: {analysis.explanation}")
    print(f"  Suggested fix: {analysis.suggested_fix}")


def cmd_badge(args: argparse.Namespace) -> int:
    config = load_config()
    db_path = config.resolve_db_path()
    if not db_path.exists():
        print(f"No history database found at {db_path}. Run 'pytest --flakeradar' first.")
        return 1
    store = Storage(db_path)
    results = _compute_all_scores(store, config)
    store.close()

    flaky_count = sum(1 for r in results if r.classification == "flaky")
    svg = badge_for_flaky_count(flaky_count, label=args.label)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")
    print(f"Badge written to {out_path.resolve()} ({flaky_count} flaky test(s))")
    return 0


def cmd_quarantine(args: argparse.Namespace) -> int:
    config = load_config()
    q_path = config.resolve_quarantine_path()

    if args.qcmd == "list":
        entries = read_quarantine(q_path)
        if not entries:
            print("Quarantine list is empty.")
            return 0
        for nodeid, e in sorted(entries.items()):
            tag = _color("[auto]", _DIM) if e.auto else _color("[manual]", _GREEN)
            print(f"{tag} {nodeid}  {('# ' + e.comment) if e.comment else ''}")
        return 0

    if args.qcmd == "add":
        entries = read_quarantine(q_path)
        entries[args.nodeid] = QuarantineEntry(nodeid=args.nodeid, comment=args.reason or "manually pinned", auto=False)
        write_quarantine(q_path, entries.values())
        print(f"Added {args.nodeid} to quarantine.")
        return 0

    if args.qcmd == "remove":
        entries = read_quarantine(q_path)
        if args.nodeid in entries:
            del entries[args.nodeid]
            write_quarantine(q_path, entries.values())
            print(f"Removed {args.nodeid} from quarantine.")
        else:
            print(f"{args.nodeid} was not in the quarantine list.")
        return 0

    if args.qcmd == "sync":
        db_path = config.resolve_db_path()
        if not db_path.exists():
            print(f"No history database found at {db_path}.")
            return 1
        store = Storage(db_path)
        results = _compute_all_scores(store, config)
        store.close()
        diff = sync_quarantine(q_path, results, config.quarantine_threshold, dry_run=args.dry_run)
        prefix = "(dry run) " if args.dry_run else ""
        for nodeid in diff["added"]:
            print(_color(f"{prefix}+ quarantined {nodeid}", _YELLOW))
        for nodeid in diff["removed"]:
            print(_color(f"{prefix}- released {nodeid} (no longer flaky)", _GREEN))
        if not diff["added"] and not diff["removed"]:
            print("Quarantine list is already up to date.")
        elif args.dry_run:
            print("\nNo changes written (--dry-run). Re-run without --dry-run to apply.")
        return 0

    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flakeradar", description="Flaky test detection and diagnosis for pytest.")
    parser.add_argument("--version", action="version", version=f"flakeradar {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a flakeradar.toml config file in the current directory.")
    p_init.add_argument("--force", action="store_true", help="Overwrite an existing config file.")
    p_init.set_defaults(func=cmd_init)

    p_report = sub.add_parser("report", help="Generate the flakiness report from recorded history.")
    p_report.add_argument("--out", default=None, help="Output path (default: from config, or format-specific default).")
    p_report.add_argument("--format", choices=["html", "json"], default="html", help="Report format (default: html).")
    p_report.add_argument("--open", action="store_true", help="Open the HTML report in a browser after generating it.")
    p_report.add_argument("--min-runs", type=int, default=None, help="Minimum runs before a test is classified.")
    p_report.add_argument("--window", type=int, default=40, help="Number of most recent runs shown per sparkline (HTML only).")
    p_report.add_argument("--max-flaky", type=int, default=None, help="Exit non-zero if more than N tests are flaky.")
    p_report.add_argument("--max-broken", type=int, default=None, help="Exit non-zero if more than N tests are consistently failing.")
    p_report.set_defaults(func=cmd_report)

    p_history = sub.add_parser("history", help="Show the recorded pass/fail history for one test.")
    p_history.add_argument("nodeid", help="Test nodeid, e.g. tests/test_x.py::test_y")
    p_history.set_defaults(func=cmd_history)

    p_stress = sub.add_parser("stress", help="Run a test repeatedly right now to quickly check if it's flaky.")
    p_stress.add_argument("path", help="Path to test file or directory (passed through to pytest).")
    p_stress.add_argument("-k", default=None, help="pytest -k expression to select a specific test.")
    p_stress.add_argument("-n", type=int, default=20, help="Number of times to run (default: 20).")
    p_stress.add_argument("--analyze", action="store_true", help="Run AI root-cause analysis if flakiness is found.")
    p_stress.set_defaults(func=cmd_stress)

    p_analyze = sub.add_parser("analyze", help="Run AI root-cause analysis for a specific test's recorded history.")
    p_analyze.add_argument("nodeid", help="Test nodeid, e.g. tests/test_x.py::test_y")
    p_analyze.add_argument("--source", default=None, help="Path to the test's source file, included as context.")
    p_analyze.add_argument(
        "--llm-provider", default=None, choices=[*provider_names(), "none"], help="Override the configured LLM provider."
    )
    p_analyze.set_defaults(func=cmd_analyze)

    p_quarantine = sub.add_parser("quarantine", help="Manage the quarantine list of known-flaky tests.")
    q_sub = p_quarantine.add_subparsers(dest="qcmd", required=True)
    q_sub.add_parser("list", help="List quarantined tests.").set_defaults(func=cmd_quarantine)
    q_sync = q_sub.add_parser("sync", help="Recompute the quarantine list from recorded history.")
    q_sync.add_argument("--dry-run", action="store_true", help="Show what would change without writing the file.")
    q_sync.set_defaults(func=cmd_quarantine)
    q_add = q_sub.add_parser("add", help="Manually pin a test to the quarantine list.")
    q_add.add_argument("nodeid")
    q_add.add_argument("--reason", default=None)
    q_add.set_defaults(func=cmd_quarantine)
    q_remove = q_sub.add_parser("remove", help="Remove a test from the quarantine list.")
    q_remove.add_argument("nodeid")
    q_remove.set_defaults(func=cmd_quarantine)

    p_badge = sub.add_parser("badge", help="Generate a self-contained SVG badge showing the flaky test count.")
    p_badge.add_argument("--out", default="flakeradar-badge.svg", help="Output SVG path (default: flakeradar-badge.svg).")
    p_badge.add_argument("--label", default="flaky tests", help="Badge label text (default: 'flaky tests').")
    p_badge.set_defaults(func=cmd_badge)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
