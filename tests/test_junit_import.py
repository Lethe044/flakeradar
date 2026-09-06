import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from flakeradar.junit_import import parse_junit_xml, run_id_for_import

_SUITES_XML = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="suite1">
    <testcase classname="pkg.mod" name="test_ok" time="0.01"/>
    <testcase classname="pkg.mod" name="test_fail" time="0.02">
      <failure message="AssertionError: boom">Traceback (most recent call last):\nboom</failure>
    </testcase>
    <testcase classname="pkg.mod" name="test_error" time="0.0">
      <error message="ConnectionError">could not connect</error>
    </testcase>
    <testcase classname="pkg.mod" name="test_skip" time="0.0">
      <skipped/>
    </testcase>
  </testsuite>
</testsuites>"""

_SINGLE_SUITE_XML = """<testsuite name="only">
  <testcase classname="a.b" name="test_one" time="0.5"/>
</testsuite>"""


def test_parses_testsuites_wrapper(tmp_path: Path):
    path = tmp_path / "results.xml"
    path.write_text(_SUITES_XML)
    results = parse_junit_xml(path)
    assert len(results) == 4
    assert [r.nodeid for r in results] == [
        "pkg.mod::test_ok",
        "pkg.mod::test_fail",
        "pkg.mod::test_error",
        "pkg.mod::test_skip",
    ]


def test_outcomes_mapped_correctly(tmp_path: Path):
    path = tmp_path / "results.xml"
    path.write_text(_SUITES_XML)
    results = {r.nodeid.split("::")[-1]: r for r in parse_junit_xml(path)}
    assert results["test_ok"].outcome == "passed"
    assert results["test_fail"].outcome == "failed"
    assert results["test_error"].outcome == "error"
    assert results["test_skip"].outcome == "skipped"


def test_failure_message_and_text_captured(tmp_path: Path):
    path = tmp_path / "results.xml"
    path.write_text(_SUITES_XML)
    results = {r.nodeid.split("::")[-1]: r for r in parse_junit_xml(path)}
    assert "AssertionError: boom" in results["test_fail"].longrepr
    assert "boom" in results["test_fail"].longrepr


def test_duration_parsed_as_float(tmp_path: Path):
    path = tmp_path / "results.xml"
    path.write_text(_SUITES_XML)
    results = {r.nodeid.split("::")[-1]: r for r in parse_junit_xml(path)}
    assert results["test_ok"].duration == 0.01


def test_single_testsuite_root_without_wrapper(tmp_path: Path):
    path = tmp_path / "results.xml"
    path.write_text(_SINGLE_SUITE_XML)
    results = parse_junit_xml(path)
    assert len(results) == 1
    assert results[0].nodeid == "a.b::test_one"


def test_invalid_xml_raises_parse_error(tmp_path: Path):
    path = tmp_path / "bad.xml"
    path.write_text("not xml at all <<<")
    with pytest.raises(ET.ParseError):
        parse_junit_xml(path)


def test_missing_classname_falls_back_to_suite_name(tmp_path: Path):
    path = tmp_path / "results.xml"
    path.write_text('<testsuite name="mysuite"><testcase name="test_bare"/></testsuite>')
    results = parse_junit_xml(path)
    assert results[0].nodeid == "mysuite::test_bare"


def test_run_id_for_import_is_stable_and_prefixed(tmp_path: Path):
    path = tmp_path / "results.xml"
    path.write_text(_SINGLE_SUITE_XML)
    rid1 = run_id_for_import(path)
    rid2 = run_id_for_import(path)
    assert rid1 == rid2
    assert rid1.startswith("junit-")
    assert "results" in rid1
