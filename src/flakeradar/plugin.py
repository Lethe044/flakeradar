"""pytest plugin entry point.

Enable with `pytest --flakeradar`. Every test outcome from that run is
recorded to the local history database so that `flakeradar report` and
`flakeradar analyze` have data to work with over time (e.g. across nightly
CI runs). This hook does not slow down or change test behavior - it is
purely an observer, unless `--flakeradar-quarantine` is also passed, in
which case tests on the quarantine list are skipped instead of run.
"""

from __future__ import annotations

import time
import uuid
from typing import Dict, List

import pytest

from .config import load_config
from .gitinfo import current_branch, current_sha
from .ignore import matches_ignore
from .quarantine import read_quarantine
from .storage import Storage, TestResult
from .summary import build_run_summary_markdown, write_github_step_summary

_RUN_ID_KEY = "flakeradar_run_id"


def pytest_addoption(parser: "pytest.Parser") -> None:
    group = parser.getgroup("flakeradar")
    group.addoption(
        "--flakeradar",
        action="store_true",
        default=False,
        help="Record this test run's outcomes into the flakeradar history database.",
    )
    group.addoption(
        "--flakeradar-quarantine",
        action="store_true",
        default=False,
        help="Skip tests currently on the flakeradar quarantine list instead of running them.",
    )
    group.addoption(
        "--flakeradar-db",
        action="store",
        default=None,
        help="Override the flakeradar history database path.",
    )


def pytest_configure(config: "pytest.Config") -> None:
    if not config.getoption("--flakeradar"):
        return
    fr_config = load_config(db_path=config.getoption("--flakeradar-db"))
    config._flakeradar_config = fr_config  # type: ignore[attr-defined]
    config._flakeradar_results = []  # type: ignore[attr-defined]
    config._flakeradar_run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"  # type: ignore[attr-defined]

    store = Storage(fr_config.resolve_db_path())
    store.start_run(
        run_id=config._flakeradar_run_id,  # type: ignore[attr-defined]
        git_sha=current_sha(),
        git_branch=current_branch(),
        source="pytest",
    )
    store.close()


def pytest_collection_modifyitems(config: "pytest.Config", items: list) -> None:
    if not config.getoption("--flakeradar-quarantine"):
        return
    fr_config = load_config(db_path=config.getoption("--flakeradar-db"))
    quarantined = read_quarantine(fr_config.resolve_quarantine_path())
    if not quarantined:
        return
    skip_marker = pytest.mark.skip(reason="flakeradar: quarantined as flaky (see .flakeradar/quarantine.txt)")
    for item in items:
        if item.nodeid in quarantined:
            item.add_marker(skip_marker)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: "pytest.Item", call: "pytest.CallInfo") -> None:
    outcome = yield
    report = outcome.get_result()

    config = item.config
    if not config.getoption("--flakeradar"):
        return
    if not hasattr(config, "_flakeradar_results"):
        return

    if matches_ignore(item.nodeid, config._flakeradar_config.ignore):  # type: ignore[attr-defined]
        return

    # Only record the "call" phase as pass/fail; setup/teardown errors are
    # recorded as "error" so they are distinguishable but still contribute
    # to the flakiness signal. Tests skipped before they even run (e.g. via
    # @pytest.mark.skip or a skipif condition) only produce a "setup"
    # report, never a "call" report, so that case is handled separately -
    # otherwise marker-skipped tests would silently never appear in history
    # at all, unlike an inline pytest.skip() call (which does go through
    # "call" and was already covered).
    if report.when == "call":
        outcome_str = report.outcome  # passed | failed | skipped
    elif report.when in ("setup", "teardown") and report.failed:
        outcome_str = "error"
    elif report.when == "setup" and report.skipped:
        outcome_str = "skipped"
    else:
        return

    longrepr = None
    if report.longrepr is not None:
        try:
            longrepr = str(report.longrepr)
        except Exception:  # pragma: no cover - defensive
            longrepr = repr(report.longrepr)

    location = report.location  # (file, lineno, domain)
    result = TestResult(
        nodeid=report.nodeid,
        outcome=outcome_str,
        duration=getattr(report, "duration", 0.0) or 0.0,
        longrepr=longrepr,
        file=location[0] if location else None,
        line=(location[1] + 1) if location and location[1] is not None else None,
    )
    config._flakeradar_results.append(result)  # type: ignore[attr-defined]


def pytest_sessionfinish(session: "pytest.Session", exitstatus: int) -> None:
    config = session.config
    if not config.getoption("--flakeradar"):
        return
    if not hasattr(config, "_flakeradar_results"):
        return

    results: List[TestResult] = config._flakeradar_results  # type: ignore[attr-defined]
    if not results:
        return

    fr_config = config._flakeradar_config  # type: ignore[attr-defined]
    run_id = config._flakeradar_run_id  # type: ignore[attr-defined]

    store = Storage(fr_config.resolve_db_path())
    store.record_results(run_id, results)

    summary_md = build_run_summary_markdown(
        store, results, fr_config.min_runs, fr_config.flakiness_threshold
    )
    write_github_step_summary(summary_md)
    store.close()

    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        fail_like = sum(1 for r in results if r.outcome in ("failed", "error"))
        reporter.write_sep("-", "flakeradar")
        reporter.write_line(
            f"flakeradar: recorded {len(results)} result(s) "
            f"({fail_like} failing/error) to {fr_config.resolve_db_path()}"
        )
        reporter.write_line("Run 'flakeradar report' to see flakiness trends across runs.")
