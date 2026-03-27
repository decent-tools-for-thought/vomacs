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
- [Credits](#credits)

## Install
$$\color{#D4D4D8}Install \space \color{#A1A1AA}Tool$$

From a checkout:

```bash
uv sync                             # install project dependencies
uv run python -m vomacsd --help     # inspect the daemon CLI
```

The packaged entry points are:

- `vomacsd`
- `vomacsd-kde-helper`

## Functionality
$$\color{#D4D4D8}Service \space \color{#A1A1AA}Lifecycle$$
- `vomacsd serve`: run the transcription daemon in the foreground.
- `vomacsd start`: tell the running daemon to begin recording or transcription.
- `vomacsd stop`: tell the running daemon to stop the current recording or transcription cycle.
- `vomacsd toggle`: toggle the active recording state.
- `vomacsd cancel`: cancel the current operation.
- `vomacsd status`: fetch daemon status over the control socket.
- `vomacsd reload`: reload daemon configuration.

$$\color{#D4D4D8}Config \space \color{#A1A1AA}Setup$$
- `vomacsd init-config`: write a default config file.
- `vomacsd init-config --force`: overwrite an existing config file.
- `vomacsd print-default-config`: print the built-in default config JSON.

$$\color{#D4D4D8}Runtime \space \color{#A1A1AA}Model$$
- The daemon exposes a Unix socket control interface.
- The daemon supports upload-after-recording transcription through `openai.backend = "file"`.
- The daemon supports streamed transcription through `openai.backend = "realtime"`.
- The daemon is designed for KDE Wayland workflows with clipboard and command hooks.

## Configuration
$$\color{#D4D4D8}User \space \color{#A1A1AA}Config$$

- Default config path: `~/.config/vomacsd/config.json`
- Default API key env var: `OPENAI_API_KEY`
- Default socket path: `${XDG_RUNTIME_DIR}/vomacsd/control.sock`

There is also a user-service template at `contrib/vomacsd.service`.

## Quick Start
$$\color{#D4D4D8}Try \space \color{#A1A1AA}Daemon$$

```bash
uv run python -m vomacsd init-config    # write the default config file

uv run python -m vomacsd serve          # run the daemon in the foreground

uv run python -m vomacsd status         # inspect daemon status
uv run python -m vomacsd start          # begin recording or transcription
uv run python -m vomacsd stop           # stop the active capture
uv run python -m vomacsd toggle         # toggle the active state
```

## Credits

This project is built for KDE/Plasma desktop workflows and OpenAI transcription APIs and is not affiliated with KDE, Plasma, or OpenAI.

Credit goes to those upstream projects for the desktop integration surface and speech models this daemon relies on.
