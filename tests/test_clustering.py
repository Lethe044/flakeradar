from flakeradar.clustering import cluster_failures, fingerprint_failure


def test_identical_errors_cluster_together():
    tb1 = "E   AssertionError: expected 200 got 500"
    tb2 = "E   AssertionError: expected 200 got 500"
    clusters = cluster_failures([tb1, tb2])
    assert len(clusters) == 1
    assert clusters[0].occurrences == 2


def test_numbers_are_normalized_so_similar_errors_cluster():
    tb1 = "E   AssertionError: expected 200 got 500"
    tb2 = "E   AssertionError: expected 200 got 503"
    clusters = cluster_failures([tb1, tb2])
    assert len(clusters) == 1
    assert clusters[0].occurrences == 2


def test_different_exception_types_do_not_cluster():
    tb1 = "E   AssertionError: boom"
    tb2 = "E   TimeoutError: boom"
    clusters = cluster_failures([tb1, tb2])
    assert len(clusters) == 2


def test_empty_and_none_are_ignored():
    clusters = cluster_failures(["", None, "E   ValueError: x"])  # type: ignore[list-item]
    assert len(clusters) == 1


def test_clusters_sorted_by_occurrence_descending():
    failures = (
        ["E   AssertionError: a"] * 5
        + ["E   TimeoutError: b"] * 1
        + ["E   ValueError: c"] * 3
    )
    clusters = cluster_failures(failures)
    occurrences = [c.occurrences for c in clusters]
    assert occurrences == sorted(occurrences, reverse=True)


def test_fingerprint_is_deterministic():
    tb = "E   ConnectionError: timed out after 30s to 10.0.0.5:8080"
    fp1 = fingerprint_failure(tb)
    fp2 = fingerprint_failure(tb)
    assert fp1 == fp2
