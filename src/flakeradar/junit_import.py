"""Import JUnit XML test results into flakeradar's history database.

Two use cases this unlocks:

1. Backfilling history from CI logs that predate adopting the pytest
   plugin - most CI systems keep old JUnit XML artifacts around.
2. Tracking flakiness for test suites that don't use pytest at all
   (Jest, Go test, JUnit/Java, RSpec, etc.), since virtually every test
   runner can emit JUnit-style XML even if flakeradar's own hooks only
   understand pytest directly.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from .storage import TestResult


def _iter_testcases(root: ET.Element) -> Iterator[Tuple[str, ET.Element]]:
    """Yield (suite_name, testcase_element) for every <testcase> found.

    Handles both common JUnit XML shapes: a single <testsuite> root, or a
    <testsuites> wrapper containing one or more <testsuite> children.
    """
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    elif root.tag == "testsuite":
        suites = [root]
    else:
        suites = root.findall(".//testsuite")
    for suite in suites:
        suite_name = suite.get("name", "")
        for case in suite.findall("testcase"):
            yield suite_name, case


def _outcome_for_testcase(case: ET.Element) -> str:
    if case.find("failure") is not None:
        return "failed"
    if case.find("error") is not None:
        return "error"
    if case.find("skipped") is not None:
        return "skipped"
    return "passed"


def _longrepr_for_testcase(case: ET.Element) -> Optional[str]:
    for tag in ("failure", "error"):
        el = case.find(tag)
        if el is None:
            continue
        message = (el.get("message") or "").strip()
        text = (el.text or "").strip()
        combined = "\n".join(part for part in (message, text) if part)
        return combined or None
    return None


def parse_junit_xml(path: Path) -> List[TestResult]:
    """Parse a JUnit XML file into a list of TestResult objects.

    Raises xml.etree.ElementTree.ParseError if the file isn't valid XML.
    """
    tree = ET.parse(str(path))
    root = tree.getroot()

    results: List[TestResult] = []
    for suite_name, case in _iter_testcases(root):
        classname = case.get("classname") or suite_name
        name = case.get("name", "unknown")
        nodeid = f"{classname}::{name}" if classname else name

        try:
            duration = float(case.get("time", 0.0) or 0.0)
        except ValueError:
            duration = 0.0

        results.append(
            TestResult(
                nodeid=nodeid,
                outcome=_outcome_for_testcase(case),
                duration=duration,
                longrepr=_longrepr_for_testcase(case),
            )
        )
    return results


def run_id_for_import(path: Path) -> str:
    """A stable-ish run id derived from the imported file's mtime and name."""
    mtime = path.stat().st_mtime
    return f"junit-{int(mtime)}-{path.stem}"
