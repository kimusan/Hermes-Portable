# Hermes Portable v0.1.0

This is an alternative portable layout for Hermes that keeps durable state on this USB stick but keeps rebuildable runtimes on each host machine.

State on USB:
- data/.env
- data/config.yaml
- data/state.db and sessions
- data/skills, memories, auth, plugins, cron
- data/platforms/ with platform-specific portable state, including data/platforms/whatsapp/session

Host-local cache:
- Python venv
- pip cache
- Python messaging SDKs for Telegram, Discord, and Slack
- Node runtime if the host does not have Node 18+
- npm cache
- WhatsApp bridge node_modules

Linux/macOS:

    ./hermes-portable

Windows PowerShell:

    .\bin\hermes-portable.ps1

Windows cmd:

    hermes-portable.bat

Useful commands:

    ./hermes-portable --doctor
    ./hermes-portable --repair --doctor
    ./hermes-portable --setup-platform telegram
    ./hermes-portable --setup-platform discord
    ./hermes-portable --setup-platform slack
    ./hermes-portable --setup-platform signal
    ./hermes-portable --pair-whatsapp
    ./hermes-portable --no-gateway
    ./hermes-portable --gateway-only
    ./hermes-portable --reset-runtime
    ./hermes-portable -- hermes config env-path

Gateway behavior:
- The gateway is never installed as a system service by this launcher.
- When launched without Hermes arguments, it starts `hermes gateway run` as a child process, then starts the Hermes CLI.
- When the CLI exits, the launcher terminates the gateway child process.
- If you pass explicit Hermes arguments, the launcher runs that command and does not autostart the gateway unless you use --gateway-only.
- Use `--setup-platform telegram|discord|slack|signal|whatsapp|all` to run the upstream gateway setup wizard with portable `HERMES_HOME` and platform-specific setup notes.

Messaging behavior:
- Telegram, Discord, and Slack use upstream Hermes Python adapters and SDKs installed in the host-local venv through the `messaging` extra.
- Signal uses upstream Hermes plus an external host `signal-cli` daemon; Java and signal-cli are not bundled on the USB stick.
- WhatsApp remains the only Node bridge runtime prepared by this launcher.

WhatsApp behavior:
- The WhatsApp session stays on USB at data/platforms/whatsapp/session.
- The WhatsApp bridge runtime is copied to the host cache and npm install runs there, avoiding exFAT symlink/node_modules problems.
- The portable launcher exports HERMES_PORTABLE_WHATSAPP_BRIDGE_DIR and HERMES_PORTABLE_WHATSAPP_SESSION so the patched Hermes copy uses those paths.
