"""Configuration loading for flakeradar.

Resolution order (highest priority first):
    1. Explicit keyword arguments passed to `load_config`
    2. Environment variables (FLAKERADAR_*)
    3. `flakeradar.toml` in the project root
    4. `[tool.flakeradar]` table in `pyproject.toml`
    5. Built-in defaults
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

DEFAULT_DB_DIR = ".flakeradar"
DEFAULT_DB_NAME = "history.db"
DEFAULT_QUARANTINE_FILE = "quarantine.txt"

_ENV_PREFIX = "FLAKERADAR_"


@dataclass
class Config:
    """Resolved flakeradar configuration."""

    # Storage
    project_root: Path = field(default_factory=Path.cwd)
    db_path: Optional[Path] = None
    quarantine_path: Optional[Path] = None

    # Flakiness scoring
    min_runs: int = 5
    flakiness_threshold: float = 0.15
    quarantine_threshold: float = 0.30

    # LLM / AI analysis
    llm_provider: str = "none"  # none | groq | gemini | ollama | openai | anthropic
    llm_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_timeout: float = 30.0

    # Report
    report_out: str = "flakeradar-report.html"

    # Notifications
    webhook_url: Optional[str] = None

    # Tests to exclude entirely from tracking and reporting (glob patterns
    # matched against the full pytest nodeid, e.g. "tests/fuzz/*").
    ignore: List[str] = field(default_factory=list)

    def resolve_db_path(self) -> Path:
        if self.db_path:
            return Path(self.db_path)
        return self.project_root / DEFAULT_DB_DIR / DEFAULT_DB_NAME

    def resolve_quarantine_path(self) -> Path:
        if self.quarantine_path:
            return Path(self.quarantine_path)
        return self.project_root / DEFAULT_DB_DIR / DEFAULT_QUARANTINE_FILE

    def default_llm_model(self) -> str:
        """Return a sensible default model name for the configured provider.

        These defaults are intentionally overridable (via config/env) since
        provider model names change over time - check the provider's docs
        for the current recommended free-tier model.
        """
        if self.llm_model:
            return self.llm_model
        defaults = {
            "groq": "llama-3.1-8b-instant",
            "gemini": "gemini-2.0-flash",
            "ollama": "llama3.1",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-latest",
        }
        return defaults.get(self.llm_provider, "")

    def validate(self) -> List[str]:
        """Return a list of human-readable warnings about implausible values.

        Never raises - callers decide whether/how to surface these (e.g.
        `flakeradar doctor` prints them). Nothing here blocks normal use;
        it's meant to catch likely typos, not enforce hard constraints.
        """
        warnings: List[str] = []

        if not (0.0 <= self.flakiness_threshold <= 1.0):
            warnings.append(
                f"flakiness_threshold={self.flakiness_threshold} is outside the expected 0.0-1.0 range"
            )
        if not (0.0 <= self.quarantine_threshold <= 1.0):
            warnings.append(
                f"quarantine_threshold={self.quarantine_threshold} is outside the expected 0.0-1.0 range"
            )
        if self.quarantine_threshold < self.flakiness_threshold:
            warnings.append(
                f"quarantine_threshold ({self.quarantine_threshold}) is lower than flakiness_threshold "
                f"({self.flakiness_threshold}) - tests could be auto-quarantined before they're even "
                "classified as flaky"
            )
        if self.min_runs < 1:
            warnings.append(f"min_runs={self.min_runs} should be at least 1")

        valid_providers = {"none", "groq", "gemini", "ollama", "openai", "anthropic"}
        if self.llm_provider not in valid_providers:
            warnings.append(
                f"llm_provider='{self.llm_provider}' is not recognized "
                f"(expected one of {', '.join(sorted(valid_providers))})"
            )

        return warnings


def _read_toml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _find_project_root(start: Optional[Path] = None) -> Path:
    """Walk upward from `start` looking for pyproject.toml or .git."""
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").is_file() or (candidate / ".git").exists():
            return candidate
    return current


def _apply_env(data: Dict[str, Any]) -> Dict[str, Any]:
    mapping = {
        "FLAKERADAR_DB_PATH": "db_path",
        "FLAKERADAR_QUARANTINE_PATH": "quarantine_path",
        "FLAKERADAR_MIN_RUNS": "min_runs",
        "FLAKERADAR_FLAKINESS_THRESHOLD": "flakiness_threshold",
        "FLAKERADAR_QUARANTINE_THRESHOLD": "quarantine_threshold",
        "FLAKERADAR_LLM_PROVIDER": "llm_provider",
        "FLAKERADAR_LLM_API_KEY": "llm_api_key",
        "FLAKERADAR_LLM_MODEL": "llm_model",
        "FLAKERADAR_LLM_BASE_URL": "llm_base_url",
        "FLAKERADAR_LLM_TIMEOUT": "llm_timeout",
        "FLAKERADAR_REPORT_OUT": "report_out",
        "FLAKERADAR_WEBHOOK_URL": "webhook_url",
    }
    for env_key, field_name in mapping.items():
        if env_key in os.environ and os.environ[env_key] != "":
            data[field_name] = os.environ[env_key]

    # Common convenience aliases for API keys people are likely to already
    # have set for other tools.
    if not data.get("llm_api_key"):
        for alias in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            if os.environ.get(alias):
                data["llm_api_key"] = os.environ[alias]
                break

    # Comma-separated list, handled separately since it isn't a scalar 1:1
    # mapping like the fields above.
    if os.environ.get("FLAKERADAR_IGNORE"):
        data["ignore"] = [p.strip() for p in os.environ["FLAKERADAR_IGNORE"].split(",") if p.strip()]

    return data


def _coerce(data: Dict[str, Any]) -> Dict[str, Any]:
    int_fields = {"min_runs"}
    float_fields = {"flakiness_threshold", "quarantine_threshold", "llm_timeout"}
    for key in list(data.keys()):
        if key in int_fields and data[key] is not None:
            data[key] = int(data[key])
        elif key in float_fields and data[key] is not None:
            data[key] = float(data[key])
    for path_key in ("db_path", "quarantine_path", "project_root"):
        if data.get(path_key) is not None:
            data[path_key] = Path(data[path_key])
    return data


def load_config(project_root: Optional[Path] = None, **overrides: Any) -> Config:
    """Build a Config by merging defaults, config files, env vars, and overrides."""
    root = _find_project_root(project_root)
    data: Dict[str, Any] = {"project_root": root}

    pyproject = _read_toml(root / "pyproject.toml")
    tool_section = pyproject.get("tool", {}).get("flakeradar", {})
    data.update(tool_section)

    toml_file = _read_toml(root / "flakeradar.toml")
    data.update(toml_file)

    data = _apply_env(data)

    for key, value in overrides.items():
        if value is not None:
            data[key] = value

    valid_fields = {f.name for f in fields(Config)}
    data = {k: v for k, v in data.items() if k in valid_fields}
    data = _coerce(data)

    return Config(**data)
