from __future__ import annotations

import os
import subprocess
from typing import Any

from vomacs import kde


def resolve_target(
    config: dict[str, Any], start_target: dict[str, Any] | None
) -> dict[str, Any] | None:
    target_config = config["target"]
    provider = target_config.get("provider")
    if provider != "kde_kwin":
        return start_target

    try:
        mode = target_config.get("mode")
        if mode == "focused_on_start":
            return start_target
        if mode == "focused_on_finish":
            return kde.query_active_window()
        if mode == "explicit_uuid":
            explicit_uuid = target_config.get("explicit_uuid")
            if not explicit_uuid:
                return None
            return kde.get_window_info(str(explicit_uuid))
    except Exception:
        return start_target
    return start_target


def deliver_text(
    config: dict[str, Any],
    text: str,
    *,
    target: dict[str, Any] | None,
    env: dict[str, str],
) -> None:
    output_config = config["output"]
    mode = output_config.get("mode")

    if mode == "stdout":
        print(text, flush=True)
        return

    if mode == "clipboard":
        _set_clipboard(text, output_config)
        return

    if mode == "command":
        _run_output_command(output_config, text, env, target)
        return

    if mode == "clipboard_then_command":
        _set_clipboard(text, output_config)
        _run_output_command(output_config, text, env, target)
        return

    raise RuntimeError(f"Unsupported output mode: {mode}")


def _set_clipboard(text: str, output_config: dict[str, Any]) -> None:
    backend = output_config.get("clipboard_backend", "auto")
    if backend in {"auto", "kde_klipper"}:
        try:
            kde.set_clipboard_contents(text)
            return
        except Exception:
            if backend == "kde_klipper":
                raise

    if backend in {"auto", "xclip"}:
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            check=True,
            input=text,
            text=True,
            capture_output=True,
        )
        return

    raise RuntimeError(f"No supported clipboard backend available for {backend}")


def _run_output_command(
    output_config: dict[str, Any],
    text: str,
    env: dict[str, str],
    target: dict[str, Any] | None,
) -> None:
    command = output_config.get("command")
    if not command:
        raise RuntimeError("output.command must be set when output.mode uses a command")

    merged_env = os.environ.copy()
    merged_env.update(env)
    merged_env.update(kde.target_env(target))
    subprocess.run(
        ["/bin/sh", "-lc", str(command)],
        check=True,
        env=merged_env,
        input=text,
        text=True,
        capture_output=True,
    )
