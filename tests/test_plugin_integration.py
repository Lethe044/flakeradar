"""End-to-end tests that run the flakeradar pytest plugin inside a nested
pytest process (via the `pytester` fixture) and inspect the resulting
history database.
"""

from flakeradar.storage import Storage


def test_flakeradar_flag_records_results(pytester):
    pytester.makepyfile(
        """
        def test_ok():
            assert True

        def test_fail():
            assert False
        """
    )
    result = pytester.runpytest("--flakeradar")
    result.assert_outcomes(passed=1, failed=1)

    db_path = pytester.path / ".flakeradar" / "history.db"
    assert db_path.exists()

    store = Storage(db_path)
    nodeids = store.all_nodeids()
    store.close()
    assert any("test_ok" in n for n in nodeids)
    assert any("test_fail" in n for n in nodeids)


def test_without_flag_nothing_is_recorded(pytester):
    pytester.makepyfile(
        """
        def test_ok():
            assert True
        """
    )
    pytester.runpytest()
    db_path = pytester.path / ".flakeradar" / "history.db"
    assert not db_path.exists()


def test_quarantine_skips_listed_tests(pytester):
    pytester.makepyfile(
        """
        def test_a():
            assert True

        def test_b():
            assert False
        """
    )
    q_dir = pytester.path / ".flakeradar"
    q_dir.mkdir()
    (q_dir / "quarantine.txt").write_text("test_quarantine_skips_listed_tests.py::test_b\n")

    result = pytester.runpytest("--flakeradar-quarantine")
    result.assert_outcomes(passed=1, skipped=1)


def test_multiple_runs_accumulate_history(pytester):
    pytester.makepyfile(
        """
        def test_stable():
            assert True
        """
    )
    pytester.runpytest("--flakeradar")
    pytester.runpytest("--flakeradar")
    pytester.runpytest("--flakeradar")

    db_path = pytester.path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    nodeids = store.all_nodeids()
    history = store.history_for(nodeids[0])
    store.close()
    assert len(history) == 3


def test_marker_skipped_test_is_recorded_as_skipped(pytester):
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.skip(reason="not ready yet")
        def test_skipped_by_marker():
            assert False
        """
    )
    result = pytester.runpytest("--flakeradar")
    result.assert_outcomes(skipped=1)

    db_path = pytester.path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    nodeids = store.all_nodeids()
    history = store.history_for(nodeids[0]) if nodeids else []
    store.close()
    assert len(nodeids) == 1
    assert history[0].outcome == "skipped"


def test_ignored_test_is_never_recorded(pytester):
    pytester.makepyfile(
        """
        def test_fuzzy_by_design():
            assert True

        def test_tracked_normally():
            assert True
        """
    )
    q_dir = pytester.path / ".flakeradar"
    q_dir.mkdir()
    (pytester.path / "flakeradar.toml").write_text('ignore = ["*test_fuzzy_by_design*"]\n')

    pytester.runpytest("--flakeradar")

    db_path = pytester.path / ".flakeradar" / "history.db"
    store = Storage(db_path)
    nodeids = store.all_nodeids()
    store.close()
    assert any("test_tracked_normally" in n for n in nodeids)
    assert not any("test_fuzzy_by_design" in n for n in nodeids)
