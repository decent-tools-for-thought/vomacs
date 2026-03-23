<div align="center">

# vomacsd

[![Release](https://img.shields.io/github/v/release/decent-tools-for-thought/vomacs?sort=semver&color=c0c0c0)](https://github.com/decent-tools-for-thought/vomacs/releases)
![Python](https://img.shields.io/badge/python-3.11%2B-d4d4d8)
![License](https://img.shields.io/badge/license-0BSD-a1a1aa)

Hookable KDE Wayland voice-transcription daemon with foreground service mode, control commands, and clipboard or command-based transcript routing.

</div>

> [!IMPORTANT]
> This codebase is entirely AI-generated. It is useful to me, I hope it might be useful to others, and issues and contributions are welcome.

## Map
- [Install](#install)
- [Functionality](#functionality)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Development](#development)
- [Credits](#credits)

## Install

From a checkout:

```bash
uv sync
uv run python -m vomacsd --help
```

The packaged entry points are:

- `vomacsd`
- `vomacsd-kde-helper`

## Functionality

### Service Lifecycle
- `vomacsd serve`: run the transcription daemon in the foreground.
- `vomacsd start`: tell the running daemon to begin recording or transcription.
- `vomacsd stop`: tell the running daemon to stop the current recording or transcription cycle.
- `vomacsd toggle`: toggle the active recording state.
- `vomacsd cancel`: cancel the current operation.
- `vomacsd status`: fetch daemon status over the control socket.
- `vomacsd reload`: reload daemon configuration.

### Config Initialization And Inspection
- `vomacsd init-config`: write a default config file.
- `vomacsd init-config --force`: overwrite an existing config file.
- `vomacsd print-default-config`: print the built-in default config JSON.

### Runtime Model
- The daemon exposes a Unix socket control interface.
- The daemon supports upload-after-recording transcription through `openai.backend = "file"`.
- The daemon supports streamed transcription through `openai.backend = "realtime"`.
- The daemon is designed for KDE Wayland workflows with clipboard and command hooks.

## Configuration

- Default config path: `~/.config/vomacsd/config.json`
- Default API key env var: `OPENAI_API_KEY`
- Default socket path: `${XDG_RUNTIME_DIR}/vomacsd/control.sock`

There is also a user-service template at `contrib/vomacsd.service`.

## Quick Start

```bash
uv run python -m vomacsd init-config

uv run python -m vomacsd serve

uv run python -m vomacsd status
uv run python -m vomacsd start
uv run python -m vomacsd stop
uv run python -m vomacsd toggle
```

## Development

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
PYTHONPATH=python-src python -m unittest discover -s tests -v
```

## Credits

This project is built for KDE/Plasma desktop workflows and OpenAI transcription APIs and is not affiliated with KDE, Plasma, or OpenAI.

Credit goes to those upstream projects for the desktop integration surface and speech models this daemon relies on.
