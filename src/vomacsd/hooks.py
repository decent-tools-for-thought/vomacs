from __future__ import annotations

import os
import subprocess
from typing import Any


def run_commands(commands: list[str], env: dict[str, str], *, stdin_text: str | None = None) -> None:
    merged_env = os.environ.copy()
    merged_env.update(env)
    for command in commands:
        subprocess.run(
            ["/bin/sh", "-lc", command],
            check=True,
            env=merged_env,
            input=stdin_text,
            text=True,
            capture_output=True,
        )


def run_text_filters(commands: list[str], text: str, env: dict[str, str]) -> str:
    if not commands:
        return text

    merged_env = os.environ.copy()
    merged_env.update(env)
    current = text
    for command in commands:
        result = subprocess.run(
            ["/bin/sh", "-lc", command],
            check=True,
            env=merged_env,
            input=current,
            text=True,
            capture_output=True,
        )
        current = result.stdout
    return current


def hook_list(config: dict[str, Any], event_name: str) -> list[str]:
    hooks = config.get("hooks", {})
    values = hooks.get(event_name, [])
    if isinstance(values, list):
        return [str(item) for item in values]
    raise TypeError(f"Hook list for {event_name!r} must be a list of strings")
