from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from vomacs.config import default_socket_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vomacs-kde-helper",
        description="KDE session helper for vomacs.",
    )
    parser.add_argument("--socket", type=Path, default=default_socket_path())
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve")
    serve.add_argument("--poll-interval", type=float, default=0.5)

    sub.add_parser("check-kde-env")
    return parser


def _send(socket_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        raw = client.recv(1024 * 1024)
    return json.loads(raw.decode("utf-8"))


def _is_kde_session(env: dict[str, str] | None = None) -> bool:
    current = env or os.environ
    values = [
        current.get("XDG_CURRENT_DESKTOP", ""),
        current.get("XDG_SESSION_DESKTOP", ""),
        current.get("DESKTOP_SESSION", ""),
        current.get("KDE_FULL_SESSION", ""),
    ]
    joined = ":".join(values).upper()
    return (
        "KDE" in joined
        or "PLASMA" in joined
        or current.get("KDE_FULL_SESSION") == "true"
    )


def _notify(summary: str, body: str | None = None, *, urgency: str = "normal") -> None:
    command = ["notify-send", "-a", "vomacs", "-u", urgency, summary]
    if body:
        command.append(body)
    try:
        subprocess.run(
            command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def _result_signature(result: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if not isinstance(result, dict):
        return None
    return (
        result.get("status"),
        result.get("session_id"),
        result.get("completed_at"),
        result.get("error"),
    )


def _status(socket_path: Path) -> dict[str, Any] | None:
    try:
        return _send(socket_path, {"action": "status"})
    except (
        FileNotFoundError,
        ConnectionRefusedError,
        PermissionError,
        OSError,
        json.JSONDecodeError,
    ):
        return None


def _handle_phase_change(phase: str | None, previous_phase: str | None) -> None:
    if phase == previous_phase:
        return
    if phase == "recording":
        _notify("vomacs", "Recording started")
    elif phase == "processing":
        _notify("vomacs", "Transcribing")


def _handle_result_change(result: dict[str, Any] | None) -> None:
    if not isinstance(result, dict):
        return
    status = str(result.get("status", ""))
    if status == "ok":
        _notify("vomacs", "Transcript delivered")
    elif status == "cancelled":
        _notify("vomacs", "Recording cancelled")
    elif status == "error":
        _notify(
            "vomacs",
            str(result.get("error", "Transcription failed")),
            urgency="critical",
        )


def serve(socket_path: Path, *, poll_interval: float) -> int:
    if not _is_kde_session():
        return 0

    last_phase: str | None = None
    last_result: tuple[Any, ...] | None = None

    while True:
        status = _status(socket_path)
        phase = None
        result = None
        if status and status.get("ok"):
            phase = str(status.get("phase", ""))
            result = status.get("last_result")

        _handle_phase_change(phase, last_phase)
        signature = _result_signature(result)
        if signature != last_result:
            _handle_result_change(result if isinstance(result, dict) else None)
        last_phase = phase
        last_result = signature
        time.sleep(max(0.1, poll_interval))


def main(argv: list[str] | None = None) -> int:
    cli_parser = _parser()
    args = cli_parser.parse_args(argv)
    if args.command is None:
        cli_parser.print_help()
        return 0

    if args.command == "check-kde-env":
        return 0 if _is_kde_session() else 1

    if args.command == "serve":
        try:
            return serve(args.socket, poll_interval=args.poll_interval)
        except KeyboardInterrupt:
            return 0

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 1
