import json
from pathlib import Path

from flakeradar.cli import build_parser
from flakeradar.storage import Storage, TestResult


def _seed(tmp_path: Path) -> None:
    db_path = tmp_path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    for i in range(10):
        store.start_run(f"run{i}", started_at=float(i))
        outcome = "passed" if i % 3 != 0 else "failed"
        store.record_results(
            f"run{i}",
            [TestResult(nodeid="tests/test_x.py::test_flip", outcome=outcome, longrepr="E boom")],
        )
    store.close()


def _run(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def test_report_html_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["report"])
    assert rc == 0
    assert (tmp_path / "flakeradar-report.html").exists()


def test_report_json_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["report", "--format", "json"])
    assert rc == 0
    out = tmp_path / "flakeradar-report.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["tests"][0]["nodeid"] == "tests/test_x.py::test_flip"


def test_report_max_flaky_gating_fails_build(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["report", "--max-flaky", "0"])
    assert rc == 1


def test_report_max_flaky_gating_passes_when_under_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["report", "--max-flaky", "99"])
    assert rc == 0


def test_report_without_history_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = _run(["report"])
    assert rc == 1


def test_badge_command_writes_svg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["badge"])
    assert rc == 0
    svg_path = tmp_path / "flakeradar-badge.svg"
    assert svg_path.exists()
    assert svg_path.read_text().startswith("<svg")


def test_badge_custom_output_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["badge", "--out", "assets/badge.svg", "--label", "flake count"])
    assert rc == 0
    svg_path = tmp_path / "assets" / "badge.svg"
    assert svg_path.exists()
    assert "flake count" in svg_path.read_text()


def test_quarantine_sync_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["quarantine", "sync", "--dry-run"])
    assert rc == 0
    assert not (tmp_path / ".flakeradar" / "quarantine.txt").exists()


def test_quarantine_sync_without_dry_run_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["quarantine", "sync"])
    assert rc == 0
    assert (tmp_path / ".flakeradar" / "quarantine.txt").exists()


def test_prune_keeps_requested_number_of_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["prune", "--keep", "3"])
    assert rc == 0
    from flakeradar.storage import Storage

    store = Storage(tmp_path / ".flakeradar" / "history.db")
    assert store.run_count() == 3
    store.close()


def test_prune_without_history_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = _run(["prune", "--keep", "5"])
    assert rc == 1


def test_import_junit_records_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    xml_path = tmp_path / "results.xml"
    xml_path.write_text(
        '<testsuite name="s">'
        '<testcase classname="a.b" name="test_ok" time="0.1"/>'
        '<testcase classname="a.b" name="test_bad" time="0.2">'
        '<failure message="boom">trace</failure></testcase>'
        "</testsuite>"
    )
    rc = _run(["import-junit", str(xml_path)])
    assert rc == 0

    from flakeradar.storage import Storage

    store = Storage(tmp_path / ".flakeradar" / "history.db")
    nodeids = store.all_nodeids()
    store.close()
    assert "a.b::test_ok" in nodeids
    assert "a.b::test_bad" in nodeids


def test_import_junit_missing_file_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = _run(["import-junit", str(tmp_path / "nope.xml")])
    assert rc == 1


def test_import_junit_invalid_xml_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad_path = tmp_path / "bad.xml"
    bad_path.write_text("not valid xml <<<")
    rc = _run(["import-junit", str(bad_path)])
    assert rc == 1


def test_report_webhook_flag_sends_notification(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)

    captured = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("flakeradar.notify.requests.post", fake_post)
    rc = _run(["report", "--webhook", "https://hooks.example.com/x"])
    assert rc == 0
    assert captured["url"] == "https://hooks.example.com/x"
    out = capsys.readouterr().out
    assert "Webhook notification sent" in out


def test_report_html_includes_trend_section(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    _run(["report"])
    html = (tmp_path / "flakeradar-report.html").read_text()
    assert "Failing tests per run" in html


def test_diff_detects_new_flakiness(tmp_path, monkeypatch):
    from flakeradar.storage import Storage

    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    for i in range(10):
        store.start_run(f"main{i}", started_at=float(i), git_branch="main")
        store.record_results(f"main{i}", [TestResult(nodeid="t", outcome="passed")])
    for i in range(10):
        store.start_run(f"head{i}", started_at=100 + float(i), git_branch="pr-branch")
        outcome = "passed" if i % 2 == 0 else "failed"
        store.record_results(f"head{i}", [TestResult(nodeid="t", outcome=outcome)])
    store.close()

    rc = _run(["diff", "--baseline", "main", "--head", "pr-branch"])
    assert rc == 0  # informational by default, no --fail-on-new

    rc_fail = _run(["diff", "--baseline", "main", "--head", "pr-branch", "--fail-on-new"])
    assert rc_fail == 1


def test_diff_without_history_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = _run(["diff", "--baseline", "main", "--head", "other"])
    assert rc == 1


def test_doctor_runs_without_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = _run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "flakeradar" in out
    assert "history db: not found" in out


def test_doctor_reports_existing_history(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "journal_mode=wal" in out


def test_analyze_all_with_no_flaky_tests(tmp_path, monkeypatch, capsys):
    from flakeradar.storage import Storage

    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    for i in range(6):
        store.start_run(f"run{i}", started_at=float(i))
        store.record_results(f"run{i}", [TestResult(nodeid="t", outcome="passed")])
    store.close()

    rc = _run(["analyze", "--all"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "No flaky or consistently failing tests" in out


def test_analyze_requires_nodeid_or_all(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    rc = _run(["analyze"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "--all" in out


def test_analyze_all_writes_consolidated_markdown(tmp_path, monkeypatch):
    import json as _json

    from flakeradar.llm.base import LLMProvider

    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)

    class FakeProvider(LLMProvider):
        name = "fake"

        def generate(self, system_prompt, user_prompt):
            return _json.dumps(
                {
                    "category": "timing_or_sleep",
                    "confidence": "medium",
                    "explanation": "looks timing related",
                    "suggested_fix": "add a wait condition",
                }
            )

    monkeypatch.setattr("flakeradar.cli.build_provider", lambda config: FakeProvider())

    out_path = tmp_path / "analysis.md"
    rc = _run(["analyze", "--all", "--out", str(out_path)])
    assert rc == 0
    assert out_path.exists()
    content = out_path.read_text()
    assert "flakeradar AI analysis" in content
    assert "tests/test_x.py::test_flip" in content
    assert "timing related" in content
