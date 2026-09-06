"""Post or update a summary comment on a GitHub pull request.

Designed to run inside a GitHub Actions job triggered by a `pull_request`
event, where a `GITHUB_TOKEN` is already available as a job permission
(not a secret you have to create yourself) - see
https://docs.github.com/en/actions/security-guides/automatic-token-authentication

Only the REST API and `requests` (an existing dependency) are used, so no
extra dependency is needed just for this feature.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional, Tuple

import requests

from .scoring import FlakinessResult

_MARKER = "<!-- flakeradar-report -->"
_API_BASE = "https://api.github.com"


def detect_pr_context() -> Optional[Tuple[str, str, int]]:
    """Return (owner, repo, pr_number) when running in a GitHub Actions
    pull_request (or pull_request_target) event context, else None.
    """
    repo_full = os.environ.get("GITHUB_REPOSITORY")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not repo_full or not event_path or not os.path.isfile(event_path):
        return None

    try:
        with open(event_path, "r", encoding="utf-8") as fh:
            event = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None

    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return None
    pr_number = pull_request.get("number")
    if pr_number is None:
        return None

    owner, sep, repo = repo_full.partition("/")
    if not sep:
        return None
    return owner, repo, int(pr_number)


def build_comment_markdown(
    flaky: List[FlakinessResult],
    broken: List[FlakinessResult],
    report_url: Optional[str] = None,
    max_listed: int = 10,
) -> str:
    lines = ["### flakeradar report", ""]

    if not flaky and not broken:
        lines.append("No flaky or consistently failing tests detected.")
    else:
        if flaky:
            lines.append(f"**{len(flaky)} flaky test(s):**")
            lines.append("")
            for r in sorted(flaky, key=lambda r: -r.score)[:max_listed]:
                lines.append(f"- `{r.nodeid}` (score {r.score:.2f})")
            if len(flaky) > max_listed:
                lines.append(f"- ...and {len(flaky) - max_listed} more")
            lines.append("")
        if broken:
            lines.append(f"**{len(broken)} consistently failing test(s):**")
            lines.append("")
            for r in sorted(broken, key=lambda r: -r.fail_rate)[:max_listed]:
                lines.append(f"- `{r.nodeid}` (fail rate {r.fail_rate:.0%})")
            if len(broken) > max_listed:
                lines.append(f"- ...and {len(broken) - max_listed} more")

    if report_url:
        lines.append("")
        lines.append(f"[Full report]({report_url})")

    return "\n".join(lines)


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def post_or_update_comment(
    owner: str, repo: str, pr_number: int, token: str, body: str, timeout: float = 15.0
) -> Tuple[bool, Optional[str]]:
    """Create a new PR comment, or update flakeradar's previous one if found.

    Looks for an existing comment containing flakeradar's hidden marker so
    repeated runs update one comment instead of piling up new ones.
    """
    body_with_marker = f"{_MARKER}\n{body}"
    comments_url = f"{_API_BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"

    try:
        resp = requests.get(comments_url, headers=_headers(token), timeout=timeout)
    except requests.RequestException as exc:
        return False, f"Could not list existing comments: {exc}"
    if resp.status_code != 200:
        return False, f"Could not list existing comments: HTTP {resp.status_code}: {resp.text[:300]}"

    existing_id = None
    for comment in resp.json():
        if _MARKER in (comment.get("body") or ""):
            existing_id = comment.get("id")
            break

    try:
        if existing_id is not None:
            resp = requests.patch(
                f"{_API_BASE}/repos/{owner}/{repo}/issues/comments/{existing_id}",
                headers=_headers(token),
                json={"body": body_with_marker},
                timeout=timeout,
            )
        else:
            resp = requests.post(
                comments_url, headers=_headers(token), json={"body": body_with_marker}, timeout=timeout
            )
    except requests.RequestException as exc:
        return False, f"Could not post comment: {exc}"

    if resp.status_code not in (200, 201):
        return False, f"Could not post comment: HTTP {resp.status_code}: {resp.text[:300]}"
    return True, None
