# vomacsd

`vomacsd` is a small voice-transcription daemon with three explicit goals:

- keep the core flow CLI-first and daemon-friendly
- make start/stop/transcription/output lifecycle hooks first-class
- treat window targeting and text insertion as adapter problems, not hardcoded keystrokes

The first cut in this repo is intentionally narrow but usable:

- `ffmpeg` records from the default Pulse/PipeWire input
- OpenAI file transcription and Realtime transcription are both supported
- optional ffmpeg compression can shrink uploads before transcription
- KDE Wayland start-window metadata is captured from KWin over D-Bus
- output is pluggable: `stdout`, `clipboard`, `command`, `clipboard_then_command`
- hooks run around recording, transcription, and output stages
- text post-processing filters are chainable

## Why this shape

On KDE Wayland, "put text back into the exact window that was active when recording started"
is only partly generic:

- capturing metadata for that start-window is feasible and implemented
- generic text injection into an arbitrary unfocused app is not a universal Wayland feature
- the right design is to remember the target window and pass its metadata to an output adapter

That is why `vomacsd` stores target metadata up front and exposes it via environment variables
to output commands and hooks. The daemon does not pretend that `Ctrl+V` is universal.

## Commands

Set up the repo with `uv`:

```bash
uv sync
uv run vomacsd --help
```

Install from source with `pip` if you want a plain packaging smoke check:

```bash
python -m pip install .
vomacsd --help
```

Start the daemon:

```bash
uv run python -m vomacsd init-config
uv run python -m vomacsd serve
```

Control it from another shell:

```bash
uv run python -m vomacsd status
uv run python -m vomacsd start
uv run python -m vomacsd stop
uv run python -m vomacsd toggle
uv run python -m vomacsd cancel
uv run python -m vomacsd reload
```

There is also a user-service template at [contrib/vomacsd.service](/home/morty/Software/dtft/vomacs/contrib/vomacsd.service).

## Auth and config

Initialize the default config file:

```bash
uv run python -m vomacsd init-config
```

By default this writes to `~/.config/vomacsd/config.json`.

Authentication can be configured either by placing an API key directly in the config
or by exporting the environment variable named by `openai.api_key_env`, which defaults
to `OPENAI_API_KEY`:

```bash
export OPENAI_API_KEY=...
uv run python -m vomacsd print-default-config
```

The daemon socket defaults to `${XDG_RUNTIME_DIR}/vomacsd/control.sock` and falls back to
`/tmp/vomacsd-<uid>/vomacsd/control.sock` when `XDG_RUNTIME_DIR` is unset.

## Smoke test

For a minimal local smoke check that does not hit audio capture or OpenAI:

```bash
uv run vomacsd --help
PYTHONPATH=python-src python -m unittest discover -s tests -v
python -c "from vomacsd.config import default_socket_path; assert default_socket_path().name == 'control.sock'"
```

## Release assets

Tagging `v<version>` publishes release artifacts from the tagged commit on GitHub:

- `vomacsd-<version>.tar.gz`
- `vomacsd-<version>-py3-none-any.whl`
- `SHA256SUMS`

The installed service is a user service tied to `graphical-session.target`. It starts the KDE helper
as a companion service, and that helper exits unless `vomacsd-kde-helper check-kde-env` detects a
KDE or Plasma session.

The package metadata is currently marked `custom:unlicensed`. Add an explicit project license before
the first public release if you want normal open-source license metadata.

## Local environment

For local development, prefer a repo-local `uv` environment:

```bash
uv sync
uv run python -m vomacsd --help
uv run ruff format --check .
uv run ruff check .
uv run mypy
PYTHONPATH=python-src python -m unittest discover -s tests -v
```

If you specifically need the old conda workflow for local system integration experiments,
keep it separate from the default `uv` environment.

## Config

The default config is written to `~/.config/vomacsd/config.json`.

## OpenAI models and cost

`vomacsd` can currently talk to OpenAI in two ways:

- `openai.backend = "file"`
  - calls `/v1/audio/transcriptions` after recording stops
- `openai.backend = "realtime"`
  - creates a transcription session via `/v1/realtime/client_secrets`
  - then opens a WebSocket to `/v1/realtime` and streams PCM audio while recording is still active

Model options worth caring about here, with pricing checked on March 21, 2026:

- `gpt-4o-mini-transcribe`
  - lower cost default
  - `$0.003 / minute`
- `gpt-4o-transcribe`
  - higher-accuracy option
  - `$0.006 / minute`
- `whisper-1`
  - older general-purpose option
  - `$0.006 / minute`

The config default is:

```json
{
  "openai": {
    "backend": "file",
    "model": "gpt-4o-mini-transcribe"
  }
}
```

If you want the better accuracy/cost tradeoff to skew toward accuracy, change it to:

```json
{
  "openai": {
    "model": "gpt-4o-transcribe"
  }
}
```

Pricing changes over time. Re-check:

