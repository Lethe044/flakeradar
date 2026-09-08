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


def test_slow_command_ranks_by_average_duration(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    for i in range(4):
        run_id = f"run{i}"
        store.start_run(run_id, started_at=float(i))
        store.record_results(
            run_id,
            [
                TestResult(nodeid="slow_test", outcome="passed", duration=2.0),
                TestResult(nodeid="fast_test", outcome="passed", duration=0.01),
            ],
        )
    store.close()

    rc = _run(["slow", "--top", "5"])
    assert rc == 0
    out = capsys.readouterr().out
    slow_idx = out.index("slow_test")
    fast_idx = out.index("fast_test")
    assert slow_idx < fast_idx  # slower test listed first


def test_slow_command_without_history_returns_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = _run(["slow"])
    assert rc == 1


def test_ignore_list_excludes_test_from_report(tmp_path, monkeypatch):
    from flakeradar.storage import Storage

    monkeypatch.chdir(tmp_path)
    (tmp_path / "flakeradar.toml").write_text('ignore = ["tests/fuzz/*"]\n')
    db_path = tmp_path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    for i in range(6):
        store.start_run(f"run{i}", started_at=float(i))
        store.record_results(
            f"run{i}",
            [
                TestResult(nodeid="tests/fuzz/test_c.py::test_fuzzy", outcome="passed" if i % 2 else "failed"),
                TestResult(nodeid="tests/test_b.py::test_stable", outcome="passed"),
            ],
        )
    store.close()

    rc = _run(["report"])
    assert rc == 0
    html = (tmp_path / "flakeradar-report.html").read_text()
    assert "test_fuzzy" not in html
    assert "test_stable" in html


def test_ignore_list_excludes_test_from_slow_command(tmp_path, monkeypatch, capsys):
    from flakeradar.storage import Storage

    monkeypatch.chdir(tmp_path)
    (tmp_path / "flakeradar.toml").write_text('ignore = ["tests/fuzz/*"]\n')
    db_path = tmp_path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    store.start_run("run0")
    store.record_results(
        "run0",
        [
            TestResult(nodeid="tests/fuzz/test_c.py::test_fuzzy", outcome="passed", duration=5.0),
            TestResult(nodeid="tests/test_b.py::test_stable", outcome="passed", duration=0.1),
        ],
    )
    store.close()

    rc = _run(["slow"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "test_fuzzy" not in out
    assert "test_stable" in out


def test_ignore_list_excludes_test_from_diff(tmp_path, monkeypatch, capsys):
    from flakeradar.storage import Storage

    monkeypatch.chdir(tmp_path)
    (tmp_path / "flakeradar.toml").write_text('ignore = ["tests/fuzz/*"]\n')
    db_path = tmp_path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    for i in range(6):
        store.start_run(f"m{i}", started_at=float(i), git_branch="main")
        store.record_results(f"m{i}", [TestResult(nodeid="tests/fuzz/test_c.py::test_fuzzy", outcome="passed")])
    for i in range(6):
        store.start_run(f"h{i}", started_at=100 + float(i), git_branch="head")
        outcome = "passed" if i % 2 == 0 else "failed"
        store.record_results(f"h{i}", [TestResult(nodeid="tests/fuzz/test_c.py::test_fuzzy", outcome=outcome)])
    store.close()

    rc = _run(["diff", "--baseline", "main", "--head", "head"])
    assert rc == 0
    out = capsys.readouterr().out
    # the only test that changed is ignored, so nothing should be reported as new
    assert "No new flakiness" in out


def test_init_with_ci_scaffolds_workflow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = _run(["init", "--with-ci"])
    assert rc == 0
    workflow_path = tmp_path / ".github" / "workflows" / "flakeradar.yml"
    assert workflow_path.exists()
    assert "flakeradar" in workflow_path.read_text()


def test_init_without_with_ci_does_not_create_workflow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = _run(["init"])
    assert rc == 0
    assert not (tmp_path / ".github" / "workflows" / "flakeradar.yml").exists()


def test_init_with_ci_skips_existing_workflow_without_force(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    workflow_path = tmp_path / ".github" / "workflows" / "flakeradar.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("# custom content, do not overwrite")
    rc = _run(["init", "--with-ci"])
    assert rc == 0
    assert workflow_path.read_text() == "# custom content, do not overwrite"
    out = capsys.readouterr().out
    assert "already exists" in out


def test_init_with_ci_overwrites_existing_workflow_with_force(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    workflow_path = tmp_path / ".github" / "workflows" / "flakeradar.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("# custom content, do not overwrite")
    rc = _run(["init", "--with-ci", "--force"])
    assert rc == 0
    assert "flakeradar" in workflow_path.read_text()
    assert "custom content" not in workflow_path.read_text()


def test_doctor_reports_config_warnings(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flakeradar.toml").write_text("flakiness_threshold = 5.0\n")
    rc = _run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "config warnings" in out
    assert "flakiness_threshold" in out


def test_doctor_reports_ok_for_default_config(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = _run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "config: OK" in out


def test_quarantine_list_flags_stale_entries(tmp_path, monkeypatch, capsys):
    from datetime import datetime, timedelta, timezone

    from flakeradar.quarantine import QuarantineEntry, write_quarantine

    monkeypatch.chdir(tmp_path)
    q_path = tmp_path / ".flakeradar" / "quarantine.txt"
    old_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    write_quarantine(q_path, [QuarantineEntry(nodeid="old_flaky", comment=f"score=0.5, auto-added {old_date}", auto=True)])

    rc = _run(["quarantine", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "stale" in out

    rc2 = _run(["quarantine", "list", "--stale-days", "120"])
    assert rc2 == 0
    out2 = capsys.readouterr().out
    assert "stale" not in out2


def test_completion_bash_command(capsys):
    rc = _run(["completion", "bash"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "_flakeradar_completion" in out


def test_completion_zsh_command(capsys):
    rc = _run(["completion", "zsh"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "#compdef flakeradar" in out


def test_doctor_shows_ignore_patterns(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "flakeradar.toml").write_text('ignore = ["tests/fuzz/*"]\n')
    rc = _run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ignore patterns: 1 configured" in out
    assert "tests/fuzz/*" in out


def test_doctor_shows_no_ignore_patterns_by_default(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc = _run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ignore patterns: none configured" in out


def test_stress_parallel_runs_all_iterations(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    call_log = []

    def fake_run_once(pytest_args):
        call_log.append(pytest_args)
        # alternate pass/fail deterministically by call count
        outcome = "passed" if len(call_log) % 2 == 0 else "failed"
        return outcome, "output"

    monkeypatch.setattr("flakeradar.cli._run_pytest_once", fake_run_once)

    rc = _run(["stress", "some_test.py", "-k", "test_x", "-n", "6", "--parallel", "3"])
    assert rc in (0, 1)  # depends on classification, both are valid exit paths
    assert len(call_log) == 6

    from flakeradar.storage import Storage

    store = Storage(tmp_path / ".flakeradar" / "history.db")
    history = store.history_for("test_x")
    store.close()
    assert len(history) == 6


def test_stress_sequential_matches_parallel_count(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fake_run_once(pytest_args):
        return "passed", ""

    monkeypatch.setattr("flakeradar.cli._run_pytest_once", fake_run_once)
    rc = _run(["stress", "some_test.py", "-k", "test_y", "-n", "5"])
    assert rc == 0  # all passed -> stable classification -> exit 0

    from flakeradar.storage import Storage

    store = Storage(tmp_path / ".flakeradar" / "history.db")
    history = store.history_for("test_y")
    store.close()
    assert len(history) == 5
