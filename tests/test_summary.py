import os
from pathlib import Path

from flakeradar.storage import Storage, TestResult
from flakeradar.summary import build_run_summary_markdown, write_github_step_summary


def _seeded_store(tmp_path: Path) -> Storage:
    store = Storage(tmp_path / "h.db")
    for i in range(6):
        store.start_run(f"run{i}", started_at=float(i))
        outcome = "passed" if i % 2 == 0 else "failed"
        store.record_results(f"run{i}", [TestResult(nodeid="t", outcome=outcome, longrepr="E boom")])
    return store


def test_empty_when_everything_passed(tmp_path: Path):
    store = _seeded_store(tmp_path)
    md = build_run_summary_markdown(store, [TestResult(nodeid="t", outcome="passed")], 5, 0.15)
    store.close()
    assert md == ""


def test_includes_failing_test_with_classification(tmp_path: Path):
    store = _seeded_store(tmp_path)
    md = build_run_summary_markdown(store, [TestResult(nodeid="t", outcome="failed")], 5, 0.15)
    store.close()
    assert "flakeradar summary" in md
    assert "`t`" in md
    assert "Known flaky" in md


def test_pipe_in_nodeid_is_escaped_for_markdown_table(tmp_path: Path):
    store = Storage(tmp_path / "h.db")
    store.start_run("run0")
    store.record_results("run0", [TestResult(nodeid="test[a|b]", outcome="failed")])
    md = build_run_summary_markdown(store, [TestResult(nodeid="test[a|b]", outcome="failed")], 1, 0.15)
    store.close()
    assert "test[a\\|b]" in md


def test_write_github_step_summary_appends_to_env_path(tmp_path: Path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    assert write_github_step_summary("hello") is True
    assert write_github_step_summary("world") is True
    content = summary_file.read_text(encoding="utf-8")
    assert "hello" in content and "world" in content


def test_write_github_step_summary_noop_without_env(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert write_github_step_summary("hello") is False


def test_write_github_step_summary_noop_for_empty_markdown(tmp_path: Path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    assert write_github_step_summary("") is False
