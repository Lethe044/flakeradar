"""Turn flakiness stats + clustered failures into an AI root cause report.

Works with any configured provider (or none, in which case
`analyze_test` returns None and callers should fall back to the plain
statistical output - flakeradar never requires an API key to be useful).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional

from ..clustering import FailureCluster
from ..scoring import FlakinessResult
from .base import LLMError, LLMProvider

_SYSTEM_PROMPT = (
    "You are a senior test engineer helping diagnose a flaky automated test. "
    "You will be given the test's pass/fail history statistics and one or more "
    "clustered failure tracebacks. Reply with a single JSON object only, no "
    "markdown fences, no prose outside the JSON, matching this shape:\n"
    '{"category": "<one of: race_condition, test_order_dependency, '
    'external_dependency, timing_or_sleep, shared_mutable_state, '
    'nondeterministic_data, resource_leak, environment_difference, unknown>", '
    '"confidence": "<low|medium|high>", '
    '"explanation": "<2-4 sentences on why you think this is the cause>", '
    '"suggested_fix": "<concrete, actionable suggestion>"}'
)

_CATEGORY_LABELS = {
    "race_condition": "Race condition",
    "test_order_dependency": "Test order dependency",
    "external_dependency": "External dependency (network/API/service)",
    "timing_or_sleep": "Timing-sensitive / sleep-based wait",
    "shared_mutable_state": "Shared mutable state between tests",
    "nondeterministic_data": "Non-deterministic test data (random/time/uuid)",
    "resource_leak": "Resource leak (file handle, connection, port)",
    "environment_difference": "Environment difference (CI vs local)",
    "unknown": "Unclear from available data",
}


@dataclass
class RootCauseAnalysis:
    category: str
    category_label: str
    confidence: str
    explanation: str
    suggested_fix: str
    raw_response: str


def _build_user_prompt(
    nodeid: str,
    stats: FlakinessResult,
    clusters: List[FailureCluster],
    source_snippet: Optional[str],
) -> str:
    lines = [
        f"Test: {nodeid}",
        f"Total runs observed: {stats.total_runs}",
        f"Pass: {stats.pass_count}  Fail: {stats.fail_count}  Other: {stats.other_count}",
        f"Fail rate: {stats.fail_rate:.2%}",
        f"Outcome transition rate (how often it flips between runs): {stats.transition_rate:.2%}",
        f"Flakiness score: {stats.score:.2f}",
        "",
        f"Distinct failure clusters: {len(clusters)}",
    ]
    for i, c in enumerate(clusters[:3], start=1):
        lines.append(f"\n--- Cluster {i} ({c.occurrences} occurrence(s)): {c.exception_type} ---")
        lines.append(c.example_longrepr or c.sample_message)

    if source_snippet:
        lines.append("\n--- Test source (for context) ---")
        lines.append(source_snippet[:3000])

    return "\n".join(lines)


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    # Strip markdown code fences if the model added them despite instructions.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: find the first {...} block.
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def analyze_test(
    provider: LLMProvider,
    nodeid: str,
    stats: FlakinessResult,
    clusters: List[FailureCluster],
    source_snippet: Optional[str] = None,
) -> RootCauseAnalysis:
    """Run AI root-cause analysis. Raises LLMError on failure - callers should catch it."""
    user_prompt = _build_user_prompt(nodeid, stats, clusters, source_snippet)
    raw = provider.generate(_SYSTEM_PROMPT, user_prompt)
    parsed = _extract_json(raw)

    if parsed is None:
        return RootCauseAnalysis(
            category="unknown",
            category_label=_CATEGORY_LABELS["unknown"],
            confidence="low",
            explanation="The model did not return structured output; showing raw response instead.",
            suggested_fix=raw.strip()[:1000],
            raw_response=raw,
        )

    category = str(parsed.get("category", "unknown")).strip()
    if category not in _CATEGORY_LABELS:
        category = "unknown"

    return RootCauseAnalysis(
        category=category,
        category_label=_CATEGORY_LABELS[category],
        confidence=str(parsed.get("confidence", "low")),
        explanation=str(parsed.get("explanation", "")).strip(),
        suggested_fix=str(parsed.get("suggested_fix", "")).strip(),
        raw_response=raw,
    )


def try_analyze_test(
    provider: Optional[LLMProvider],
    nodeid: str,
    stats: FlakinessResult,
    clusters: List[FailureCluster],
    source_snippet: Optional[str] = None,
) -> "tuple[Optional[RootCauseAnalysis], Optional[str]]":
    """Same as analyze_test but never raises. Returns (result, error_message)."""
    if provider is None:
        return None, "No LLM provider configured. Set --llm-provider or FLAKERADAR_LLM_PROVIDER."
    try:
        return analyze_test(provider, nodeid, stats, clusters, source_snippet), None
    except LLMError as exc:
        return None, str(exc)
