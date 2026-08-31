"""Flakiness scoring.

A test that fails every time is not flaky - it is broken. A flaky test is
one whose outcome *changes* across runs without a corresponding code
change. We measure that directly with a "transition rate": how often the
outcome flips from one run to the next, relative to the number of
opportunities to flip. A test that alternates pass/fail/pass/fail has a
transition rate of 1.0. A test that is always green, or always red, has a
transition rate of 0.0.

Transition rate alone is not quite enough: a test that failed once in 200
runs also has a very low transition rate but is worth flagging early. So
the final score blends transition rate with a "balance" term that rewards
outcomes closer to 50/50 (the failure mode most associated with true
non-determinism), while still giving partial credit to rare, isolated
failures.

score = 0.6 * transition_rate + 0.4 * balance

balance = 2 * min(fail_rate, pass_rate)   -> 0 when always-pass/always-fail,
                                              1.0 when exactly 50/50

Both components are in [0, 1], so the final score is in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Sequence

Classification = Literal["stable", "flaky", "broken", "insufficient_data"]

# Outcomes counted as a "pass" for scoring purposes.
_PASS_OUTCOMES = {"passed"}
# Outcomes counted as a "fail" for scoring purposes. Errors during setup /
# teardown are treated the same as a failed call, since from the caller's
# perspective the test did not reliably succeed.
_FAIL_OUTCOMES = {"failed", "error"}


@dataclass
class FlakinessResult:
    nodeid: str
    total_runs: int
    pass_count: int
    fail_count: int
    other_count: int
    fail_rate: float
    transition_rate: float
    score: float
    classification: Classification
    last_outcome: str


def _binary_outcomes(outcomes: Sequence[str]) -> List[int]:
    """Map outcomes to 1 (pass) / 0 (fail), dropping anything else (e.g. skipped)."""
    result = []
    for o in outcomes:
        if o in _PASS_OUTCOMES:
            result.append(1)
        elif o in _FAIL_OUTCOMES:
            result.append(0)
        # skipped / xfail / other: excluded from the binary sequence entirely,
        # since they carry no pass/fail signal.
    return result


def score_test(
    nodeid: str,
    outcomes: Sequence[str],
    min_runs: int = 5,
    flakiness_threshold: float = 0.15,
) -> FlakinessResult:
    """Compute a FlakinessResult from an ordered sequence of raw outcomes.

    `outcomes` must be in chronological order (oldest first).
    """
    binary = _binary_outcomes(outcomes)
    total_considered = len(binary)
    other_count = len(outcomes) - total_considered
    last_outcome = outcomes[-1] if outcomes else "unknown"

    if total_considered == 0:
        return FlakinessResult(
            nodeid=nodeid,
            total_runs=len(outcomes),
            pass_count=0,
            fail_count=0,
            other_count=other_count,
            fail_rate=0.0,
            transition_rate=0.0,
            score=0.0,
            classification="insufficient_data",
            last_outcome=last_outcome,
        )

    pass_count = sum(binary)
    fail_count = total_considered - pass_count
    fail_rate = fail_count / total_considered
    pass_rate = pass_count / total_considered

    if total_considered < 2:
        transition_rate = 0.0
    else:
        transitions = sum(
            1 for a, b in zip(binary, binary[1:]) if a != b
        )
        transition_rate = transitions / (total_considered - 1)

    balance = 2 * min(fail_rate, pass_rate)
    score = round(0.6 * transition_rate + 0.4 * balance, 4)

    if total_considered < min_runs:
        classification: Classification = "insufficient_data"
    elif fail_rate >= 0.95 and transition_rate <= 0.05:
        classification = "broken"
    elif score >= flakiness_threshold:
        classification = "flaky"
    else:
        classification = "stable"

    return FlakinessResult(
        nodeid=nodeid,
        total_runs=len(outcomes),
        pass_count=pass_count,
        fail_count=fail_count,
        other_count=other_count,
        fail_rate=round(fail_rate, 4),
        transition_rate=round(transition_rate, 4),
        score=score,
        classification=classification,
        last_outcome=last_outcome,
    )
