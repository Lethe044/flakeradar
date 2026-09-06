import requests

from flakeradar.notify import build_notification_text, send_webhook
from flakeradar.scoring import FlakinessResult


def _fr(nodeid, score, cls, fail_rate=0.5):
    return FlakinessResult(
        nodeid=nodeid, total_runs=10, pass_count=5, fail_count=5, other_count=0,
        fail_rate=fail_rate, transition_rate=0.5, score=score, classification=cls, last_outcome="passed",
    )


def test_empty_when_nothing_flaky_or_broken():
    text = build_notification_text([], [])
    assert "No flaky" in text


def test_includes_flaky_and_broken_sections():
    flaky = [_fr("t1", 0.6, "flaky")]
    broken = [_fr("t2", 0.0, "broken", fail_rate=1.0)]
    text = build_notification_text(flaky, broken)
    assert "1 flaky test(s)" in text
    assert "t1" in text
    assert "1 consistently failing test(s)" in text
    assert "t2" in text


def test_truncates_long_lists_with_more_indicator():
    flaky = [_fr(f"t{i}", 0.9 - i * 0.01, "flaky") for i in range(8)]
    text = build_notification_text(flaky, [], max_listed=5)
    assert "...and 3 more" in text
    assert text.count("score") == 5


def test_report_url_included_when_given():
    text = build_notification_text([], [], report_url="https://example.com/report.html")
    assert "https://example.com/report.html" in text


def test_send_webhook_success(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = "ok"

    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("flakeradar.notify.requests.post", fake_post)
    ok, error = send_webhook("https://hooks.example.com/x", "hello")
    assert ok is True
    assert error is None
    assert captured["json"] == {"text": "hello"}


def test_send_webhook_http_error(monkeypatch):
    class FakeResponse:
        status_code = 500
        text = "server error"

    monkeypatch.setattr("flakeradar.notify.requests.post", lambda *a, **k: FakeResponse())
    ok, error = send_webhook("https://hooks.example.com/x", "hello")
    assert ok is False
    assert "500" in error


def test_send_webhook_network_error(monkeypatch):
    def raise_error(*args, **kwargs):
        raise requests.RequestException("connection refused")

    monkeypatch.setattr("flakeradar.notify.requests.post", raise_error)
    ok, error = send_webhook("https://hooks.example.com/x", "hello")
    assert ok is False
    assert "connection refused" in error
