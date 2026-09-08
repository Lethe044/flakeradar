from flakeradar.ignore import filter_ignored, matches_ignore


def test_matches_simple_glob():
    assert matches_ignore("tests/fuzz/test_x.py::test_a", ["tests/fuzz/*"])


def test_does_not_match_unrelated_path():
    assert not matches_ignore("tests/unit/test_x.py::test_a", ["tests/fuzz/*"])


def test_matches_any_of_multiple_patterns():
    patterns = ["tests/fuzz/*", "tests/load/*"]
    assert matches_ignore("tests/load/test_spike.py::test_a", patterns)
    assert matches_ignore("tests/fuzz/test_random.py::test_b", patterns)
    assert not matches_ignore("tests/unit/test_c.py::test_c", patterns)


def test_matches_exact_nodeid():
    assert matches_ignore("tests/test_x.py::test_flaky_by_design", ["tests/test_x.py::test_flaky_by_design"])


def test_no_patterns_matches_nothing():
    assert not matches_ignore("anything", [])


def test_filter_ignored_removes_matching_entries():
    nodeids = ["a", "b", "tests/fuzz/x", "tests/fuzz/y"]
    result = filter_ignored(nodeids, ["tests/fuzz/*"])
    assert result == ["a", "b"]


def test_filter_ignored_no_patterns_returns_same_list():
    nodeids = ["a", "b"]
    assert filter_ignored(nodeids, []) == nodeids


def test_filter_ignored_empty_input():
    assert filter_ignored([], ["tests/fuzz/*"]) == []
