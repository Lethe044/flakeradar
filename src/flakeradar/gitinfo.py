"""Best-effort git metadata lookup. Never raises - flakeradar must work fine
in a plain (non-git) directory too."""

from __future__ import annotations

import subprocess
from typing import Optional


def _run(args: list, cwd: Optional[str] = None) -> Optional[str]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    output = result.stdout.strip()
    return output or None


def current_sha(cwd: Optional[str] = None, short: bool = True) -> Optional[str]:
    args = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
    return _run(args, cwd)


def current_branch(cwd: Optional[str] = None) -> Optional[str]:
    return _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
