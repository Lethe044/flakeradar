from pathlib import Path

import pytest

from flakeradar.storage import Storage, TestResult


@pytest.fixture()
def store(tmp_path: Path):
    s = Storage(tmp_path / "history.db")
    yield s
    s.close()


def test_record_and_read_back(store: Storage):
    store.start_run("run1", git_sha="abc123", git_branch="main")
    store.record_results(
        "run1",
        [
            TestResult(nodeid="tests/test_x.py::test_a", outcome="passed", duration=0.1),
            TestResult(nodeid="tests/test_x.py::test_b", outcome="failed", duration=0.2, longrepr="boom"),
        ],
    )
    history_a = store.history_for("tests/test_x.py::test_a")
    history_b = store.history_for("tests/test_x.py::test_b")
    assert len(history_a) == 1
    assert history_a[0].outcome == "passed"
    assert history_a[0].git_sha == "abc123"
    assert len(history_b) == 1
    assert history_b[0].longrepr == "boom"


def test_history_ordered_chronologically(store: Storage):
    for i in range(3):
        run_id = f"run{i}"
        store.start_run(run_id, started_at=float(i))
        store.record_results(run_id, [TestResult(nodeid="t", outcome="passed" if i % 2 == 0 else "failed")])
    history = store.history_for("t")
    assert [h.outcome for h in history] == ["passed", "failed", "passed"]


def test_all_nodeids(store: Storage):
    store.start_run("run1")
    store.record_results(
        "run1",
        [
            TestResult(nodeid="t1", outcome="passed"),
            TestResult(nodeid="t2", outcome="failed"),
        ],
    )
    assert set(store.all_nodeids()) == {"t1", "t2"}


def test_prune_runs_keeps_most_recent(store: Storage):
    for i in range(5):
        run_id = f"run{i}"
        store.start_run(run_id, started_at=float(i))
        store.record_results(run_id, [TestResult(nodeid="t", outcome="passed")])
    removed = store.prune_runs(keep_last_n=2)
    assert removed == 3
    assert store.run_count() == 2
    assert len(store.history_for("t")) == 2


def test_history_limit(store: Storage):
    for i in range(10):
        run_id = f"run{i}"
        store.start_run(run_id, started_at=float(i))
        store.record_results(run_id, [TestResult(nodeid="t", outcome="passed")])
    assert len(store.history_for("t", limit=3)) == 3


def test_empty_results_is_noop(store: Storage):
    store.start_run("run1")
    store.record_results("run1", [])
    assert store.all_nodeids() == []
