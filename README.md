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
- platform sessions and credentials under `data/platforms/`, including `data/platforms/whatsapp/session/`

It keeps rebuildable runtime pieces in a host-local cache:

- Python virtualenv
- pip cache
- Python messaging SDKs for Telegram, Discord, and Slack
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
2. install Hermes with the mainstream messaging gateway SDKs,
3. prepare the WhatsApp bridge runtime outside the USB filesystem,
4. start `hermes gateway run` as a child process,
5. start the Hermes CLI,
6. stop the gateway child when the CLI exits.

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

## Gateway platform setup

Hermes Portable can run several gateway adapters from the same USB state directory. Use the portable setup helper so the wizard reads and writes `data/.env` and `data/config.yaml`, not a global `~/.hermes` install:

```bash
./hermes-portable --setup-platform telegram
./hermes-portable --setup-platform discord
./hermes-portable --setup-platform slack
./hermes-portable --setup-platform signal
./hermes-portable --setup-platform whatsapp
./hermes-portable --setup-platform all
```

The helper prints platform-specific prerequisites and then starts upstream `hermes gateway setup`. The gateway setup wizard may offer to install a system service; for portable use, prefer this launcher's child-process modes instead:

```bash
./hermes-portable              # gateway child + CLI
./hermes-portable --gateway-only
```

Platform notes:

- Telegram, Discord, and Slack use Python gateway SDKs installed into the host-local portable virtualenv.
- WhatsApp uses the Node bridge runtime in the host-local cache while keeping its pairing session on the USB stick.
- Signal uses the upstream Hermes Signal adapter, but `signal-cli` and Java are external host prerequisites; the USB stick stores only Hermes config/state.

## Telegram setup

Telegram is the easiest non-WhatsApp bridge to add because it only needs a bot token and your numeric Telegram user ID.

1. In Telegram, message `@BotFather`, run `/newbot`, and copy the bot token.
2. Find your numeric user ID with `@userinfobot` or `@get_id_bot`. Use the number, not your `@username`.
3. Run the portable setup helper:

   ```bash
   ./hermes-portable --setup-platform telegram
   ```

4. When the wizard asks for credentials, store them in the portable Hermes environment. The equivalent manual entries in `data/.env` look like this:

   ```env
   TELEGRAM_BOT_TOKEN=<bot-token-from-botfather>
   TELEGRAM_ALLOWED_USERS=<numeric-telegram-user-id>
   ```

   A template is available at `examples/env/telegram.env`.

5. Start the gateway and send a message to your bot:

   ```bash
   ./hermes-portable --gateway-only
   ```

For group chats, disable BotFather privacy mode or promote the bot to admin if you want it to see ordinary messages. Keep `TELEGRAM_ALLOWED_USERS` tight; do not enable open access on a bot that can run tools.

## Discord setup

Discord is useful for DMs, private servers, and shared team channels. The most important setup step is enabling Discord's privileged intents.

1. Go to the Discord Developer Portal and create an application with a bot user.
2. In the bot settings, enable both **Server Members Intent** and **Message Content Intent**. Without Message Content Intent the bot can appear online but receive empty messages.
3. Reset/copy the bot token, then invite the bot to your server with at least View Channels, Send Messages, Read Message History, Attach Files, and Embed Links permissions.
4. Enable Developer Mode in Discord and copy your numeric Discord User ID.
5. Run the portable setup helper:

   ```bash
   ./hermes-portable --setup-platform discord
   ```

6. The equivalent manual entries in `data/.env` look like this:

   ```env
   DISCORD_BOT_TOKEN=<discord-bot-token>
   DISCORD_ALLOWED_USERS=<discord-user-id>
   ```

   A template is available at `examples/env/discord.env`.

7. Start the gateway and test a DM or mention the bot in a server channel:

   ```bash
   ./hermes-portable --gateway-only
   ```

By default Hermes responds to every DM, but in server channels it expects an `@mention` unless you configure free-response channels.

## Slack setup

Slack uses Socket Mode, so Hermes Portable does not need a public webhook URL. You need two different Slack tokens, and they come from different places:

- `SLACK_BOT_TOKEN`: the Bot User OAuth Token. It starts with `xoxb-`.
- `SLACK_APP_TOKEN`: the app-level Socket Mode token. It starts with `xapp-`.

Do not use the Slack Verification Token or Signing Secret as `SLACK_BOT_TOKEN`; those are different values and Slack will return `invalid_auth`.

