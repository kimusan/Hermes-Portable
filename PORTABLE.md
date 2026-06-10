# Hermes Portable v0.2.0

Hermes Portable is a USB-first wrapper around upstream Hermes Agent. It keeps durable Hermes state on the portable drive and keeps rebuildable runtime pieces on each host machine.

Vendored upstream Hermes version in this release: `v0.16.0`

## Design goals

- keep `HERMES_HOME` and user state on the USB stick
- keep `venv`, Node, npm artifacts, and dashboard build output off removable filesystems
- make normal Hermes CLI usage work through the wrapper with minimal friction
- support temporary/shared machines by cleaning up host-local runtime state when requested
- make wrapper-level update flows practical

## Portable state versus host cache

Portable state on USB:
- `data/.env`
- `data/config.yaml`
- `data/state.db`
- `data/sessions/`
- `data/skills/`
- `data/memories/`
- `data/auth.json`
- `data/platforms/`

Host-local runtime cache:
- Python virtualenv
- pip cache
- selected Python gateway SDKs
- Node runtime when needed
- npm cache
- WhatsApp bridge runtime
- dashboard source/build cache
- temporary files

The host-local cache root is platform-specific:
- Linux: `~/.cache/hermes-portable/<usb-id>/`
- macOS: `~/Library/Caches/HermesPortable/<usb-id>/`
- Windows: `%LOCALAPPDATA%\HermesPortable\<usb-id>\`

## Python compatibility handling

Upstream Hermes now declares `requires-python = ">=3.11,<3.14"`.

The wrapper does not assume the bootstrap Python is suitable for the Hermes venv. Instead it:
- reads the requirement from `src/hermes-agent/pyproject.toml`
- probes likely host interpreters
- prefers `python3.13`, `python3.12`, `python3.11`, then generic `python3`/`python`
- records the selected interpreter in the runtime cache
- rebuilds the cached venv automatically if it was created with an incompatible Python

## Runtime preparation

The wrapper prepares runtime pieces lazily:
- Python venv is created and populated on demand
- Node is reused from the host if a suitable version is already available
- otherwise Node is downloaded into the host-local runtime cache
- WhatsApp bridge assets are copied into host cache and `npm install` runs there
- dashboard source and frontend/TUI builds are copied and built in host cache

## Dashboard support

The wrapper adds a portable dashboard surface on top of upstream `hermes dashboard`.

Key points:
- `--dashboard` starts the Hermes dashboard using host-cached web and TUI assets
- by default it also starts the portable gateway child process
- `--dashboard-no-gateway` disables that autostart
- `--dashboard-status` and `--dashboard-stop` forward to the upstream dashboard process manager
- the wrapper opens the dashboard URL with the system opener rather than Python `webbrowser`
- the portable dashboard install path includes the extra package needed by the Kanban plugin API

The dashboard build outputs are redirected with:
- `HERMES_WEB_DIST`
- `HERMES_TUI_DIR`
- `HERMES_NODE`

That keeps the vendored USB source tree clean.

## Interactive CLI behavior

The wrapper uses a PTY-backed launch path for interactive Hermes sessions on POSIX systems. That is there to preserve behavior Hermes expects from a real terminal, including:
- list navigation with arrow keys
- interactive setup flows
- resumed sessions through `--resume`
- cleaner Ctrl-C handling

## Gateway model

Normal `./hermes-portable` behavior:
1. prepare runtime
2. start `hermes gateway run` as a child process
3. run Hermes CLI
4. stop the child gateway when Hermes exits

Other modes:
- `--gateway-only` runs only the gateway child
- `--no-gateway` runs Hermes without autostarting the gateway child
- `--dashboard` starts the dashboard and, by default, also starts the gateway child

The wrapper does not install a system service for normal portable use.

## Update flows

Wrapper update:
- `./hermes-portable --update-wrapper`
- fast-forwards the portable repo from its configured git upstream
- resets the host-local runtime cache afterward

Hermes source update:
- `./hermes-portable --update-hermes`
- `./hermes-portable --update-hermes-ref <tag-or-branch>`
- replaces `src/hermes-agent` with a refreshed upstream snapshot
- resets the host-local runtime cache afterward

Both update commands refuse to run on a dirty worktree.

## Temporary-machine cleanup

`--temporary` and `--cleanup-runtime-on-exit` remove the host-local runtime cache when the wrapper exits.

That cleanup is intentionally limited to rebuildable local artifacts. It does not delete USB state under `data/` and it does not try to uninstall unrelated host software that the wrapper merely reused from `PATH`.

## Deprecated environment cleanup

Older portable layouts used `TERMINAL_CWD` in `data/.env`.

This release removes that deprecated key automatically if it is still present. If you need the same behavior, move it to `config.yaml` under:

```yaml
terminal:
  cwd: /your/project/path
```

## Key files

Tracked wrapper files:
- `hermes-portable`
- `hermes-portable.bat`
- `bin/hermes-portable.sh`
- `bin/hermes-portable.ps1`
- `bin/hermes-portable.command`
- `bin/bootstrap_portable.py`
- `README.md`
- `PORTABLE.md`

Portable metadata created at runtime:
- `portable/manifest.json`
- `portable/runtime-state.json`

## Release summary for v0.2.0

This release includes:
- updated banner text to `Hermes Portable`
- generalized gateway preparation and platform action flags
- wrapper banner display for help and other wrapper-only commands
- temporary-machine cleanup mode
- update commands for both the wrapper and vendored Hermes source
- PTY-backed interactive Hermes handling improvements
- top-level `--resume` support
- automatic Python compatibility selection for Hermes `v0.16.0`
- portable dashboard support with host-cached assets
- dashboard gateway autostart and system-browser opening
- automatic cleanup of deprecated `TERMINAL_CWD` entries
