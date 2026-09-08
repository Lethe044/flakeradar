"""Static shell completion scripts for the flakeradar CLI.

Kept simple and hand-maintained (top-level subcommands only, no per-flag
completion) rather than dynamically introspecting argparse - that's
fragile across argparse versions and the payoff for a CLI this size is
small. Update _COMMAND_HELP when a new top-level command is added.
"""

from __future__ import annotations

_COMMAND_HELP = {
    "init": "Create a flakeradar.toml config file",
    "report": "Generate the flakiness report",
    "history": "Show recorded pass/fail history for one test",
    "stress": "Run a test repeatedly to check for flakiness",
    "analyze": "AI root-cause analysis",
    "quarantine": "Manage the quarantine list",
    "badge": "Generate an SVG flaky-test-count badge",
    "prune": "Delete old run history",
    "slow": "Show the slowest tests by duration",
    "import-junit": "Import a JUnit XML report",
    "diff": "Compare flakiness between two branches",
    "doctor": "Check your flakeradar setup",
    "completion": "Print a shell completion script",
}


def _bash_script() -> str:
    commands = " ".join(_COMMAND_HELP)
    return (
        "# flakeradar bash completion\n"
        '# Add to your shell profile: eval "$(flakeradar completion bash)"\n'
        "_flakeradar_completion() {\n"
        "    local cur commands\n"
        "    COMPREPLY=()\n"
        '    cur="${COMP_WORDS[COMP_CWORD]}"\n'
        f'    commands="{commands}"\n'
        '    if [ "$COMP_CWORD" -eq 1 ]; then\n'
        '        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )\n'
        "    fi\n"
        "}\n"
        "complete -F _flakeradar_completion flakeradar\n"
    )


def _zsh_script() -> str:
    entries = " ".join(f"'{cmd}:{desc}'" for cmd, desc in _COMMAND_HELP.items())
    return (
        "#compdef flakeradar\n"
        "# flakeradar zsh completion\n"
        '# Add to your shell profile: eval "$(flakeradar completion zsh)"\n'
        "_flakeradar() {\n"
        "    local -a commands\n"
        f"    commands=({entries})\n"
        "    _describe 'command' commands\n"
        "}\n"
        "compdef _flakeradar flakeradar\n"
    )


def _fish_script() -> str:
    lines = "\n".join(
        f'complete -c flakeradar -n "__fish_use_subcommand" -a "{cmd}" -d "{desc}"'
        for cmd, desc in _COMMAND_HELP.items()
    )
    return f"# flakeradar fish completion\n{lines}\n"


_GENERATORS = {"bash": _bash_script, "zsh": _zsh_script, "fish": _fish_script}


def generate_completion(shell: str) -> str:
    generator = _GENERATORS.get(shell)
    if generator is None:
        raise ValueError(f"Unsupported shell '{shell}'. Choose one of: {', '.join(_GENERATORS)}")
    return generator()
