import json

from flakeradar.clustering import cluster_failures
from flakeradar.llm.analyzer import analyze_test, try_analyze_test
from flakeradar.llm.base import LLMError, LLMProvider
from flakeradar.scoring import score_test


class _FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, response: str = "", raise_error: bool = False):
        super().__init__(api_key="fake", model="fake-model")
        self._response = response
        self._raise_error = raise_error

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        if self._raise_error:
            raise LLMError("simulated failure")
        return self._response


def _sample_stats_and_clusters():
    outcomes = ["passed", "failed"] * 5
    stats = score_test("tests/test_x.py::test_flip", outcomes, min_runs=5)
    clusters = cluster_failures(["E   TimeoutError: connection timed out after 30s"] * 5)
    return stats, clusters


def test_analyze_test_parses_clean_json():
    stats, clusters = _sample_stats_and_clusters()
    response = json.dumps(
        {
            "category": "external_dependency",
            "confidence": "high",
            "explanation": "The failures all involve a network timeout.",
            "suggested_fix": "Mock the external service in tests.",
        }
    )
    provider = _FakeProvider(response=response)
    result = analyze_test(provider, "tests/test_x.py::test_flip", stats, clusters)
    assert result.category == "external_dependency"
    assert result.confidence == "high"
    assert "network timeout" in result.explanation


def test_analyze_test_parses_json_wrapped_in_markdown_fences():
    stats, clusters = _sample_stats_and_clusters()
    response = "```json\n" + json.dumps({"category": "timing_or_sleep", "confidence": "medium"}) + "\n```"
    provider = _FakeProvider(response=response)
    result = analyze_test(provider, "t", stats, clusters)
    assert result.category == "timing_or_sleep"


def test_analyze_test_falls_back_gracefully_on_unparseable_response():
    stats, clusters = _sample_stats_and_clusters()
    provider = _FakeProvider(response="I think this is a race condition, sorry no JSON.")
    result = analyze_test(provider, "t", stats, clusters)
    assert result.category == "unknown"
    assert "race condition" in result.suggested_fix


def test_analyze_test_rejects_unknown_category_gracefully():
    stats, clusters = _sample_stats_and_clusters()
    response = json.dumps({"category": "totally_made_up", "confidence": "low"})
    provider = _FakeProvider(response=response)
    result = analyze_test(provider, "t", stats, clusters)
    assert result.category == "unknown"


def test_try_analyze_test_returns_none_provider_message_when_no_provider():
    stats, clusters = _sample_stats_and_clusters()
    result, error = try_analyze_test(None, "t", stats, clusters)
    assert result is None
    assert "No LLM provider" in error


def test_try_analyze_test_catches_llm_error():
    stats, clusters = _sample_stats_and_clusters()
    provider = _FakeProvider(raise_error=True)
    result, error = try_analyze_test(provider, "t", stats, clusters)
    assert result is None
    assert "simulated failure" in error


def test_build_cache_key_stable_for_same_clusters():
    from flakeradar.llm.analyzer import build_cache_key

    clusters_a = cluster_failures(["E TimeoutError: connection timed out"] * 3)
    clusters_b = cluster_failures(["E TimeoutError: connection timed out"] * 3)
    assert build_cache_key("t1", clusters_a) == build_cache_key("t1", clusters_b)


def test_build_cache_key_changes_with_different_failure_pattern():
    from flakeradar.llm.analyzer import build_cache_key

    clusters_a = cluster_failures(["E TimeoutError: x"] * 3)
    clusters_b = cluster_failures(["E ValueError: y"] * 3)
    assert build_cache_key("t1", clusters_a) != build_cache_key("t1", clusters_b)


def test_build_cache_key_changes_with_different_nodeid():
    from flakeradar.llm.analyzer import build_cache_key

    clusters = cluster_failures(["E TimeoutError: x"] * 3)
    assert build_cache_key("t1", clusters) != build_cache_key("t2", clusters)


def test_analysis_from_cache_row_reconstructs_analysis():
    from flakeradar.llm.analyzer import analysis_from_cache_row

    row = {
        "category": "race_condition",
        "confidence": "high",
        "explanation": "shared state",
        "suggested_fix": "use a lock",
        "raw_response": "raw text",
    }
    analysis = analysis_from_cache_row(row)
    assert analysis.category == "race_condition"
    assert analysis.category_label == "Race condition"
    assert analysis.confidence == "high"
    assert analysis.explanation == "shared state"


def test_analysis_from_cache_row_handles_unknown_category():
    from flakeradar.llm.analyzer import analysis_from_cache_row

    row = {"category": "not_a_real_category", "confidence": "low", "explanation": "", "suggested_fix": "", "raw_response": ""}
    analysis = analysis_from_cache_row(row)
    assert analysis.category == "unknown"
