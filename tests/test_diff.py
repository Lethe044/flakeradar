from pathlib import Path

from flakeradar.config import load_config
from flakeradar.diff import diff_branches
from flakeradar.storage import Storage, TestResult


def _seed_two_branches(store: Storage) -> None:
    # main: t1 stable, t2 flaky (pre-existing), t3 broken
    for i in range(10):
        store.start_run(f"main-run{i}", started_at=float(i), git_branch="main")
        store.record_results(
            f"main-run{i}",
            [
                TestResult(nodeid="t1", outcome="passed"),
                TestResult(nodeid="t2", outcome="passed" if i % 2 == 0 else "failed"),
                TestResult(nodeid="t3", outcome="failed"),
            ],
        )
    # feature-x: t1 now flaky (new), t2 still flaky, t3 fixed (now passing)
    for i in range(10):
        store.start_run(f"feat-run{i}", started_at=100 + float(i), git_branch="feature-x")
        store.record_results(
            f"feat-run{i}",
            [
                TestResult(nodeid="t1", outcome="passed" if i % 2 == 0 else "failed"),
                TestResult(nodeid="t2", outcome="passed" if i % 2 == 0 else "failed"),
                TestResult(nodeid="t3", outcome="passed"),
            ],
        )


def test_detects_newly_flaky_test(tmp_path: Path):
    store = Storage(tmp_path / "h.db")
    _seed_two_branches(store)
    config = load_config(project_root=tmp_path)
    result = diff_branches(store, "main", "feature-x", config)
    store.close()
    assert "t1" in [r.nodeid for r in result.newly_flaky]


def test_detects_fixed_test(tmp_path: Path):
    store = Storage(tmp_path / "h.db")
    _seed_two_branches(store)
    config = load_config(project_root=tmp_path)
    result = diff_branches(store, "main", "feature-x", config)
    store.close()
    assert "t3" in result.fixed


def test_pre_existing_flakiness_is_unchanged_not_new(tmp_path: Path):
    store = Storage(tmp_path / "h.db")
    _seed_two_branches(store)
    config = load_config(project_root=tmp_path)
    result = diff_branches(store, "main", "feature-x", config)
    store.close()
    assert "t2" in [r.nodeid for r in result.unchanged]
    assert "t2" not in [r.nodeid for r in result.newly_flaky]


def test_has_new_issues_property(tmp_path: Path):
    store = Storage(tmp_path / "h.db")
    _seed_two_branches(store)
    config = load_config(project_root=tmp_path)
    result = diff_branches(store, "main", "feature-x", config)
    store.close()
    assert result.has_new_issues is True


def test_no_new_issues_when_branches_identical(tmp_path: Path):
    store = Storage(tmp_path / "h.db")
    for i in range(10):
        for branch in ("main", "other"):
            run_id = f"{branch}-run{i}"
            store.start_run(run_id, started_at=float(i), git_branch=branch)
            store.record_results(run_id, [TestResult(nodeid="t1", outcome="passed")])
    config = load_config(project_root=tmp_path)
    result = diff_branches(store, "main", "other", config)
    store.close()
    assert result.has_new_issues is False
    assert result.fixed == []


def test_unknown_branch_yields_empty_classification(tmp_path: Path):
    store = Storage(tmp_path / "h.db")
    _seed_two_branches(store)
    config = load_config(project_root=tmp_path)
    result = diff_branches(store, "main", "does-not-exist", config)
    store.close()
    assert result.newly_flaky == []
    assert result.newly_broken == []
