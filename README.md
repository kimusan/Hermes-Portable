# Hermes Portable

![Hermes Portable logo](https://raw.githubusercontent.com/kimusan/Hermes-Portable/main/assets/hermes-portable-logo-orange.png)

Portable wrapper for Hermes Agent that keeps durable user state on the USB drive and keeps rebuildable runtimes in a host-local cache.

Current release: `v0.2.0`

Vendored upstream Hermes: `v0.16.0`

Project home: https://github.com/kimusan/Hermes-Portable

## What it does

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

## Security warning

This USB stick can contain API keys, messenger credentials, WhatsApp pairing data, chat/session history, memories, skills, and other personal material.

Treat it like a password vault:
- do not leave it unattended on shared machines
- do not lend it to people you do not fully trust
- keep secure backups
- use disk or container encryption if practical
- rotate credentials if the stick is lost or copied

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

Default behavior:
1. selects a Hermes-compatible host Python automatically
2. prepares or repairs the host-local runtime cache
3. prepares the portable gateway runtime
4. starts `hermes gateway run` as a child process
5. starts the Hermes CLI
6. stops the gateway child when Hermes exits

## First-run checks

```bash
./hermes-portable --doctor
./hermes-portable -- hermes config env-path
```

The reported Hermes env path should point at this portable project:

```text
.../Hermes-USB-Portable2/data/.env
```

## Supported Python and Hermes version

This release is updated for upstream Hermes `v0.16.0`.

Important compatibility detail:
- Hermes now requires Python `>=3.11,<3.14`
- the wrapper auto-detects that requirement from `src/hermes-agent/pyproject.toml`
- it prefers a compatible host interpreter such as `python3.13`, `python3.12`, or `python3.11`
- if an old cached venv was built with an incompatible Python, the wrapper rebuilds it automatically

## Common commands

```bash
# normal portable launch: gateway child + Hermes CLI
./hermes-portable

# resume a Hermes session by ID
./hermes-portable --resume 20260610_170738_1de746

# run doctor checks
./hermes-portable --doctor

# rebuild portable runtime pieces and then run doctor
./hermes-portable --repair --doctor

# run only the gateway under the wrapper
./hermes-portable --gateway-only

# run Hermes without starting the gateway child
./hermes-portable --no-gateway

# delete the host-local runtime cache; it will be rebuilt next run
./hermes-portable --reset-runtime

# temporary-machine mode: remove host-local runtime cache on exit
./hermes-portable --temporary

# pass commands through to Hermes directly
./hermes-portable -- hermes status --all
./hermes-portable -- hermes config env-path
```

## Gateway setup

Portable platform setup helpers:

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

Hermes Portable now supports the upstream Hermes dashboard.

Wrapper commands:

```bash
./hermes-portable --dashboard
./hermes-portable --dashboard --dashboard-no-open
./hermes-portable --dashboard --dashboard-port 9120
./hermes-portable --dashboard --dashboard-no-gateway
./hermes-portable --dashboard-status
./hermes-portable --dashboard-stop
```

Dashboard behavior:
- the wrapper installs the dashboard-capable Hermes extras when needed
- web and TUI dashboard assets are built into the host-local runtime cache, not into the USB source tree
- `--dashboard` starts the portable gateway child by default
- `--dashboard-no-gateway` disables that autostart if you want dashboard-only mode
- the wrapper opens the dashboard with the system browser opener instead of relying on Python's limited browser detection
- on Linux it prefers `xdg-open`, on macOS `open`, and on Windows `cmd /c start`

The dashboard binds to `127.0.0.1:9119` by default.

## Platform notes

### Telegram

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

### Discord

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

### Slack

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

### Signal

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

### WhatsApp

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

## Temporary-machine mode

If you want to use Hermes Portable on a borrowed or temporary machine and remove locally installed runtime files afterward:

```bash
./hermes-portable --temporary
```

Equivalent explicit flag:

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

## Startup banner and colors

```bash
# force color
HERMES_PORTABLE_COLOR=always ./hermes-portable --doctor

# disable ANSI colors
NO_COLOR=1 ./hermes-portable --doctor

# disable the ASCII logo
HERMES_PORTABLE_NO_LOGO=1 ./hermes-portable --doctor
```

The wrapper now shows the `Hermes Portable` ASCII banner for normal launches, `--help`, and other wrapper-level commands.

## Notes on recent compatibility changes

Recent wrapper changes worth knowing about:
- interactive sessions now run through a PTY-backed wrapper path so list navigation and direct Hermes terminal behavior are preserved more closely
- `--resume` is supported directly by the wrapper
- deprecated `TERMINAL_CWD` entries in `data/.env` are removed automatically; use `config.yaml` `terminal.cwd` instead if you still need a custom working directory
- the dashboard path now includes the extra dependency needed for the Kanban plugin API to mount correctly

## Directory layout

```text
Hermes-USB-Portable2/
├── hermes-portable
├── hermes-portable.bat
├── README.md
├── PORTABLE.md
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
