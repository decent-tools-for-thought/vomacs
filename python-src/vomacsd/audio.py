from __future__ import annotations

import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def start_recording(config: dict[str, Any], output_path: Path) -> subprocess.Popen[str]:
    audio = config["audio"]
    command = [
        audio["ffmpeg_path"],
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        audio["input_format"],
        *audio.get("extra_input_args", []),
        "-i",
        audio["input_device"],
        "-ac",
        str(audio["channels"]),
        "-ar",
        str(audio["sample_rate_hz"]),
        *audio.get("extra_output_args", []),
        str(output_path),
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    time.sleep(0.25)
    exit_code = process.poll()
    if exit_code is not None:
        stderr = ""
        if process.stderr:
            stderr = process.stderr.read().strip()
        raise RuntimeError(f"ffmpeg exited immediately with code {exit_code}: {stderr}")

    return process


def stop_recording(
    process: subprocess.Popen[str], *, timeout_seconds: float = 10.0
) -> None:
    if process.poll() is not None:
        return

    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5.0)


def start_pcm_stream(
    config: dict[str, Any],
    *,
    sample_rate_hz: int,
    channels: int = 1,
) -> subprocess.Popen[bytes]:
    audio = config["audio"]
    command = [
        audio["ffmpeg_path"],
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-f",
        audio["input_format"],
        *audio.get("extra_input_args", []),
        "-i",
        audio["input_device"],
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate_hz),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "pipe:1",
    ]

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    time.sleep(0.25)
    exit_code = process.poll()
    if exit_code is not None:
        stderr = b""
        if process.stderr:
            stderr = process.stderr.read().strip()
        raise RuntimeError(
            f"ffmpeg exited immediately with code {exit_code}: "
            f"{stderr.decode('utf-8', errors='replace')}"
        )

    if process.stdout is None:
        raise RuntimeError("ffmpeg did not expose a PCM stdout pipe")
    return process


def pcm_chunk_size_bytes(
    *,
    sample_rate_hz: int,
    channels: int,
    chunk_ms: int,
    sample_width_bytes: int = 2,
) -> int:
    samples_per_chunk = max(1, (sample_rate_hz * chunk_ms) // 1000)
    return samples_per_chunk * channels * sample_width_bytes


def maybe_prepare_upload_audio(config: dict[str, Any], audio_path: Path) -> Path:
    audio = config["audio"]
    if not audio.get("compress_before_transcription"):
        return audio_path

    suffix = "." + str(audio.get("compression_format", "mp3")).lstrip(".")
    fd, raw_path = tempfile.mkstemp(
        prefix=f"{audio_path.stem}-upload-",
        suffix=suffix,
        dir=str(audio_path.parent),
    )
    Path(raw_path).unlink(missing_ok=True)

    command = [
        audio["ffmpeg_path"],
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(audio_path),
        *audio.get("compression_args", []),
        raw_path,
    ]
    subprocess.run(
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    return Path(raw_path)
