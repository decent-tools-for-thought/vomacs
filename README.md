# vomacsd

[![Release](https://img.shields.io/github/v/release/decent-tools-for-thought/vomacs?sort=semver)](https://github.com/decent-tools-for-thought/vomacs/releases)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-0BSD-green)

Voice transcription daemon for KDE Wayland with clipboard and command hooks.

> [!IMPORTANT]
> This codebase is entirely AI-generated. It is useful to me, I hope it might be useful to others, and issues and contributions are welcome.

## Why This Exists

- Record speech and turn it into text from a desktop-first workflow.
- Route transcripts into the clipboard or a custom command.
- Support both upload-after-recording and realtime transcription paths.

## Install

From a checkout:

```bash
uv sync
uv run python -m vomacsd --help
```

The packaged entry points are:

- `vomacsd`
- `vomacsd-kde-helper`

## Quick Start

Initialize config:

```bash
uv run python -m vomacsd init-config
```

Run in the foreground:

```bash
uv run python -m vomacsd serve
```

Control it from another shell:

```bash
uv run python -m vomacsd status
uv run python -m vomacsd start
uv run python -m vomacsd stop
uv run python -m vomacsd toggle
```

There is also a user-service template at `contrib/vomacsd.service`.

## Configuration

- Default config path: `~/.config/vomacsd/config.json`
- Default API key env var: `OPENAI_API_KEY`
- Default socket path: `${XDG_RUNTIME_DIR}/vomacsd/control.sock`

The daemon supports:

- `openai.backend = "file"` for upload-after-recording transcription
- `openai.backend = "realtime"` for streamed transcription

## Development

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
PYTHONPATH=python-src python -m unittest discover -s tests -v
```

## Credits

This project builds on KDE/Plasma desktop tooling and OpenAI transcription APIs. Credit goes to those upstream projects for the desktop integration surface and speech models this daemon relies on.
