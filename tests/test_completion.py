import pytest

from flakeradar.completion import generate_completion


def test_bash_completion_contains_all_commands():
    script = generate_completion("bash")
    assert "flakeradar" in script
    for cmd in ("init", "report", "diff", "doctor", "slow", "completion"):
        assert cmd in script


def test_bash_completion_registers_complete_function():
    script = generate_completion("bash")
    assert "complete -F _flakeradar_completion flakeradar" in script


def test_zsh_completion_has_compdef_header():
    script = generate_completion("zsh")
    assert script.startswith("#compdef flakeradar")
    assert "compdef _flakeradar flakeradar" in script


def test_fish_completion_has_complete_lines_per_command():
    script = generate_completion("fish")
    assert 'complete -c flakeradar -n "__fish_use_subcommand" -a "diff"' in script
    assert 'complete -c flakeradar -n "__fish_use_subcommand" -a "doctor"' in script


def test_unsupported_shell_raises_value_error():
    with pytest.raises(ValueError):
        generate_completion("powershell")


def test_unsupported_shell_error_lists_valid_options():
    with pytest.raises(ValueError) as exc_info:
        generate_completion("nushell")
    assert "bash" in str(exc_info.value)
    assert "zsh" in str(exc_info.value)
    assert "fish" in str(exc_info.value)