1. Generate the upstream Hermes Slack app manifest from the portable environment:

   ```bash
   ./hermes-portable -- hermes slack manifest --write
   ```

   The file is written under the portable Hermes home, not your global home directory.

2. In Slack, go to `api.slack.com/apps`, create an app from an app manifest, paste the generated manifest, and install it to your workspace.
3. Copy the bot token:
   - Open your app in `api.slack.com/apps`.
   - Go to `OAuth & Permissions`.
   - Copy `Bot User OAuth Token`.
   - It must start with `xoxb-`.
4. Copy the app-level Socket Mode token:
   - Go to `Basic Information` -> `App-Level Tokens`.
   - Create/copy a token with `connections:write`.
   - It must start with `xapp-`.
5. Find your Slack Member ID from your profile menu (`View full profile` -> more menu -> `Copy member ID`). It usually starts with `U` or `W`.
6. Run the portable setup helper:

   ```bash
   ./hermes-portable --setup-platform slack
   ```

7. The equivalent manual entries in `data/.env` look like this:

   ```env
   SLACK_BOT_TOKEN=xoxb-...
   SLACK_APP_TOKEN=xapp-...
   SLACK_ALLOWED_USERS=U0123456789
   ```

   `SLACK_ALLOWED_USERS` is required for normal private access. If it is empty, Hermes will deny Slack users even though the Slack app is connected. Only skip it if you intentionally set `SLACK_ALLOW_ALL_USERS=true` or `GATEWAY_ALLOW_ALL_USERS=true`.

   A template is available at `examples/env/slack.env`.

8. Check the portable configuration:

   ```bash
   ./hermes-portable --doctor
   ```

   The Slack checks should show a valid `xoxb-` bot token, a valid `xapp-` app token, and configured allowed users/open access.

9. Start the gateway, invite the bot to any channel where it should respond, and test a DM or app mention:

   ```bash
   ./hermes-portable --gateway-only
   ```

If Slack works in DMs but not channels, check that the app has `message.channels` / `message.groups` event subscriptions and that the bot has been invited to the channel.

## Signal setup

Signal support uses the upstream Hermes Signal adapter plus a host-installed `signal-cli` daemon. Hermes Portable stores the Hermes config on the USB stick, but it does not bundle Java or signal-cli.

1. Install Java 17+ and `signal-cli` on the host machine.
2. Link signal-cli as a secondary device:

   ```bash
   signal-cli link -n "HermesPortable"
   ```

   Then open Signal on your phone and use `Settings -> Linked Devices -> Link New Device`.

3. Start the Signal HTTP daemon on the host, replacing the account with your E.164 phone number:

   ```bash
   signal-cli --account +1234567890 daemon --http 127.0.0.1:8080
   ```

4. Run the portable setup helper:

   ```bash
   ./hermes-portable --setup-platform signal
   ```

5. The equivalent manual entries in `data/.env` look like this:

   ```env
   SIGNAL_HTTP_URL=http://127.0.0.1:8080
   SIGNAL_ACCOUNT=<your-e164-signal-number>
   SIGNAL_ALLOWED_USERS=<allowed-e164-number-or-signal-uuid>
   ```

   A template is available at `examples/env/signal.env`.

6. Check that the portable launcher can see signal-cli and the daemon:

   ```bash
   ./hermes-portable --doctor
   ```

7. Start the gateway and test Signal. For a single-number setup, send a message to Signal's "Note to Self" conversation from your phone:

   ```bash
   ./hermes-portable --gateway-only
   ```

If `--doctor` says the Signal daemon is not reachable, start the `signal-cli ... daemon --http ...` command first and make sure `SIGNAL_HTTP_URL` points to the same host/port.

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

# Configure a messenger platform with portable HERMES_HOME
./hermes-portable --setup-platform telegram
./hermes-portable --setup-platform discord
./hermes-portable --setup-platform slack
./hermes-portable --setup-platform signal

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

## Startup styling

Hermes Portable shows a compact ANSI/ASCII startup banner inspired by the upstream Hermes CLI. It follows normal terminal color conventions:

```bash
# Force color even when stdout is redirected
HERMES_PORTABLE_COLOR=always ./hermes-portable --doctor

# Disable ANSI colors but keep the text logo
NO_COLOR=1 ./hermes-portable --doctor

# Disable the logo entirely for very plain logs/scripts
HERMES_PORTABLE_NO_LOGO=1 ./hermes-portable --doctor
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
│   └── platforms/               # portable messenger state, such as WhatsApp sessions
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
