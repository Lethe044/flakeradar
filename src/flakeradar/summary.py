"""Build a concise per-run Markdown summary and, when running inside GitHub
Actions, publish it to the job summary tab automatically.

This is deliberately separate from the full HTML report: it only covers
*this run's* non-passing tests, cross-referenced against historical
classification, so a reviewer can tell at a glance whether a red test in
CI is a known flaky test or something new without leaving the Actions UI.
"""

from __future__ import annotations

import os
from typing import List

from .scoring import score_test
from .storage import Storage, TestResult

_CLASSIFICATION_LABELS = {
    "flaky": "Known flaky",
    "broken": "Consistently failing",
    "stable": "Unexpected (was stable)",
    "insufficient_data": "Not enough history yet",
}


def build_run_summary_markdown(
    store: Storage,
    run_results: List[TestResult],
    min_runs: int,
    flakiness_threshold: float,
) -> str:
    """Markdown summary of the non-passing tests from a single run.

    Returns an empty string if everything passed (nothing worth summarizing).
    """
    non_passing = [r for r in run_results if r.outcome != "passed"]
    if not non_passing:
        return ""

    lines = [
        "### flakeradar summary",
        "",
        f"{len(non_passing)} test(s) did not pass this run:",
        "",
        "| Test | Outcome | Classification | Score | Runs seen |",
        "|---|---|---|---|---|",
    ]
    for r in non_passing:
        history = store.history_for(r.nodeid)
        outcomes = [h.outcome for h in history]
        stats = score_test(r.nodeid, outcomes, min_runs=min_runs, flakiness_threshold=flakiness_threshold)
        label = _CLASSIFICATION_LABELS.get(stats.classification, stats.classification)
        nodeid_display = r.nodeid.replace("|", "\\|")
        lines.append(f"| `{nodeid_display}` | {r.outcome} | {label} | {stats.score:.2f} | {stats.total_runs} |")

    lines.append("")
    lines.append("Run `flakeradar report` for full historical trends.")
    return "\n".join(lines)


def write_github_step_summary(markdown: str) -> bool:
    """Append markdown to $GITHUB_STEP_SUMMARY if that env var is set.

    Returns True if something was written, False otherwise (not running in
    GitHub Actions, or nothing to report). Never raises - this is a
    best-effort visibility feature, not something that should break a
    test run if the file can't be written.
    """
    if not markdown:
        return False
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return False
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")
        return True
    except OSError:
        return False
