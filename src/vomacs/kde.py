from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any


def _run_busctl(args: list[str]) -> str:
    result = subprocess.run(
        ["busctl", "--user", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _parse_a_sv(output: str) -> dict[str, Any]:
    tokens = shlex.split(output)
    if len(tokens) < 2 or tokens[0] != "a{sv}":
        raise ValueError(f"Unexpected busctl payload: {output!r}")

    idx = 2
    parsed: dict[str, Any] = {}
    while idx < len(tokens):
        key = tokens[idx]
        idx += 1
        signature = tokens[idx]
        idx += 1

        if signature == "s":
            parsed[key] = tokens[idx]
            idx += 1
        elif signature == "b":
            parsed[key] = tokens[idx] == "true"
            idx += 1
        elif signature == "i":
            parsed[key] = int(tokens[idx])
            idx += 1
        elif signature == "d":
            parsed[key] = float(tokens[idx])
            idx += 1
        elif signature == "as":
            count = int(tokens[idx])
            idx += 1
            parsed[key] = tokens[idx : idx + count]
            idx += count
        else:
            raise ValueError(f"Unsupported KWin value signature: {signature}")

    return parsed


def query_active_window() -> dict[str, Any] | None:
    output = _run_busctl(
        ["call", "org.kde.KWin", "/KWin", "org.kde.KWin", "queryWindowInfo"]
    )
    if not output:
        return None
    return _parse_a_sv(output)


def get_window_info(uuid: str) -> dict[str, Any] | None:
    output = _run_busctl(
        ["call", "org.kde.KWin", "/KWin", "org.kde.KWin", "getWindowInfo", "s", uuid]
    )
    if not output:
        return None
    return _parse_a_sv(output)


def set_clipboard_contents(text: str) -> None:
    subprocess.run(
        [
            "busctl",
            "--user",
            "call",
            "org.kde.klipper",
            "/klipper",
            "org.kde.klipper.klipper",
            "setClipboardContents",
            "s",
            text,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def target_env(target: dict[str, Any] | None) -> dict[str, str]:
    if not target:
        return {}

    env: dict[str, str] = {"VT_TARGET_WINDOW_JSON": json.dumps(target, sort_keys=True)}
    for key, value in target.items():
        env_key = "VT_TARGET_" + "".join(
            ch if ch.isalnum() else "_" for ch in key.upper()
        )
        if isinstance(value, list):
            env[env_key] = json.dumps(value)
        elif value is None:
            env[env_key] = ""
        else:
            env[env_key] = str(value)
    return env
