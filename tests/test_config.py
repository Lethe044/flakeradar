import os
from pathlib import Path

from flakeradar.config import load_config


def test_defaults(tmp_path: Path):
    config = load_config(project_root=tmp_path)
    assert config.min_runs == 5
    assert config.flakiness_threshold == 0.15
    assert config.llm_provider == "none"


def test_toml_file_overrides_defaults(tmp_path: Path):
    (tmp_path / "flakeradar.toml").write_text(
        'min_runs = 10\nflakiness_threshold = 0.5\nllm_provider = "groq"\n'
    )
    config = load_config(project_root=tmp_path)
    assert config.min_runs == 10
    assert config.flakiness_threshold == 0.5
    assert config.llm_provider == "groq"


def test_env_var_overrides_toml(tmp_path: Path, monkeypatch):
    (tmp_path / "flakeradar.toml").write_text("min_runs = 10\n")
    monkeypatch.setenv("FLAKERADAR_MIN_RUNS", "3")
    config = load_config(project_root=tmp_path)
    assert config.min_runs == 3


def test_explicit_kwarg_overrides_everything(tmp_path: Path, monkeypatch):
    (tmp_path / "flakeradar.toml").write_text("min_runs = 10\n")
    monkeypatch.setenv("FLAKERADAR_MIN_RUNS", "3")
    config = load_config(project_root=tmp_path, min_runs=99)
    assert config.min_runs == 99


def test_pyproject_tool_section(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.flakeradar]\nmin_runs = 7\n"
    )
    config = load_config(project_root=tmp_path)
    assert config.min_runs == 7


def test_resolve_db_path_default(tmp_path: Path):
    config = load_config(project_root=tmp_path)
    assert config.resolve_db_path() == tmp_path / ".flakeradar" / "history.db"


def test_llm_api_key_falls_back_to_provider_alias(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FLAKERADAR_LLM_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "secret123")
    config = load_config(project_root=tmp_path)
    assert config.llm_api_key == "secret123"


def test_default_llm_model_for_known_provider(tmp_path: Path):
    config = load_config(project_root=tmp_path, llm_provider="groq")
    assert config.default_llm_model() == "llama-3.1-8b-instant"


def test_explicit_llm_model_overrides_default(tmp_path: Path):
    config = load_config(project_root=tmp_path, llm_provider="groq", llm_model="custom-model")
    assert config.default_llm_model() == "custom-model"
