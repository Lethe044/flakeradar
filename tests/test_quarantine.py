from pathlib import Path

from flakeradar.quarantine import (
    QuarantineEntry,
    read_quarantine,
    sync_quarantine,
    write_quarantine,
)
from flakeradar.scoring import FlakinessResult


def _fake_result(nodeid: str, score: float, classification: str = "flaky") -> FlakinessResult:
    return FlakinessResult(
        nodeid=nodeid,
        total_runs=10,
        pass_count=5,
        fail_count=5,
        other_count=0,
        fail_rate=0.5,
        transition_rate=0.5,
        score=score,
        classification=classification,
        last_outcome="passed",
    )


def test_write_and_read_roundtrip(tmp_path: Path):
    path = tmp_path / "quarantine.txt"
    write_quarantine(path, [QuarantineEntry(nodeid="t1", comment="manual"), QuarantineEntry(nodeid="t2")])
    entries = read_quarantine(path)
    assert set(entries.keys()) == {"t1", "t2"}
    assert entries["t1"].comment == "manual"


def test_read_missing_file_returns_empty(tmp_path: Path):
    assert read_quarantine(tmp_path / "nope.txt") == {}


def test_sync_adds_high_scoring_tests(tmp_path: Path):
    path = tmp_path / "quarantine.txt"
    results = [_fake_result("t1", 0.5), _fake_result("t2", 0.05, classification="stable")]
    diff = sync_quarantine(path, results, quarantine_threshold=0.3)
    assert diff["added"] == ["t1"]
    entries = read_quarantine(path)
    assert "t1" in entries
    assert "t2" not in entries


def test_sync_removes_stabilized_auto_entries(tmp_path: Path):
    path = tmp_path / "quarantine.txt"
    write_quarantine(path, [QuarantineEntry(nodeid="t1", comment="score=0.50, auto-added 2026-01-01", auto=True)])
    results = [_fake_result("t1", 0.02, classification="stable")]
    diff = sync_quarantine(path, results, quarantine_threshold=0.3)
    assert diff["removed"] == ["t1"]
    assert "t1" not in read_quarantine(path)


def test_sync_never_touches_manual_entries(tmp_path: Path):
    path = tmp_path / "quarantine.txt"
    write_quarantine(path, [QuarantineEntry(nodeid="t1", comment="manually pinned, see #42", auto=False)])
    results = [_fake_result("t1", 0.01, classification="stable")]
    diff = sync_quarantine(path, results, quarantine_threshold=0.3)
    assert diff["removed"] == []
    assert "t1" in read_quarantine(path)


def test_comment_lines_and_blank_lines_ignored(tmp_path: Path):
    path = tmp_path / "quarantine.txt"
    path.write_text("# a comment\n\nt1\nt2  # with a note\n")
    entries = read_quarantine(path)
    assert set(entries.keys()) == {"t1", "t2"}


def test_days_since_auto_added_parses_date(tmp_path: Path):
    from datetime import datetime, timedelta, timezone

    from flakeradar.quarantine import days_since_auto_added

    old_date = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d")
    entry = QuarantineEntry(nodeid="t1", comment=f"score=0.50, auto-added {old_date}", auto=True)
    days = days_since_auto_added(entry)
    assert days is not None
    assert 44 <= days <= 46


def test_days_since_auto_added_none_for_manual_entry():
    from flakeradar.quarantine import days_since_auto_added

    entry = QuarantineEntry(nodeid="t1", comment="manually pinned, see #42", auto=False)
    assert days_since_auto_added(entry) is None


def test_days_since_auto_added_none_when_unparseable():
    from flakeradar.quarantine import days_since_auto_added

    entry = QuarantineEntry(nodeid="t1", comment="auto-added at some point", auto=True)
    assert days_since_auto_added(entry) is None
