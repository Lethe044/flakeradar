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
