"""Group failures of the same test by a normalized fingerprint.

A flaky test can fail for more than one reason across its history. Before
handing a batch of failures to an LLM (or a human), it helps to know
whether they are "one bug, N occurrences" or "three different bugs". We
fingerprint each failure by its exception type plus a normalized version
of the message (numbers, hex addresses, UUIDs, and file paths stripped
out), so that superficially different but structurally identical failures
collapse into the same cluster.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

_HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
_UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_NUMBER_RE = re.compile(r"\b\d+\b")
_PATH_RE = re.compile(r"(/[\w\-.]+)+\.py")
_EXC_LINE_RE = re.compile(r"^E\s+([\w.]+(?:Error|Exception|Warning|Failure|Timeout)\b)")
_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")


@dataclass
class FailureCluster:
    fingerprint: str
    exception_type: str
    sample_message: str
    occurrences: int
    example_longrepr: Optional[str]


def _normalize_message(longrepr: str) -> str:
    text = _PATH_RE.sub("<path>", longrepr)
    text = _HEX_RE.sub("<hex>", text)
    text = _UUID_RE.sub("<uuid>", text)
    text = _QUOTED_RE.sub("<str>", text)
    text = _NUMBER_RE.sub("<n>", text)
    return text.strip()


def _extract_exception_type(longrepr: str) -> str:
    for line in longrepr.splitlines():
        m = _EXC_LINE_RE.match(line.strip())
        if m:
            return m.group(1)
    # Fallback: last non-empty line often reads "ExceptionType: message"
    for line in reversed(longrepr.strip().splitlines()):
        line = line.strip()
        if ":" in line and not line.startswith(("File ", "E ")):
            candidate = line.split(":", 1)[0].strip()
            if candidate and " " not in candidate:
                return candidate
    return "UnknownError"


def fingerprint_failure(longrepr: str) -> str:
    """Return a stable short fingerprint id for a traceback/message string."""
    exc_type = _extract_exception_type(longrepr)
    normalized = _normalize_message(longrepr)
    # Keep the fingerprint stable and short; only use the first ~300 chars of
    # the normalized text so unrelated trailing frames don't split clusters
    # that are really the same root cause.
    digest_input = f"{exc_type}:{normalized[:300]}"
    digest = hashlib.sha1(digest_input.encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"{exc_type}-{digest}"


def cluster_failures(longreprs: List[str]) -> List[FailureCluster]:
    """Cluster a list of failure longrepr strings into groups by fingerprint."""
    groups: Dict[str, List[str]] = defaultdict(list)
    for lr in longreprs:
        if not lr:
            continue
        fp = fingerprint_failure(lr)
        groups[fp].append(lr)

    clusters = []
    for fp, samples in groups.items():
        exc_type = fp.rsplit("-", 1)[0]
        sample = samples[0]
        first_line = next((ln for ln in sample.splitlines() if ln.strip()), sample[:200])
        clusters.append(
            FailureCluster(
                fingerprint=fp,
                exception_type=exc_type,
                sample_message=first_line.strip()[:300],
                occurrences=len(samples),
                example_longrepr=sample[:2000],
            )
        )
    clusters.sort(key=lambda c: c.occurrences, reverse=True)
    return clusters
