from flakeradar.scoring import score_test


def test_all_passing_is_stable():
    outcomes = ["passed"] * 10
    result = score_test("t1", outcomes, min_runs=5)
    assert result.classification == "stable"
    assert result.score == 0.0
    assert result.fail_rate == 0.0


def test_all_failing_is_broken_not_flaky():
    outcomes = ["failed"] * 10
    result = score_test("t1", outcomes, min_runs=5)
    assert result.classification == "broken"
    assert result.transition_rate == 0.0


def test_alternating_outcomes_is_flaky():
    outcomes = ["passed", "failed"] * 6
    result = score_test("t1", outcomes, min_runs=5)
    assert result.classification == "flaky"
    assert result.transition_rate == 1.0
    assert result.score > 0.9


def test_one_failure_in_many_is_still_flagged_with_low_score():
    outcomes = ["passed"] * 19 + ["failed"]
    result = score_test("t1", outcomes, min_runs=5, flakiness_threshold=0.05)
    assert result.fail_count == 1
    assert result.score > 0.0
    assert result.classification == "flaky"


def test_insufficient_data_below_min_runs():
    outcomes = ["passed", "failed"]
    result = score_test("t1", outcomes, min_runs=5)
    assert result.classification == "insufficient_data"


def test_skipped_outcomes_are_excluded_from_binary_but_counted():
    outcomes = ["passed", "skipped", "passed", "skipped", "passed", "failed", "passed"]
    result = score_test("t1", outcomes, min_runs=3)
    assert result.other_count == 2
    assert result.pass_count == 4
    assert result.fail_count == 1


def test_error_outcome_counts_as_failure():
    outcomes = ["passed", "error", "passed", "error", "passed", "error"]
    result = score_test("t1", outcomes, min_runs=3)
    assert result.fail_count == 3
    assert result.classification == "flaky"


def test_empty_outcomes():
    result = score_test("t1", [], min_runs=5)
    assert result.classification == "insufficient_data"
    assert result.total_runs == 0


def test_score_is_bounded_between_zero_and_one():
    import random

    random.seed(42)
    for _ in range(20):
        outcomes = [random.choice(["passed", "failed"]) for _ in range(30)]
        result = score_test("t1", outcomes, min_runs=5)
        assert 0.0 <= result.score <= 1.0
