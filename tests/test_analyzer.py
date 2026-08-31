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
