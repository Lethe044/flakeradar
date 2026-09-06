"""Optional webhook notifications summarizing a flakeradar report.

Uses the Slack incoming-webhook JSON shape (`{"text": "..."}`), which is
also accepted as-is by Discord, Mattermost, and most other chat tools that
support incoming webhooks - no per-service formatting needed.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import requests

from .scoring import FlakinessResult


def build_notification_text(
    flaky: List[FlakinessResult],
    broken: List[FlakinessResult],
    report_url: Optional[str] = None,
    max_listed: int = 5,
) -> str:
    lines = ["flakeradar report"]

    if not flaky and not broken:
        lines.append("No flaky or consistently failing tests detected.")
    else:
        if flaky:
            lines.append(f"\n{len(flaky)} flaky test(s):")
            for r in sorted(flaky, key=lambda r: -r.score)[:max_listed]:
                lines.append(f"  - {r.nodeid} (score {r.score:.2f})")
            if len(flaky) > max_listed:
                lines.append(f"  ...and {len(flaky) - max_listed} more")
        if broken:
            lines.append(f"\n{len(broken)} consistently failing test(s):")
            for r in sorted(broken, key=lambda r: -r.fail_rate)[:max_listed]:
                lines.append(f"  - {r.nodeid} (fail rate {r.fail_rate:.0%})")
            if len(broken) > max_listed:
                lines.append(f"  ...and {len(broken) - max_listed} more")

    if report_url:
        lines.append(f"\nReport: {report_url}")

    return "\n".join(lines)


def send_webhook(url: str, text: str, timeout: float = 10.0) -> Tuple[bool, Optional[str]]:
    """POST a Slack-style payload to `url`. Returns (success, error_message)."""
    try:
        resp = requests.post(url, json={"text": text}, timeout=timeout)
    except requests.RequestException as exc:
        return False, str(exc)
    if resp.status_code >= 300:
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
    return True, None
