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
