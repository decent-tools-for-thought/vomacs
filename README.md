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

Start the daemon:

```bash
PYTHONPATH=src python3 -m vomacsd init-config
PYTHONPATH=src python3 -m vomacsd serve
```

Control it from another shell:

```bash
PYTHONPATH=src python3 -m vomacsd status
PYTHONPATH=src python3 -m vomacsd start
PYTHONPATH=src python3 -m vomacsd stop
PYTHONPATH=src python3 -m vomacsd toggle
PYTHONPATH=src python3 -m vomacsd cancel
PYTHONPATH=src python3 -m vomacsd reload
```

There is also a user-service template at [contrib/vomacsd.service](/home/morty/Software/vomacs/contrib/vomacsd.service).

## Arch install

The release flow now targets Arch installation in two ways:

- a prebuilt `vomacsd-<version>-1-any.pkg.tar.zst` package asset on each GitHub release
- release source assets for manual `makepkg` builds:
  - a release source tarball
  - a rendered `PKGBUILD`
  - a rendered `SRCINFO`
  - `vomacsd.install`

For the normal install path on Arch, download the package asset from the GitHub release and install it:

```bash
sudo pacman -U ./vomacsd-<version>-1-any.pkg.tar.zst
systemctl --user daemon-reload
systemctl --user enable --now vomacsd.service
```

If you prefer to build from the release metadata instead:

```bash
makepkg -si
systemctl --user daemon-reload
systemctl --user enable --now vomacsd.service
```

The installed service is a user service tied to `graphical-session.target`. It starts the KDE helper
as a companion service, and that helper exits unless `vomacsd-kde-helper check-kde-env` detects a
KDE or Plasma session.

The package metadata is currently marked `custom:unlicensed`. Add an explicit project license before
the first public release if you want normal open-source license metadata.

## Local environment

For local development, a repo-local conda environment works well and keeps the Realtime
dependency isolated from your base Python:

```bash
conda create -y -p .conda/vomacsd python=3.13 pip
conda run -p .conda/vomacsd python -m pip install --no-build-isolation -e .
conda run -p .conda/vomacsd python -m vomacsd --help
```

The `.conda/` directory is ignored by git.

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
