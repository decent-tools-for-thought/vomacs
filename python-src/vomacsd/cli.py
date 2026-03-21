from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any

from vomacsd.config import (
    DEFAULT_CONFIG,
    default_config_path,
    default_socket_path,
    write_default_config,
)
from vomacsd.daemon import serve_forever


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vomacsd",
        description=(
            "vomacsd: hookable voice-transcription daemon for KDE Wayland.\n\n"
            "OpenAI transcription model options and pricing "
            "(checked 2026-03-21):\n"
            "  gpt-4o-mini-transcribe   $0.003/minute\n"
            "  gpt-4o-transcribe        $0.006/minute\n"
            "  whisper-1                $0.006/minute\n\n"
            "These models can back the file endpoint and the Realtime transcription "
            "endpoint. gpt-4o-mini-transcribe is the cheaper default and "
            "gpt-4o-transcribe is the higher-accuracy option."
        ),
        epilog=(
            "Pricing changes over time. Verify current pricing at:\n"
            "  https://platform.openai.com/docs/pricing/\n"
            "Model docs:\n"
            "  https://developers.openai.com/api/docs/models/gpt-4o-mini-transcribe\n"
            "  https://developers.openai.com/api/docs/models/gpt-4o-transcribe\n"
            "  https://developers.openai.com/api/docs/models/whisper-1\n"
            "Realtime guides:\n"
            "  https://developers.openai.com/api/docs/guides/realtime-transcription\n"
            "  https://developers.openai.com/api/docs/guides/realtime-vad"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=default_config_path())
    parser.add_argument("--socket", type=Path, default=default_socket_path())

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve")
    sub.add_parser("start")
    sub.add_parser("stop")
    sub.add_parser("toggle")
    sub.add_parser("cancel")
    sub.add_parser("status")
    sub.add_parser("reload")
    sub.add_parser("print-default-config")

    init_parser = sub.add_parser("init-config")
    init_parser.add_argument("--force", action="store_true")

    return parser


def _send(socket_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        raw = client.recv(1024 * 1024)
    return json.loads(raw.decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "serve":
        try:
            serve_forever(config_path=args.config, socket_path=args.socket)
        except KeyboardInterrupt:
            return 0
        return 0

    if args.command == "print-default-config":
        print(json.dumps(DEFAULT_CONFIG, indent=2))
        return 0

    if args.command == "init-config":
        path = write_default_config(args.config, overwrite=args.force)
        print(path)
        return 0

    try:
        response = _send(args.socket, {"action": args.command})
    except FileNotFoundError:
        print(
            f"Daemon socket not found at {args.socket}. Start the daemon with "
            f"`vomacsd --config {args.config} --socket {args.socket} serve`.",
            file=sys.stderr,
        )
        return 1
    except ConnectionRefusedError:
        print(f"Could not connect to daemon socket at {args.socket}.", file=sys.stderr)
        return 1
    except PermissionError:
        print(
            f"Could not access daemon socket at {args.socket}. "
            "For local repo testing, prefer a socket path under /tmp.",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(response, indent=2, sort_keys=True))
    return 0 if response.get("ok") else 1
