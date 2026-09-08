"""Compare flakiness classification between two branches.

Built for a specific CI question: "did this PR introduce new flakiness
compared to the base branch?" Every recorded run already carries a git
branch (captured automatically by the pytest plugin and by
`flakeradar stress`), so this reuses that data rather than needing any
new tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .config import Config
from .ignore import filter_ignored
from .scoring import FlakinessResult, score_test
from .storage import Storage

_BAD_CLASSIFICATIONS = ("flaky", "broken")


@dataclass
class DiffResult:
    baseline_branch: str
    head_branch: str
    newly_flaky: List[FlakinessResult] = field(default_factory=list)
    newly_broken: List[FlakinessResult] = field(default_factory=list)
    fixed: List[str] = field(default_factory=list)
    unchanged: List[FlakinessResult] = field(default_factory=list)

    @property
    def has_new_issues(self) -> bool:
        return bool(self.newly_flaky or self.newly_broken)


def _classify_branch(store: Storage, branch: str, config: Config) -> Dict[str, FlakinessResult]:
    out: Dict[str, FlakinessResult] = {}
    for nodeid in filter_ignored(store.all_nodeids(branch=branch), config.ignore):
        history = store.history_for(nodeid, branch=branch)
        outcomes = [h.outcome for h in history]
        out[nodeid] = score_test(nodeid, outcomes, config.min_runs, config.flakiness_threshold)
    return out


def diff_branches(store: Storage, baseline: str, head: str, config: Config) -> DiffResult:
    baseline_results = _classify_branch(store, baseline, config)
    head_results = _classify_branch(store, head, config)

    result = DiffResult(baseline_branch=baseline, head_branch=head)

    for nodeid, head_r in head_results.items():
        baseline_r = baseline_results.get(nodeid)
        baseline_bad = baseline_r is not None and baseline_r.classification in _BAD_CLASSIFICATIONS
        head_bad = head_r.classification in _BAD_CLASSIFICATIONS

        if head_bad and not baseline_bad:
            (result.newly_flaky if head_r.classification == "flaky" else result.newly_broken).append(head_r)
        elif head_bad and baseline_bad:
            result.unchanged.append(head_r)

    for nodeid, baseline_r in baseline_results.items():
        if baseline_r.classification not in _BAD_CLASSIFICATIONS:
            continue
        head_r = head_results.get(nodeid)
        if head_r is None or head_r.classification not in _BAD_CLASSIFICATIONS:
            result.fixed.append(nodeid)

    result.fixed.sort()
    return result
