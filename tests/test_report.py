from flakeradar.report import generate_html_report
from flakeradar.scoring import score_test
from flakeradar.storage import HistoryEntry


def _history(outcomes):
    return [
        HistoryEntry(run_id=f"r{i}", started_at=float(i), git_sha="abc", outcome=o, duration=0.1, longrepr=None)
        for i, o in enumerate(outcomes)
    ]


def test_report_contains_test_names():
    outcomes = ["passed", "failed"] * 5
    result = score_test("tests/test_x.py::test_flip", outcomes, min_runs=5)
    html = generate_html_report(
        [result],
        {"tests/test_x.py::test_flip": _history(outcomes)},
        run_count=10,
        threshold=0.15,
    )
    assert "test_flip" in html
    assert "FLAKY" in html


def test_report_handles_empty_results():
    html = generate_html_report([], {}, run_count=0, threshold=0.15)
    assert "No data yet" in html


def test_report_shows_stable_badge_for_all_passing():
    outcomes = ["passed"] * 8
    result = score_test("tests/test_x.py::test_ok", outcomes, min_runs=5)
    html = generate_html_report(
        [result],
        {"tests/test_x.py::test_ok": _history(outcomes)},
        run_count=8,
        threshold=0.15,
    )
    assert "STABLE" in html


def test_report_escapes_html_in_nodeid():
    outcomes = ["passed"] * 5
    nodeid = "tests/test_x.py::test[<script>]"
    result = score_test(nodeid, outcomes, min_runs=5)
    html = generate_html_report([result], {nodeid: _history(outcomes)}, run_count=5, threshold=0.15)
    assert "<script>]" not in html
    assert "&lt;script&gt;" in html


def test_report_includes_trend_section_when_run_summaries_given():
    from flakeradar.storage import RunSummary

    outcomes = ["passed"] * 5
    result = score_test("t1", outcomes, min_runs=5)
    summaries = [RunSummary(run_id=f"r{i}", started_at=float(i), git_sha=None, total=3, passed=3, failed=0) for i in range(4)]
    html = generate_html_report(
        [result], {"t1": _history(outcomes)}, run_count=4, threshold=0.15, run_summaries=summaries
    )
    assert "Failing tests per run" in html


def test_report_omits_trend_section_without_run_summaries():
    outcomes = ["passed"] * 5
    result = score_test("t1", outcomes, min_runs=5)
    html = generate_html_report([result], {"t1": _history(outcomes)}, run_count=5, threshold=0.15)
    assert "Failing tests per run" not in html


def test_json_report_contains_expected_fields():
    from flakeradar.report import generate_json_report
    import json as _json

    outcomes = ["passed", "failed"] * 5
    result = score_test("t1", outcomes, min_runs=5)
    payload = _json.loads(generate_json_report([result], run_count=10, threshold=0.15))
    assert payload["run_count"] == 10
    assert payload["tests"][0]["nodeid"] == "t1"
    assert payload["tests"][0]["classification"] == "flaky"


def test_html_report_includes_slow_section_when_durations_given():
    from flakeradar.storage import DurationSummary

    outcomes = ["passed"] * 5
    result = score_test("t1", outcomes, min_runs=5)
    durations = [DurationSummary(nodeid="t1", run_count=5, avg_duration=3.25, max_duration=4.0, total_duration=16.25)]
    html = generate_html_report(
        [result], {"t1": _history(outcomes)}, run_count=5, threshold=0.15, duration_summaries=durations
    )
    assert "Slowest tests" in html
    assert "3.25s" in html


def test_html_report_omits_slow_section_without_durations():
    outcomes = ["passed"] * 5
    result = score_test("t1", outcomes, min_runs=5)
    html = generate_html_report([result], {"t1": _history(outcomes)}, run_count=5, threshold=0.15)
    assert "Slowest tests" not in html


def test_json_report_includes_duration_fields_when_given():
    from flakeradar.storage import DurationSummary
    from flakeradar.report import generate_json_report
    import json as _json

    result = score_test("t1", ["passed"] * 5, min_runs=5)
    durations = [DurationSummary(nodeid="t1", run_count=5, avg_duration=1.23456, max_duration=2.0, total_duration=6.1728)]
    payload = _json.loads(generate_json_report([result], run_count=5, threshold=0.15, duration_summaries=durations))
    assert payload["tests"][0]["avg_duration_seconds"] == 1.2346


def test_json_report_omits_duration_fields_without_durations():
    from flakeradar.report import generate_json_report
    import json as _json

    result = score_test("t1", ["passed"] * 5, min_runs=5)
    payload = _json.loads(generate_json_report([result], run_count=5, threshold=0.15))
    assert "avg_duration_seconds" not in payload["tests"][0]
