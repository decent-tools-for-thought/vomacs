from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "openai": {
        "api_key": None,
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini-transcribe",
        "backend": "file",
        "language": None,
        "prompt": None,
        "temperature": None,
        "timeout_seconds": 120,
        "realtime": {
            "url": "wss://api.openai.com/v1/realtime",
            "sample_rate_hz": 24000,
            "chunk_ms": 100,
            "connect_timeout_seconds": 20,
            "finalize_timeout_seconds": 15,
            "noise_reduction": {"type": "near_field"},
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.5,
                "prefix_padding_ms": 300,
                "silence_duration_ms": 500,
            },
            "include": [],
        },
    },
    "audio": {
        "ffmpeg_path": "ffmpeg",
        "input_format": "pulse",
        "input_device": "default",
        "channels": 1,
        "sample_rate_hz": 16000,
        "keep_recordings": False,
        "recordings_dir": None,
        "compress_before_transcription": False,
        "compression_format": "mp3",
        "compression_args": ["-vn", "-c:a", "libmp3lame", "-b:a", "64k"],
        "extra_input_args": [],
        "extra_output_args": [],
    },
    "target": {
        "provider": "kde_kwin",
        "mode": "focused_on_start",
        "explicit_uuid": None,
    },
    "output": {
        "mode": "clipboard",
        "command": None,
        "clipboard_backend": "auto",
    },
    "hooks": {
        "recording_started": [],
        "recording_stopped": [],
        "recording_cancelled": [],
        "transcription_started": [],
        "transcription_finished": [],
        "transcription_failed": [],
        "output_started": [],
        "output_finished": [],
        "output_failed": [],
    },
    "pipelines": {
        "before_transcription": [],
        "after_transcription": [],
    },
}


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "vomacsd"


def state_dir() -> Path:
    return (
        Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        / "vomacsd"
    )


def runtime_dir() -> Path:
    default = Path("/tmp") / f"vomacsd-{os.getuid()}"
    return Path(os.environ.get("XDG_RUNTIME_DIR", default)) / "vomacsd"


def default_config_path() -> Path:
    return config_dir() / "config.json"


def default_socket_path() -> Path:
    return runtime_dir() / "control.sock"


def ensure_directories(config_path: Path | None = None) -> None:
    target_config_dir = config_path.parent if config_path else config_dir()
    target_config_dir.mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)
    runtime_dir().mkdir(parents=True, exist_ok=True)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = _deep_merge(current, value)
        else:
            result[key] = value
    return result


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_config_path()
    ensure_directories(config_path)
    if not config_path.exists():
        write_default_config(config_path)
    with config_path.open("r", encoding="utf-8") as fh:
        user_config = json.load(fh)
    return _deep_merge(DEFAULT_CONFIG, user_config)


def write_default_config(path: Path | None = None, *, overwrite: bool = False) -> Path:
    config_path = path or default_config_path()
    ensure_directories(config_path)
    if config_path.exists() and not overwrite:
        return config_path
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        json.dump(DEFAULT_CONFIG, fh, indent=2)
        fh.write("\n")
    return config_path
