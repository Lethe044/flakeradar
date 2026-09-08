"""Glob-based ignore list for excluding specific tests from flakeradar
tracking and reporting entirely.

Useful for tests that are intentionally non-deterministic by design -
property-based/fuzz tests, load tests with randomized timing, and the
like - which shouldn't ever count as "flaky" since their pass/fail
alternation is expected, not a bug to chase.
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Iterable, List


def matches_ignore(nodeid: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch(nodeid, pattern) for pattern in patterns)


def filter_ignored(nodeids: List[str], patterns: Iterable[str]) -> List[str]:
    patterns = list(patterns)
    if not patterns:
        return nodeids
    return [n for n in nodeids if not matches_ignore(n, patterns)]