- https://platform.openai.com/docs/pricing/
- https://developers.openai.com/api/docs/models/gpt-4o-mini-transcribe
- https://developers.openai.com/api/docs/models/gpt-4o-transcribe
- https://developers.openai.com/api/docs/models/whisper-1

Important fields:

- `openai.backend`
  - `file`: record first, then upload the completed audio file
  - `realtime`: stream live audio over the Realtime transcription endpoint while recording
- `openai.model`
  - defaults to `gpt-4o-mini-transcribe`
  - recommended choices:
    - `gpt-4o-mini-transcribe` for lower cost
    - `gpt-4o-transcribe` for higher accuracy
    - `whisper-1` if you explicitly want the older Whisper path
- `openai.realtime.sample_rate_hz`
  - input sample rate for the Realtime backend, default `24000`
- `openai.realtime.chunk_ms`
  - chunk size for audio frames sent to OpenAI, default `100`
- `openai.realtime.turn_detection`
  - defaults to `server_vad`
  - this is what lets the Realtime backend finalize segments during recording instead of waiting for `stop`
- `openai.realtime.noise_reduction`
  - defaults to `{"type": "near_field"}`
- `openai.realtime.finalize_timeout_seconds`
  - how long the daemon waits for final segment completion when you stop recording
- `target.mode`
  - `focused_on_start`: remember the active KDE window when recording starts
  - `focused_on_finish`: resolve the active KDE window when output is delivered
  - `explicit_uuid`: resolve a specific KWin window UUID
- `audio.compress_before_transcription`
  - when enabled, the daemon transcodes the recorded WAV to a smaller upload file before calling OpenAI
  - only used by the `file` backend
- `audio.compression_format`
  - upload format suffix, default `mp3`
- `audio.compression_args`
  - ffmpeg args for the upload transcode, default `["-vn", "-c:a", "libmp3lame", "-b:a", "64k"]`
- `output.mode`
  - `clipboard`: write transcript to clipboard only
  - `command`: run `output.command`, transcript on stdin
  - `clipboard_then_command`: set clipboard first, then run `output.command`
- `hooks.*`
  - commands run at lifecycle boundaries
- `pipelines.before_transcription`
  - commands run after recording stops and before transcription starts
  - only used by the `file` backend, because a Realtime stream has already been sent live
- `pipelines.after_transcription`
  - stdin/stdout text filters chained after transcription and before output

The daemon exports target metadata such as:

- `VT_TARGET_WINDOW_JSON`
- `VT_TARGET_UUID`
- `VT_TARGET_DESKTOPFILE`
- `VT_TARGET_RESOURCECLASS`
- `VT_TARGET_CAPTION`

It also exports session data such as:

- `VT_SESSION_ID`
- `VT_AUDIO_PATH`
- `VT_UPLOAD_AUDIO_PATH`
- `VT_PHASE`

## Example hooks

Visual notification on recording start:

```json
{
  "hooks": {
    "recording_started": ["notify-send 'vomacsd' 'Recording started'"],
    "recording_stopped": ["notify-send 'vomacsd' 'Recording stopped'"],
    "transcription_started": ["notify-send 'vomacsd' 'Transcribing'"],
    "transcription_finished": ["notify-send 'vomacsd' 'Transcript ready'"]
  }
}
```

Text post-processing:

```json
{
  "pipelines": {
    "after_transcription": [
      "sed 's/\\bteh\\b/the/g'",
      "perl -0pe 's/\\s+/ /g'"
    ]
  }
}
```

Clipboard plus custom paste adapter:

```json
{
  "output": {
    "mode": "clipboard_then_command",
    "command": "$HOME/bin/paste-target-adapter"
  }
}
```

That adapter receives the transcript on stdin and the target-window metadata in env vars.
This is where app-specific behavior belongs, for example:

- Emacs-specific insertion via `emacsclient`
- a future `ydotool` or EIS-based paste path
- terminal-specific delivery for Konsole, kitty, or wezterm

Compression before upload:

```json
{
  "audio": {
    "compress_before_transcription": true,
    "compression_format": "mp3",
    "compression_args": ["-vn", "-c:a", "libmp3lame", "-b:a", "64k"]
  }
}
```

Enable the Realtime transcription backend:

```json
{
  "openai": {
    "backend": "realtime",
    "model": "gpt-4o-mini-transcribe",
    "realtime": {
      "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500
      }
    }
  }
}
```

This backend requires the Python `websocket-client` package, which is included in
`pyproject.toml`.

## Current limits

- `start` and `stop` still arm and disarm the daemon manually. There is no standalone hotkey capture in-process yet.
- `server_vad` is supported through the Realtime endpoint, but the daemon does not yet expose dedicated `speech_started` or `speech_stopped` hooks.
- `pipelines.before_transcription` and upload compression only apply to the `file` backend.
- Generic "paste into any arbitrary Wayland window" is not implemented, because that should
  be adapter-specific and compositor-aware.

## Next steps

The obvious next pieces are:

1. dedicated push-to-talk and hold-mode control paths
2. a proper KDE input adapter for text injection
3. optional app adapters for Emacs and Konsole
