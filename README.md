# Hermes Portable

```text
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║   ██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗              ║
║   ██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝              ║
║   ███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗              ║
║   ██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║              ║
║   ██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║              ║
║   ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝              ║
║                                                                      ║
║        ☤  HERMES PORTABLE  ☤   winged messenger on a stick          ║
║                                                                      ║
║              ┌───────────────┐                                       ║
║          ╭───┤  /dev/hermes  ├───╮                                   ║
║          │   └──────┬────────┘   │                                   ║
║          │      ╭───┴───╮        │                                   ║
║          ╰──────┤  ☤☤☤  ├────────╯                                   ║
║                 ╰───┬───╯                                            ║
║            USB data │ host runtime                                   ║
║                  portable state, local speed                         ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
```

A portable, USB-first Hermes Agent layout by Kim Schulz <kim@schulz.dk>.

GitHub project: https://github.com/kimusan/Hermes-Portable

Current release: v0.1.0

This project packages Nous Research's Hermes Agent so it can travel on a USB stick while keeping the heavy, rebuildable runtimes on the host machine. The goal is simple: keep your Hermes identity, config, sessions, skills, memory, and WhatsApp pairing portable, but avoid the filesystem pain that happens when Python virtualenvs and Node `node_modules` live directly on exFAT/FAT removable media.

## Security warning

Hermes Portable stores your personal Hermes state on the USB stick. That can include AI provider API keys, gateway credentials, WhatsApp pairing/session data, chat/session history, memories, skills, config files, and other personal information.

Treat the USB stick like a password manager or hardware key:

- do not lend it to people you do not fully trust,
- do not leave it plugged into shared or unattended computers,
- keep backups in a secure place,
- consider using full-disk or container encryption for the USB drive,
- revoke/rotate AI API keys and re-pair WhatsApp if the stick is lost, copied, or handled by someone else.

If the USB stick gets into the wrong hands, assume the data and credentials stored on it may be exposed.

## What this is

Hermes Portable is a practical portable wrapper around upstream Hermes Agent.

It keeps durable state on the USB drive:

- `data/.env`
- `data/config.yaml`
- `data/state.db`
- `data/sessions/`
- `data/skills/`
- `data/memories/`
- `data/auth.json`
- `data/platforms/whatsapp/session/`

It keeps rebuildable runtime pieces in a host-local cache:

- Python virtualenv
- pip cache
- Node runtime, when needed
- npm cache
- WhatsApp bridge runtime and `node_modules`

That split makes the install much more reliable on USB sticks and external disks, especially when the drive is formatted as exFAT.

## Credits and inspiration

Project / portable layout:

- Kim Schulz <kim@schulz.dk>
- Hermes Portable: https://github.com/kimusan/Hermes-Portable

Built around:

- Hermes Agent by Nous Research: https://github.com/NousResearch/hermes-agent
- Hermes Agent docs: https://hermes-agent.nousresearch.com/docs/

Inspired by the earlier Hermes USB Portable project/layout. The old project documents are not vendored here; see the original GitHub project instead:

- https://github.com/techjarves/Hermes-USB-Portable

The upstream Hermes source README is here:

- `src/hermes-agent/README.md`

Portable layout notes are here:

- `PORTABLE.md`

## Quick start

From this folder:

```bash
./hermes-portable
```

That will:

1. prepare/check the host-local runtime cache,
2. prepare the WhatsApp bridge runtime outside the USB filesystem,
3. start `hermes gateway run` as a child process,
4. start the Hermes CLI,
5. stop the gateway child when the CLI exits.

## First-run setup

Run the doctor first:

```bash
./hermes-portable --doctor
```

Then configure Hermes:

```bash
./hermes-portable -- hermes setup
```

Check which `.env` file Hermes is using:

```bash
./hermes-portable -- hermes config env-path
```

It should point inside this project:

```text
.../Hermes-USB-Portable2/data/.env
```

## WhatsApp setup

Pair WhatsApp from the same portable environment:

```bash
./hermes-portable --pair-whatsapp
```

Then scan the QR code from WhatsApp:

```text
WhatsApp -> Settings -> Linked Devices -> Link a Device
```

For Danish phone numbers in `WHATSAPP_ALLOWED_USERS`, use E.164 digits without `+` and without `00`:

```env
WHATSAPP_ALLOWED_USERS=45xxxxxxxx
```

For example, do this:

```env
WHATSAPP_ALLOWED_USERS=4512345678
```

Do not use:

