import json
from pathlib import Path

from flakeradar.github_comment import (
    build_comment_markdown,
    detect_pr_context,
    post_or_update_comment,
)
from flakeradar.scoring import FlakinessResult


def _fr(nodeid, score, cls, fail_rate=0.5):
    return FlakinessResult(
        nodeid=nodeid, total_runs=10, pass_count=5, fail_count=5, other_count=0,
        fail_rate=fail_rate, transition_rate=0.5, score=score, classification=cls, last_outcome="passed",
    )


def test_detect_pr_context_reads_env_and_event_file(tmp_path: Path, monkeypatch):
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"pull_request": {"number": 42}}))
    monkeypatch.setenv("GITHUB_REPOSITORY", "Lethe044/flakeradar")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    assert detect_pr_context() == ("Lethe044", "flakeradar", 42)


def test_detect_pr_context_none_without_env(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    assert detect_pr_context() is None


def test_detect_pr_context_none_for_non_pr_event(tmp_path: Path, monkeypatch):
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"ref": "refs/heads/main"}))
    monkeypatch.setenv("GITHUB_REPOSITORY", "Lethe044/flakeradar")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    assert detect_pr_context() is None


def test_detect_pr_context_none_for_malformed_json(tmp_path: Path, monkeypatch):
    event_path = tmp_path / "event.json"
    event_path.write_text("not json")
    monkeypatch.setenv("GITHUB_REPOSITORY", "Lethe044/flakeradar")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    assert detect_pr_context() is None


def test_build_comment_markdown_no_issues():
    md = build_comment_markdown([], [])
    assert "No flaky" in md


def test_build_comment_markdown_lists_flaky_and_broken():
    flaky = [_fr("t1", 0.6, "flaky")]
    broken = [_fr("t2", 0.0, "broken", fail_rate=1.0)]
    md = build_comment_markdown(flaky, broken)
    assert "**1 flaky test(s):**" in md
    assert "`t1`" in md
    assert "**1 consistently failing test(s):**" in md
    assert "`t2`" in md


def test_build_comment_markdown_includes_report_url():
    md = build_comment_markdown([], [], report_url="https://example.com/r.html")
    assert "[Full report](https://example.com/r.html)" in md


def test_post_comment_creates_new_when_none_exists(monkeypatch):
    calls = []

    class FakeGetResp:
        status_code = 200

        def json(self):
            return []

    class FakePostResp:
        status_code = 201
        text = "ok"

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url))
        return FakeGetResp()

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(("POST", url, json))
        return FakePostResp()

    monkeypatch.setattr("flakeradar.github_comment.requests.get", fake_get)
    monkeypatch.setattr("flakeradar.github_comment.requests.post", fake_post)

    ok, error = post_or_update_comment("owner", "repo", 7, "tok", "hello")
    assert ok is True
    assert error is None
    assert calls[1][0] == "POST"
    assert "<!-- flakeradar-report -->" in calls[1][2]["body"]


def test_post_comment_updates_existing(monkeypatch):
    calls = []

    class FakeGetResp:
        status_code = 200

        def json(self):
            return [{"id": 999, "body": "<!-- flakeradar-report -->\nold content"}]

    class FakePatchResp:
        status_code = 200
        text = "ok"

    monkeypatch.setattr(
        "flakeradar.github_comment.requests.get",
        lambda url, headers=None, timeout=None: (calls.append(("GET", url)), FakeGetResp())[1],
    )

    def fake_patch(url, headers=None, json=None, timeout=None):
        calls.append(("PATCH", url, json))
        return FakePatchResp()

    monkeypatch.setattr("flakeradar.github_comment.requests.patch", fake_patch)

    ok, error = post_or_update_comment("owner", "repo", 7, "tok", "new content")
    assert ok is True
    assert calls[-1][0] == "PATCH"
    assert "999" in calls[-1][1]


def test_post_comment_handles_list_failure(monkeypatch):
    class FakeGetResp:
        status_code = 403
        text = "forbidden"

    monkeypatch.setattr("flakeradar.github_comment.requests.get", lambda *a, **k: FakeGetResp())
    ok, error = post_or_update_comment("owner", "repo", 7, "bad-token", "hello")
    assert ok is False
    assert "403" in error
