"""Quarantine list management.

The quarantine file is a plain text file, one nodeid per line, with
optional trailing comments. It is deliberately human-editable and meant to
be committed to version control so the whole team sees (and can review)
which tests are currently excused from blocking CI.

Format:
    tests/test_payments.py::test_webhook_retry  # score=0.42, auto-added 2026-08-01
    tests/test_upload.py::test_large_file       # manually pinned, see #482
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Set

from .scoring import FlakinessResult


@dataclass
class QuarantineEntry:
    nodeid: str
    comment: str = ""
    auto: bool = False


def read_quarantine(path: Path) -> Dict[str, QuarantineEntry]:
    entries: Dict[str, QuarantineEntry] = {}
    if not path.is_file():
        return entries
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            nodeid, comment = line.split("#", 1)
            nodeid = nodeid.strip()
            comment = comment.strip()
        else:
            nodeid, comment = line, ""
        if nodeid:
            entries[nodeid] = QuarantineEntry(
                nodeid=nodeid, comment=comment, auto="auto-added" in comment
            )
    return entries


def write_quarantine(path: Path, entries: Iterable[QuarantineEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# flakeradar quarantine list - one test nodeid per line.",
        "# Entries marked 'auto-added' are managed by `flakeradar quarantine sync`",
        "# and may be removed automatically once a test stabilizes.",
        "# Manually pinned entries (no 'auto-added' comment) are left alone.",
        "",
    ]
    for entry in sorted(entries, key=lambda e: e.nodeid):
        if entry.comment:
            lines.append(f"{entry.nodeid}  # {entry.comment}")
        else:
            lines.append(entry.nodeid)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sync_quarantine(
    path: Path,
    results: List[FlakinessResult],
    quarantine_threshold: float,
) -> Dict[str, List[str]]:
    """Recompute the quarantine list.

    - Tests scoring at/above `quarantine_threshold` are added (if not
      already manually pinned).
    - Auto-added tests that have since dropped below the threshold are
      removed.
    - Manually pinned entries (no 'auto-added' marker) are never touched.

    Returns a dict with "added" and "removed" nodeid lists for reporting.
    """
    existing = read_quarantine(path)
    manual: Set[str] = {nid for nid, e in existing.items() if not e.auto}

    today = time.strftime("%Y-%m-%d")
    new_entries: Dict[str, QuarantineEntry] = {
        nid: e for nid, e in existing.items() if nid in manual
    }

    added: List[str] = []
    for r in results:
        if r.classification != "flaky" or r.score < quarantine_threshold:
            continue
        if r.nodeid in manual:
            continue
        if r.nodeid not in existing:
            added.append(r.nodeid)
        new_entries[r.nodeid] = QuarantineEntry(
            nodeid=r.nodeid,
            comment=f"score={r.score:.2f}, auto-added {today}",
            auto=True,
        )

    still_flaky = {r.nodeid for r in results if r.classification == "flaky" and r.score >= quarantine_threshold}
    removed: List[str] = []
    for nid, entry in list(new_entries.items()):
        if entry.auto and nid not in still_flaky:
            removed.append(nid)
            del new_entries[nid]

    write_quarantine(path, new_entries.values())
    return {"added": added, "removed": removed}


def is_quarantined(path: Path, nodeid: str) -> bool:
    return nodeid in read_quarantine(path)
