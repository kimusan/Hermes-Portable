# Hermes Portable

![Hermes Portable logo](https://raw.githubusercontent.com/kimusan/Hermes-Portable/main/assets/hermes-portable-logo-orange.png)

Hermes Portable lets you carry a full Hermes Agent environment on a USB stick without dragging a fragile Python and Node runtime around with it.

It keeps your real Hermes identity and state portable, while moving the heavy, rebuildable runtime pieces onto the local machine you are using at the moment. That means you can plug into a laptop, workstation, VM, or temporary machine and get a working Hermes setup quickly, without fighting `venv`, `node_modules`, exFAT filesystem quirks, or host-global config pollution.

Current release: `v0.2.0`

Vendored upstream Hermes: `v0.16.0`

Project home: https://github.com/kimusan/Hermes-Portable

Hermes Agent website: https://hermes-agent.nousresearch.com/

## Why Hermes Portable

Upstream Hermes Agent is excellent, but a direct install is not ideal when your goal is mobility. A portable drive is a bad place for Python environments, Node dependency trees, symlinks, executable metadata, and other runtime baggage.

Hermes Portable solves that split cleanly:
- your durable Hermes state stays on the USB stick
- rebuildable runtime pieces stay in a host-local cache
- messenger sessions remain portable
- the wrapper starts Hermes with the right environment every time
- the same portable setup can be used across Linux, macOS, Windows, and WSL-style workflows

The practical result is simple: you get a Hermes setup that feels much more like an appliance than a hand-built dev environment.

## Highlights

- portable Hermes home with sessions, config, memory, skills, auth, and platform state on the USB drive
- host-local runtime caching for Python, Node, npm, dashboard assets, and the WhatsApp bridge
- automatic Python compatibility handling for modern Hermes releases that require `>=3.11,<3.14`
- wrapper-level `--resume` support so resumed sessions feel like direct Hermes usage
- portable messenger setup helpers for Telegram, Discord, Slack, Signal, and WhatsApp
- portable web dashboard support with system-browser opening and host-cached frontend assets
- temporary-machine mode that removes the local runtime cache on exit
- update commands for both the portable wrapper and the vendored Hermes source

## Quick start

Linux or macOS:

```bash
./hermes-portable
```

Windows PowerShell:

```powershell
.\bin\hermes-portable.ps1
```

Windows `cmd.exe`:

```bat
hermes-portable.bat
```

Normal launch behavior:
1. selects a Hermes-compatible host Python automatically
2. prepares or repairs the host-local runtime cache
3. prepares the portable gateway runtime
4. starts `hermes gateway run` as a child process
5. starts the Hermes CLI
6. stops the gateway child when Hermes exits

Useful first checks:

```bash
./hermes-portable --doctor
./hermes-portable -- hermes config env-path
```

The reported Hermes env path should point at this project:

```text
.../Hermes-USB-Portable2/data/.env
```

## Common workflows

### Start Hermes normally

```bash
./hermes-portable
```

This is the default portable mode: gateway child plus Hermes CLI.

### Resume an existing Hermes session

```bash
./hermes-portable --resume 20260610_170738_1de746
```

### Use it on a temporary or borrowed machine

```bash
./hermes-portable --temporary
```

This keeps your portable state on the USB stick but removes the host-local runtime cache when you are done.

### Run the dashboard

```bash
./hermes-portable --dashboard
```

Useful variants:

```bash
./hermes-portable --dashboard --dashboard-no-open
./hermes-portable --dashboard --dashboard-port 9120
./hermes-portable --dashboard --dashboard-no-gateway
./hermes-portable --dashboard-status
./hermes-portable --dashboard-stop
```

### Rebuild the portable runtime

```bash
./hermes-portable --repair --doctor
```

### Run only the gateway

```bash
./hermes-portable --gateway-only
```

### Run Hermes without starting the gateway child

```bash
./hermes-portable --no-gateway
```

## Messenger setup examples

Portable setup helpers:

```bash
./hermes-portable --setup-platform telegram
./hermes-portable --setup-platform discord
./hermes-portable --setup-platform slack
./hermes-portable --setup-platform signal
./hermes-portable --setup-platform whatsapp
./hermes-portable --setup-platform all
```

Generic platform actions:

```bash
./hermes-portable --platform-action telegram setup
./hermes-portable --platform-action discord setup
./hermes-portable --platform-action slack setup
./hermes-portable --platform-action slack manifest
./hermes-portable --platform-action signal setup
./hermes-portable --platform-action whatsapp setup
./hermes-portable --platform-action whatsapp pair
./hermes-portable --platform-action all setup
```

Notes:
- Telegram, Discord, Slack, and Signal share the portable Python gateway runtime.
- WhatsApp still uses a separate Node bridge runtime, but the session remains on the USB stick.
- `--pair-whatsapp` is kept as a compatibility alias for `--platform-action whatsapp pair`.

## Dashboard

Hermes Portable supports the upstream Hermes dashboard in a way that fits the portable model.

Dashboard behavior:
- the wrapper installs the dashboard-capable Hermes extras when needed
- web and TUI dashboard assets are built into the host-local runtime cache, not into the USB source tree
- `--dashboard` starts the portable gateway child by default
- `--dashboard-no-gateway` disables that autostart if you want dashboard-only mode
- the wrapper opens the dashboard with the system browser opener instead of relying on Python's limited browser detection
- on Linux it prefers `xdg-open`, on macOS `open`, and on Windows `cmd /c start`

Default bind:

```text
127.0.0.1:9119
```

## Update commands

Update the wrapper repo itself:

```bash
./hermes-portable --update-wrapper
```

Update the vendored Hermes source to the latest upstream release:

```bash
./hermes-portable --update-hermes
```

Update the vendored Hermes source to a specific upstream tag or branch:

```bash
./hermes-portable --update-hermes-ref v0.16.0
./hermes-portable --update-hermes-ref main
```

Update behavior:
- both update paths require a clean git worktree
- both reset the host-local runtime cache after the source update
- the next launch rebuilds against the updated code

## Security warning

This USB stick can contain API keys, messenger credentials, WhatsApp pairing data, chat/session history, memories, skills, and other personal material.

Treat it like a password vault:
- do not leave it unattended on shared machines
- do not lend it to people you do not fully trust
- keep secure backups
- use disk or container encryption if practical
- rotate credentials if the stick is lost or copied

## Technical details

### Portable state versus host cache

Hermes Portable keeps these files on the USB stick:
- `data/.env`
- `data/config.yaml`
- `data/state.db`
- `data/sessions/`
- `data/skills/`
- `data/memories/`
- `data/auth.json`
- `data/platforms/`, including the WhatsApp session directory

It keeps these rebuildable parts in a host-local cache:
- Python virtualenv
- pip cache
- Node runtime when the host does not already provide a suitable one
- npm cache
- WhatsApp bridge runtime
- dashboard build artifacts

That split avoids the usual `venv` and `node_modules` problems on exFAT/FAT removable media while keeping your Hermes identity and state portable.

### Supported Python and Hermes version

This release is updated for upstream Hermes `v0.16.0`.

Compatibility details:
- Hermes now requires Python `>=3.11,<3.14`
- the wrapper auto-detects that requirement from `src/hermes-agent/pyproject.toml`
- it prefers a compatible host interpreter such as `python3.13`, `python3.12`, or `python3.11`
- if an old cached venv was built with an incompatible Python, the wrapper rebuilds it automatically

### Platform notes

#### Telegram

1. Create a bot with `@BotFather` and copy the bot token.
2. Find your numeric Telegram user ID.
3. Run:

```bash
./hermes-portable --setup-platform telegram
```

Equivalent `.env` entries:

```env
TELEGRAM_BOT_TOKEN=<bot-token>
TELEGRAM_ALLOWED_USERS=<numeric-user-id>
```

Template: `examples/env/telegram.env`

#### Discord

1. Create a Discord bot application.
2. Enable `Server Members Intent` and `Message Content Intent`.
3. Copy the bot token and your numeric Discord user ID.
4. Run:

```bash
./hermes-portable --setup-platform discord
```

Equivalent `.env` entries:

```env
DISCORD_BOT_TOKEN=<discord-bot-token>
DISCORD_ALLOWED_USERS=<discord-user-id>
```

Template: `examples/env/discord.env`

#### Slack

1. Generate the portable Slack manifest:

```bash
./hermes-portable --platform-action slack manifest
```

2. Create/install the Slack app from that manifest.
3. Copy:
- `SLACK_BOT_TOKEN` from `OAuth & Permissions`; it must start with `xoxb-`
- `SLACK_APP_TOKEN` from `Basic Information -> App-Level Tokens`; it must start with `xapp-`
4. Set `SLACK_ALLOWED_USERS` unless you intentionally enable open access.
5. Run:

```bash
./hermes-portable --setup-platform slack
```

Equivalent `.env` entries:

```env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
SLACK_ALLOWED_USERS=U0123456789
```

Template: `examples/env/slack.env`

#### Signal

Signal support requires host-installed Java and `signal-cli`.

1. Install Java 17+ and `signal-cli` on the host.
2. Link `signal-cli` as a secondary Signal device.
3. Start the daemon:

```bash
signal-cli --account +1234567890 daemon --http 127.0.0.1:8080
```

4. Run:

```bash
./hermes-portable --setup-platform signal
```

Equivalent `.env` entries:

```env
SIGNAL_HTTP_URL=http://127.0.0.1:8080
SIGNAL_ACCOUNT=<your-e164-number>
SIGNAL_ALLOWED_USERS=<allowed-user>
```

Template: `examples/env/signal.env`

#### WhatsApp

Pair from the portable environment:

```bash
./hermes-portable --platform-action whatsapp pair
```

Compatibility alias:

```bash
./hermes-portable --pair-whatsapp
```

For Danish numbers in `WHATSAPP_ALLOWED_USERS`, use E.164 digits without `+` or `00`:

```env
WHATSAPP_ALLOWED_USERS=4512345678
```

### Maintenance and cleanup

Delete the host-local runtime cache manually:

```bash
./hermes-portable --reset-runtime
```

Equivalent explicit cleanup-on-exit flag:

```bash
./hermes-portable --cleanup-runtime-on-exit
```

This removes the host-local runtime cache on exit, including:
- portable Python venv
- downloaded Node runtime
- pip and npm caches
- dashboard build cache
- WhatsApp bridge runtime

It does not remove:
- data on the USB stick under `data/`
- host tools reused from the system `PATH`

### Startup banner and colors

```bash
# force color
HERMES_PORTABLE_COLOR=always ./hermes-portable --doctor

# disable ANSI colors
NO_COLOR=1 ./hermes-portable --doctor

# disable the ASCII logo
HERMES_PORTABLE_NO_LOGO=1 ./hermes-portable --doctor
```

The wrapper shows the `Hermes Portable` ASCII banner for normal launches, `--help`, and other wrapper-level commands.

### Notes on recent compatibility changes

- interactive sessions now run through a PTY-backed wrapper path so list navigation and direct Hermes terminal behavior are preserved more closely
- `--resume` is supported directly by the wrapper
- deprecated `TERMINAL_CWD` entries in `data/.env` are removed automatically; use `config.yaml` `terminal.cwd` instead if you still need a custom working directory
- the dashboard path includes the extra dependency needed for the Kanban plugin API to mount correctly

### Directory layout

```text
Hermes-USB-Portable2/
├── hermes-portable
├── hermes-portable.bat
├── README.md
├── PORTABLE.md
├── assets/
├── bin/
│   ├── bootstrap_portable.py
│   ├── hermes-portable.command
│   ├── hermes-portable.ps1
│   └── hermes-portable.sh
├── data/
│   ├── .env
│   ├── config.yaml
│   ├── logs/
│   ├── platforms/
│   └── state.db
├── portable/
└── src/hermes-agent/
```

The host-local cache typically lives at:

```text
~/.cache/hermes-portable/<portable-usb-id>/
```

That cache is disposable.

## More implementation detail

See `PORTABLE.md` for the wrapper layout and runtime design notes.