```env
WHATSAPP_ALLOWED_USERS=004512345678
WHATSAPP_ALLOWED_USERS=+4512345678
WHATSAPP_ALLOWED_USERS=12345678
```

## Common commands

```bash
# Normal portable launch: gateway child + Hermes CLI
./hermes-portable

# Diagnose paths, runtime, Node, npm, WhatsApp session
./hermes-portable --doctor

# Rebuild the host-local Python/Node/WhatsApp runtime where needed
./hermes-portable --repair --doctor

# Pair WhatsApp interactively
./hermes-portable --pair-whatsapp

# Run Hermes without starting the gateway child
./hermes-portable --no-gateway

# Run only the gateway under the portable launcher
./hermes-portable --gateway-only

# Delete the host-local runtime cache; it will be rebuilt next run
./hermes-portable --reset-runtime

# Pass a command through to Hermes
./hermes-portable -- hermes status --all
./hermes-portable -- hermes config path
./hermes-portable -- hermes config env-path
```

## Directory map

```text
Hermes-USB-Portable2/
├── hermes-portable              # POSIX launcher
├── hermes-portable.bat          # Windows cmd launcher
├── README.md                    # this file
├── PORTABLE.md                  # implementation notes for this layout
├── bin/
│   ├── bootstrap_portable.py    # portable runtime/bootstrap brain
│   ├── hermes-portable.sh       # Linux/macOS shell launcher
│   ├── hermes-portable.command  # macOS double-click helper
│   └── hermes-portable.ps1      # PowerShell launcher
├── data/                        # portable Hermes state; back this up
│   ├── .env                     # secrets and platform flags
│   ├── config.yaml              # Hermes config
│   ├── state.db                 # session database
│   ├── logs/                    # agent/gateway logs
│   └── platforms/whatsapp/      # WhatsApp bridge logs + session
├── portable/                    # generated runtime metadata, ignored by git
└── src/hermes-agent/            # upstream Hermes source checkout
```

Host-local runtime cache on this machine currently uses a path like:

```text
~/.cache/hermes-portable/<portable-usb-id>/
```

That cache is disposable. If it breaks, remove it with:

```bash
./hermes-portable --reset-runtime
```

Then start again.

## Why not put everything on the USB stick?

Because many removable drives are formatted as exFAT/FAT/NTFS. Those filesystems often lack the Unix filesystem features expected by development runtimes:

- symlinks,
- executable bits,
- reliable permissions,
- sockets,
- ownership metadata,
- npm-style `node_modules/.bin` links.

The WhatsApp bridge is Node-based and depends on packages that may create links or expect Unix-like metadata. Keeping the bridge runtime in a host-local cache avoids those errors while preserving the WhatsApp session on the USB stick.

## Troubleshooting

### Gateway starts but WhatsApp messages are ignored

Check the logs:

```bash
./hermes-portable --gateway-only
```

or inspect:

```text
data/logs/gateway.log
data/platforms/whatsapp/bridge.log
```

Useful things to look for:

```text
Unauthorized user
self_chat_mode_rejects_non_self
allowlist_mismatch
WhatsApp connected
```

For self-chat mode, make sure:

```env
WHATSAPP_ENABLED=true
WHATSAPP_MODE=self-chat
WHATSAPP_ALLOWED_USERS=45xxxxxxxx
```

Then restart the portable launcher.

### Runtime is confused or stale

```bash
./hermes-portable --reset-runtime
./hermes-portable --repair --doctor
```

### Need a clean state

Move or remove `data/` if you want to start completely fresh. Keep a backup first if it contains API keys, sessions, skills, or WhatsApp pairing data.

## Relationship to upstream Hermes

This repository/folder is a portable wrapper and state layout. The actual Hermes Agent source lives under:

```text
src/hermes-agent/
```

Most Hermes commands still work normally when passed through the launcher:

```bash
./hermes-portable -- hermes doctor
./hermes-portable -- hermes model
./hermes-portable -- hermes tools list
./hermes-portable -- hermes gateway run
```

Prefer using `./hermes-portable -- ...` instead of a globally installed `hermes` command, because the launcher pins the correct `HERMES_HOME`, runtime cache, WhatsApp session path, and PATH.

## License

This portable wrapper/layout is created byKim Schulz <kim@schulz.dk> and released under the MIT License. See `LICENSE` in this repository.

Hermes Agent itself is developed by Nous Research and is licensed under its upstream license. See:

- `src/hermes-agent/LICENSE`
- https://github.com/NousResearch/hermes-agent
