#!/usr/bin/env python3
"""Hermes USB portable launcher/bootstrapper.

Design goals:
- keep durable Hermes state on the USB drive (data/)
- keep rebuildable runtimes on the host cache (venv, node, node_modules, npm cache)
- optionally run the gateway only as a child of the portable launcher
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "hermes-agent"
DATA = ROOT / "data"
PORTABLE = ROOT / "portable"
MANIFEST = PORTABLE / "manifest.json"
STATE = PORTABLE / "runtime-state.json"

NODE_VERSION = "20.19.5"
MIN_NODE_MAJOR = 18
MIN_PYTHON = (3, 11)
RELEASE_VERSION = "0.1.0"
SETUP_PLATFORMS = ("telegram", "discord", "slack", "signal", "whatsapp", "all")
PLATFORM_ACTIONS = {
    "telegram": {"setup"},
    "discord": {"setup"},
    "slack": {"setup", "manifest"},
    "signal": {"setup"},
    "whatsapp": {"setup", "pair"},
    "all": {"setup"},
}
SHARED_GATEWAY_PLATFORMS = tuple(p for p in SETUP_PLATFORMS if p not in {"whatsapp", "all"})

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GOLD = "\033[38;2;255;215;0m"
AMBER = "\033[38;2;255;191;0m"
BRONZE = "\033[38;2;205;127;50m"
CREAM = "\033[38;2;255;248;220m"
MUTED = "\033[38;2;184;134;11m"
GREEN = "\033[38;2;80;220;130m"
BLUE = "\033[38;2;100;180;255m"
RED = "\033[38;2;255;100;100m"

HERMES_PORTABLE_LOGO = """██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗  ██████╗  ██████╗ ██████╗ ████████╗ █████╗ ██████╗ ██╗     ███████╗
██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝  ██╔══██╗██╔═══██╗██╔══██╗╚══██╔══╝██╔══██╗██╔══██╗██║     ██╔════╝
███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗  ██████╔╝██║   ██║██████╔╝   ██║   ███████║██████╔╝██║     █████╗
██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║  ██╔═══╝ ██║   ██║██╔══██╗   ██║   ██╔══██║██╔══██╗██║     ██╔══╝
██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║  ██║     ╚██████╔╝██║  ██║   ██║   ██║  ██║██████╔╝███████╗███████╗
╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝  ╚═╝      ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝"""


def wants_color() -> bool:
    setting = os.environ.get("HERMES_PORTABLE_COLOR", "").strip().lower()
    if setting in {"always", "1", "true", "yes", "on"}:
        return True
    if setting in {"never", "0", "false", "no", "off"}:
        return False
    if os.environ.get("NO_COLOR") or os.environ.get("HERMES_PORTABLE_NO_COLOR"):
        return False
    term = os.environ.get("TERM", "")
    return sys.stdout.isatty() and term.lower() != "dumb"


def style(text: object, color: str = "", *, bold: bool = False, dim: bool = False) -> str:
    value = str(text)
    if not wants_color():
        return value
    prefix = ""
    if bold:
        prefix += BOLD
    if dim:
        prefix += DIM
    prefix += color
    return f"{prefix}{value}{RESET}" if prefix else value


def icon(ok: bool) -> str:
    return style("✓", GREEN, bold=True) if ok else style("✗", RED, bold=True)


def info(message: str):
    print(f"{style('→', BLUE, bold=True)} {message}")


def success(message: str):
    print(f"{style('✓', GREEN, bold=True)} {message}")


def warn(message: str):
    print(f"{style('!', AMBER, bold=True)} {message}")


def key_value(label: str, value: object):
    print(f"  {style((label + ':').ljust(22), AMBER, bold=True)} {value}")


def check_value(label: str, ok: bool, detail: object = ""):
    suffix = f"  {detail}" if detail else ""
    print(f"  {style((label + ':').ljust(36), MUTED)} {icon(ok)} {ok}{suffix}")


def _real_home() -> Path:
    """Return the OS account home, ignoring portable launchers that override HOME."""
    if platform.system().lower() == "windows":
        return Path.home()
    try:
        import pwd
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except Exception:
        return Path.home()


def host_cache_base() -> Path:
    system = platform.system().lower()
    real_home = _real_home()
    if system == "windows":
        return Path(os.environ.get("LOCALAPPDATA", real_home / "AppData" / "Local")) / "HermesPortable"
    if system == "darwin":
        return real_home / "Library" / "Caches" / "HermesPortable"
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg and not str(xdg).startswith(str(ROOT)):
        return Path(xdg) / "hermes-portable"
    return real_home / ".cache" / "hermes-portable"


def stable_usb_id() -> str:
    PORTABLE.mkdir(parents=True, exist_ok=True)
    if MANIFEST.exists():
        try:
            data = json.loads(MANIFEST.read_text(encoding="utf-8"))
            if data.get("usb_id"):
                return str(data["usb_id"])
        except Exception:
            pass
    seed = f"{ROOT.resolve()}|{SRC.exists()}|hermes-portable-v2".encode("utf-8", "ignore")
    usb_id = hashlib.sha256(seed).hexdigest()[:16]
    data = {
        "portable_version": 1,
        "release_version": RELEASE_VERSION,
        "usb_id": usb_id,
        "hermes_home": "data",
        "source_dir": "src/hermes-agent",
        "gateway_autostart": True,
        "runtime_policy": "host-cache",
        "whatsapp_bridge": {
            "session_dir": "data/platforms/whatsapp/session",
            "runtime_dir": "whatsapp-bridge"
        }
    }
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return usb_id


USB_ID = stable_usb_id()
RUNTIME = host_cache_base() / USB_ID
VENV = RUNTIME / "venv"
NODE_HOME = RUNTIME / "node"
WHATSAPP_RUNTIME = RUNTIME / "whatsapp-bridge"
TMP = RUNTIME / "tmp"


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def exe(name: str) -> str:
    return name + (".exe" if is_windows() else "")


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if is_windows() else "bin/python")


def venv_bin(name: str) -> Path:
    return VENV / (f"Scripts/{name}.exe" if is_windows() else f"bin/{name}")


def run(cmd, *, cwd=None, env=None, check=True, quiet=False, timeout=None):
    if not quiet:
        info(" ".join(map(str, cmd)))
    kwargs = {}
    if quiet:
        kwargs.update({"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL})
    return subprocess.run(cmd, cwd=cwd, env=env, check=check, text=True, timeout=timeout, **kwargs)


def capture(cmd, *, env=None, cwd=None):
    return subprocess.run(cmd, env=env, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _filtered_inherited_path(env: dict[str, str]) -> str:
    """Drop paths from other Hermes portable sticks from inherited PATH."""
    parts = []
    root_s = str(ROOT)
    for part in env.get("PATH", "").split(os.pathsep):
        if not part:
            continue
        # Avoid accidentally depending on a different portable install that was
        # used to launch this session. Host system paths are fine; other USB
        # Hermes runtime paths are not.
        if "Hermes-USB-Portable" in part and not part.startswith(root_s):
            continue
        parts.append(part)
    return os.pathsep.join(parts)


def _read_env_file() -> dict[str, str]:
    """Read simple KEY=VALUE entries from the portable data/.env file."""
    env_path = DATA / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def portable_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(_read_env_file())
    env.update({
        "HERMES_PORTABLE": "1",
        "HERMES_PORTABLE_ROOT": str(ROOT),
        "HERMES_HOME": str(DATA),
        "HERMES_RUNTIME_CACHE": str(RUNTIME),
        "HERMES_PORTABLE_WHATSAPP_BRIDGE_DIR": str(WHATSAPP_RUNTIME),
        "HERMES_PORTABLE_WHATSAPP_SESSION": str(DATA / "platforms" / "whatsapp" / "session"),
        "TERMINAL_CWD": str(SRC),
        "PIP_CACHE_DIR": str(RUNTIME / "pip-cache"),
        "NPM_CONFIG_CACHE": str(RUNTIME / "npm-cache"),
        "NPM_CONFIG_INSTALL_LINKS": "true",
        "WHATSAPP_NPM_INSTALL_TIMEOUT": env.get("WHATSAPP_NPM_INSTALL_TIMEOUT", "600"),
        "PYTHONNOUSERSITE": "1",
    })
    path_parts = []
    if venv_python().exists():
        path_parts.append(str(venv_python().parent))
    if NODE_HOME.exists():
        path_parts.append(str(NODE_HOME if is_windows() else NODE_HOME / "bin"))
    path_parts.append(_filtered_inherited_path(env))
    env["PATH"] = os.pathsep.join([p for p in path_parts if p])
    if not is_windows():
        # Keep HOME stable but on the host cache so tools with Unix metadata expectations work.
        env["HOME"] = str(RUNTIME / "home")
    env["TMPDIR"] = str(TMP)
    return env


def print_header():
    if os.environ.get("HERMES_PORTABLE_NO_LOGO"):
        print(style(f"Hermes Portable v{RELEASE_VERSION}", GOLD, bold=True))
    else:
        columns = shutil.get_terminal_size((88, 24)).columns
        print()
        logo_width = max(len(line) for line in HERMES_PORTABLE_LOGO.splitlines())
        if columns >= logo_width:
            logo_lines = HERMES_PORTABLE_LOGO.splitlines()
            palette = [GOLD, GOLD, AMBER, AMBER, BRONZE, BRONZE]
            for line, color in zip(logo_lines, palette):
                print(style(line, color, bold=True))
            subtitle = f"⚕ Portable USB runtime · Hermes Agent v{RELEASE_VERSION}"
            print(style(subtitle, CREAM, bold=True))
            print(style("─" * min(len(logo_lines[0]), columns), MUTED))
        else:
            title = f" ⚕ Hermes Portable v{RELEASE_VERSION} "
            width = min(max(len(title) + 4, 34), columns)
            inner = width - 2
            print(style("╔" + "═" * inner + "╗", GOLD, bold=True))
            print(style("║", GOLD, bold=True) + style(title.center(inner), CREAM, bold=True) + style("║", GOLD, bold=True))
            print(style("╚" + "═" * inner + "╝", GOLD, bold=True))
    key_value("root", ROOT)
    key_value("HERMES_HOME", DATA)
    key_value("env file", DATA / '.env')
    key_value("runtime cache", RUNTIME)
    key_value("usb id", style(USB_ID, MUTED))


def ensure_dirs():
    for p in [DATA, PORTABLE, RUNTIME, TMP, RUNTIME / "home", RUNTIME / "pip-cache", RUNTIME / "npm-cache", DATA / "logs", DATA / "platforms" / "whatsapp" / "session"]:
        p.mkdir(parents=True, exist_ok=True)


def ensure_python_compatible():
    if sys.version_info < MIN_PYTHON:
        raise SystemExit(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required to bootstrap Hermes; current is {platform.python_version()}.")


def ensure_venv(force=False):
    ensure_python_compatible()
    py = venv_python()
    if force and VENV.exists():
        shutil.rmtree(VENV, ignore_errors=True)
    if not py.exists():
        info("Creating host-local Python venv")
        run([sys.executable, "-m", "venv", str(VENV)])
    # Make sure pip exists. Do not run ensurepip on every launch; some
    # Python builds are noisy even when everything is already present.
    pip_check = capture([str(py), "-m", "pip", "--version"])
    if pip_check.returncode != 0:
        run([str(py), "-m", "ensurepip", "--upgrade"], check=False, quiet=True)
    marker = RUNTIME / "hermes-install.marker"
    source_marker = hashlib.sha256(str(SRC.resolve()).encode()).hexdigest()[:16]
    installed_marker = marker.read_text(encoding="utf-8") if marker.exists() else ""
    if force or not venv_bin("hermes").exists() or installed_marker != source_marker:
        info("Installing Hermes into host-local venv from USB source")
        run([str(py), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"], env=portable_env())
        # Install Hermes plus the mainstream gateway SDKs. Signal does not
        # need an extra Python package, but its adapter is included in Hermes
        # and talks to an external signal-cli HTTP daemon when configured.
        run([str(py), "-m", "pip", "install", "-e", f"{SRC}[messaging]"], env=portable_env())
        marker.write_text(source_marker, encoding="utf-8")


def node_bin() -> Path:
    return NODE_HOME / ("node.exe" if is_windows() else "bin/node")


def npm_bin() -> Path:
    if is_windows():
        return NODE_HOME / "npm.cmd"
    return NODE_HOME / "bin/npm"


def node_major(path: Path | str) -> int | None:
    try:
        cp = capture([str(path), "--version"])
        if cp.returncode == 0:
            return int(cp.stdout.strip().lstrip("v").split(".")[0])
    except Exception:
        return None
    return None


def system_node_ok() -> str | None:
    env = os.environ.copy()
    env["PATH"] = _filtered_inherited_path(env)
    candidate = shutil.which("node", path=env["PATH"])
    if candidate and (node_major(candidate) or 0) >= MIN_NODE_MAJOR:
        npm = shutil.which("npm", path=env["PATH"])
        if npm:
            return candidate
    return None


def node_archive_info():
    sysname = platform.system().lower()
    machine = platform.machine().lower()
    arch = "x64" if machine in {"x86_64", "amd64"} else "arm64" if machine in {"arm64", "aarch64"} else None
    if arch is None:
        raise SystemExit(f"Unsupported CPU architecture for automatic Node download: {machine}")
    if sysname == "linux":
        return f"node-v{NODE_VERSION}-linux-{arch}.tar.xz", f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-{arch}.tar.xz"
    if sysname == "darwin":
        return f"node-v{NODE_VERSION}-darwin-{arch}.tar.gz", f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-darwin-{arch}.tar.gz"
    if sysname == "windows":
        return f"node-v{NODE_VERSION}-win-{arch}.zip", f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-{arch}.zip"
    raise SystemExit(f"Unsupported OS for automatic Node download: {platform.system()}")


def ensure_node(force=False):
    if not force and node_bin().exists() and (node_major(node_bin()) or 0) >= MIN_NODE_MAJOR and npm_bin().exists():
        return
    if not force and system_node_ok():
        success("Using host Node/npm from PATH")
        return
    info(f"Downloading host-local Node.js v{NODE_VERSION}")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    archive_name, url = node_archive_info()
    archive = RUNTIME / archive_name
    if force and NODE_HOME.exists():
        shutil.rmtree(NODE_HOME, ignore_errors=True)
    if not archive.exists():
        urllib.request.urlretrieve(url, archive)
    tmp_extract = RUNTIME / "node-extract"
    shutil.rmtree(tmp_extract, ignore_errors=True)
    tmp_extract.mkdir(parents=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmp_extract)
    else:
        with tarfile.open(archive) as t:
            t.extractall(tmp_extract)
    children = [p for p in tmp_extract.iterdir() if p.is_dir()]
    if not children:
        raise SystemExit("Node archive extraction produced no directory")
    if NODE_HOME.exists():
        shutil.rmtree(NODE_HOME, ignore_errors=True)
    shutil.move(str(children[0]), str(NODE_HOME))
    shutil.rmtree(tmp_extract, ignore_errors=True)


def bridge_hash(src_bridge: Path) -> str:
    h = hashlib.sha256()
    for name in ["package.json", "package-lock.json", "bridge.js"]:
        p = src_bridge / name
        if p.exists():
            h.update(name.encode())
            h.update(p.read_bytes())
    node = capture([str(node_bin() if node_bin().exists() else shutil.which("node") or "node"), "--version"], env=portable_env())
    h.update(node.stdout.encode())
    return h.hexdigest()


def ensure_whatsapp_bridge(force=False):
    src_bridge = SRC / "scripts" / "whatsapp-bridge"
    if not src_bridge.exists():
        warn("WhatsApp bridge source is missing; skipping bridge preparation")
        return
    if not (
        (node_bin().exists() and (node_major(node_bin()) or 0) >= MIN_NODE_MAJOR and npm_bin().exists())
        or system_node_ok()
    ):
        ensure_node(force=False)
    desired = bridge_hash(src_bridge)
    marker = WHATSAPP_RUNTIME / ".portable-bridge-hash"
    if force and WHATSAPP_RUNTIME.exists():
        shutil.rmtree(WHATSAPP_RUNTIME, ignore_errors=True)
    if not WHATSAPP_RUNTIME.exists() or (marker.read_text(encoding="utf-8") if marker.exists() else "") != desired:
        info("Preparing WhatsApp bridge in host-local cache")
        if WHATSAPP_RUNTIME.exists():
            shutil.rmtree(WHATSAPP_RUNTIME, ignore_errors=True)
        shutil.copytree(src_bridge, WHATSAPP_RUNTIME, ignore=shutil.ignore_patterns("node_modules", "*.log"))
        npm = str(npm_bin()) if npm_bin().exists() else shutil.which("npm") or "npm"
        run([npm, "install", "--no-fund", "--no-audit", "--progress=false"], cwd=WHATSAPP_RUNTIME, env=portable_env(), timeout=900)
        marker.write_text(desired, encoding="utf-8")
    else:
        success("WhatsApp bridge runtime is current")


def prepare_gateway_runtime(platform_name: str, *, force: bool = False):
    platform_name = platform_name.lower()
    if platform_name not in SETUP_PLATFORMS:
        raise SystemExit(f"Unsupported gateway platform for preparation: {platform_name}")
    if platform_name == "all":
        success("Shared Python gateway runtime is current for Telegram, Discord, Slack, and Signal")
        ensure_whatsapp_bridge(force=force)
        return
    if platform_name in SHARED_GATEWAY_PLATFORMS:
        success(f"{platform_name.title()} uses the shared portable Python gateway runtime")
        return
    if platform_name == "whatsapp":
        ensure_whatsapp_bridge(force=force)


def hermes_cmd(args: list[str], *, env=None, cwd=None):
    h = venv_bin("hermes")
    if h.exists():
        return [str(h)] + args
    return [str(venv_python()), "-m", "hermes_cli.main"] + args


def save_state(extra: dict):
    STATE.write_text(json.dumps(extra, indent=2) + "\n", encoding="utf-8")


def _env_value(name: str, env: dict[str, str] | None = None) -> str:
    source = env if env is not None else portable_env()
    return source.get(name, "").strip()


def _env_has(name: str, env: dict[str, str] | None = None) -> bool:
    return bool(_env_value(name, env))


def print_platform_setup_notes(platform_name: str):
    platform_name = platform_name.lower()
    print()
    print("Portable gateway setup")
    print("  Durable config/secrets go here:")
    print(f"    {DATA / '.env'}")
    print(f"    {DATA / 'config.yaml'}")
    print("  Runtime packages stay in the host-local cache:")
    print(f"    {RUNTIME}")
    print()

    if platform_name in {"telegram", "all"}:
        print("Telegram:")
        print("  1. Create a bot with @BotFather and copy the bot token.")
        print("  2. Find your numeric user ID, for example with @userinfobot.")
        print("  3. Configure TELEGRAM_BOT_TOKEN and TELEGRAM_ALLOWED_USERS.")
        print()
    if platform_name in {"discord", "all"}:
        print("Discord:")
        print("  1. Create an app/bot in the Discord Developer Portal.")
        print("  2. Enable Server Members Intent and Message Content Intent.")
        print("  3. Configure DISCORD_BOT_TOKEN and DISCORD_ALLOWED_USERS.")
        print()
    if platform_name in {"slack", "all"}:
        print("Slack:")
        print("  1. Generate a manifest with:")
        print("       ./hermes-portable -- hermes slack manifest --write")
        print("  2. Create a Slack app from that manifest, install it to your workspace, and enable Socket Mode.")
        print("  3. Copy SLACK_BOT_TOKEN from OAuth & Permissions -> Bot User OAuth Token.")
        print("     It must start with xoxb-. Do NOT use the Verification Token or Signing Secret.")
        print("  4. Copy SLACK_APP_TOKEN from Basic Information -> App-Level Tokens.")
        print("     It must start with xapp- and include the connections:write scope.")
        print("  5. Set SLACK_ALLOWED_USERS to your Slack member ID (profile -> More -> Copy member ID).")
        print("     Without SLACK_ALLOWED_USERS, SLACK_ALLOW_ALL_USERS=true, or GATEWAY_ALLOW_ALL_USERS=true,")
        print("     Slack users are authenticated but denied by Hermes authorization.")
        print()
    if platform_name in {"signal", "all"}:
        print("Signal:")
        print("  1. Install Java 17+ and signal-cli on the host machine.")
        print("  2. Link signal-cli as a secondary Signal device.")
        print("  3. Run signal-cli daemon --http 127.0.0.1:8080.")
        print("  4. Configure SIGNAL_HTTP_URL, SIGNAL_ACCOUNT, and SIGNAL_ALLOWED_USERS.")
        print()
    if platform_name in {"whatsapp", "all"}:
        print("WhatsApp:")
        print("  1. Run ./hermes-portable --platform-action whatsapp pair and scan the QR code.")
        print("  2. Configure WHATSAPP_ENABLED, WHATSAPP_MODE, and WHATSAPP_ALLOWED_USERS.")
        print()


def _platform_action_supported(platform_name: str, action: str) -> bool:
    return action in PLATFORM_ACTIONS.get(platform_name, set())


def _normalize_platform_action(args) -> tuple[str, str] | None:
    if args.platform_action:
        platform_name, action = args.platform_action
        return platform_name.lower(), action.lower()
    if args.setup_platform:
        return args.setup_platform.lower(), "setup"
    if args.pair_whatsapp:
        return "whatsapp", "pair"
    return None


def run_platform_action(platform_name: str, action: str) -> int:
    platform_name = platform_name.lower()
    action = action.lower()
    if platform_name not in SETUP_PLATFORMS:
        raise SystemExit(f"Unsupported platform: {platform_name}")
    if not _platform_action_supported(platform_name, action):
        supported = ", ".join(sorted(PLATFORM_ACTIONS.get(platform_name, set()))) or "none"
        raise SystemExit(f"Unsupported action '{action}' for {platform_name}; supported actions: {supported}")
    env = portable_env()
    if action == "setup":
        print_platform_setup_notes(platform_name)
        if platform_name == "slack":
            info("Writing Slack app manifest in the portable Hermes home")
            subprocess.call(hermes_cmd(["slack", "manifest", "--write"], env=env), cwd=SRC, env=env)
        info("Starting upstream Hermes gateway setup wizard")
        print("  Select the platform(s) you want to configure, then restart the portable gateway.")
        return subprocess.call(hermes_cmd(["gateway", "setup"], env=env), cwd=SRC, env=env)
    if action == "manifest":
        info("Writing Slack app manifest in the portable Hermes home")
        return subprocess.call(hermes_cmd(["slack", "manifest", "--write"], env=env), cwd=SRC, env=env)
    if action == "pair":
        prepare_gateway_runtime(platform_name, force=False)
        return subprocess.call(hermes_cmd(["whatsapp"], env=env), cwd=SRC, env=env)
    raise SystemExit(f"Unhandled platform action: {platform_name} {action}")


def start_gateway(env) -> subprocess.Popen | None:
    info("Starting gateway as child process (portable mode; no service install)")
    log = DATA / "logs" / "gateway-portable-child.log"
    fh = open(log, "a", encoding="utf-8")
    kwargs = {}
    if is_windows():
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(hermes_cmd(["gateway", "run"], env=env), cwd=SRC, env=env, stdout=fh, stderr=subprocess.STDOUT, **kwargs)
    save_state({"gateway_pid": proc.pid, "log": str(log), "runtime": str(RUNTIME), "started_at": time.time()})
    print(f"  gateway pid: {proc.pid}")
    print(f"  gateway log: {log}")
    return proc


def stop_process_tree(proc: subprocess.Popen | None):
    if not proc or proc.poll() is not None:
        return
    info("Stopping gateway child process")
    try:
        if is_windows():
            proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:
        try:
            if is_windows():
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            pass


def _signal_daemon_status(env: dict[str, str]) -> str:
    url = env.get("SIGNAL_HTTP_URL", "").strip().rstrip("/")
    if not url:
        return "not configured"
    try:
        with urllib.request.urlopen(f"{url}/api/v1/check", timeout=2) as response:
            return f"reachable HTTP {response.status}"
    except Exception as exc:
        return f"not reachable ({exc.__class__.__name__})"


def doctor(env, *, show_header: bool = True):
    if show_header:
        print_header()
    print(style("Checks:", GOLD, bold=True))
    check_value("source exists", SRC.exists(), SRC)
    check_value("data exists", DATA.exists(), DATA)
    check_value(".env exists", (DATA / '.env').exists(), DATA / '.env')
    check_value("venv python", venv_python().exists(), venv_python())
    filtered_path = _filtered_inherited_path(os.environ.copy())
    nb = node_bin() if node_bin().exists() else Path(shutil.which("node", path=filtered_path) or "")
    check_value("node", bool(nb), f"{nb}  major={node_major(nb) if nb else None}")
    npm = npm_bin() if npm_bin().exists() else Path(shutil.which("npm", path=filtered_path) or "")
    check_value("npm", bool(npm), npm or "not found")
    check_value("whatsapp bridge", (WHATSAPP_RUNTIME / 'bridge.js').exists(), WHATSAPP_RUNTIME / 'bridge.js')
    key_value("whatsapp session", DATA / 'platforms' / 'whatsapp' / 'session')
    check_value("whatsapp creds", (DATA / 'platforms' / 'whatsapp' / 'session' / 'creds.json').exists())
    slack_bot_token = _env_value("SLACK_BOT_TOKEN", env)
    slack_app_token = _env_value("SLACK_APP_TOKEN", env)
    slack_has_allowlist = any(
        _env_has(name, env)
        for name in ("SLACK_ALLOWED_USERS", "GATEWAY_ALLOWED_USERS")
    ) or any(
        _env_value(name, env).lower() in {"true", "1", "yes"}
        for name in ("SLACK_ALLOW_ALL_USERS", "GATEWAY_ALLOW_ALL_USERS")
    )
    platform_checks = {
        "telegram configured": _env_has("TELEGRAM_BOT_TOKEN", env),
        "discord configured": _env_has("DISCORD_BOT_TOKEN", env),
        "slack tokens present": bool(slack_bot_token and slack_app_token),
        "slack bot token starts xoxb-": slack_bot_token.startswith("xoxb-"),
        "slack app token starts xapp-": slack_app_token.startswith("xapp-"),
        "slack allowed users/open access": slack_has_allowlist,
        "signal configured": _env_has("SIGNAL_HTTP_URL", env) and _env_has("SIGNAL_ACCOUNT", env),
    }
    for label, ok in platform_checks.items():
        check_value(label, ok)
    signal_cli = shutil.which("signal-cli", path=filtered_path)
    check_value("signal-cli", bool(signal_cli), signal_cli or "not found")
    signal_status = _signal_daemon_status(env)
    check_value("signal daemon", signal_status.startswith("reachable"), signal_status)
    if venv_bin("hermes").exists():
        cp = capture(hermes_cmd(["config", "env-path"], env=env), env=env, cwd=SRC)
        key_value("hermes env-path", cp.stdout.strip() or cp.stderr.strip())


def command_run(args):
    ensure_dirs()
    env = portable_env()
    platform_action = _normalize_platform_action(args)
    print_header()
    ensure_venv(force=args.repair)
    ensure_node(force=args.repair_node)
    if not args.skip_gateway_prepare:
        prepare_target = args.prepare_platform or (platform_action[0] if platform_action else "all")
        prepare_gateway_runtime(prepare_target, force=args.repair)
    elif args.prepare_platform or (platform_action and platform_action[1] == "pair"):
        warn("Skipping requested platform preparation because gateway preparation is disabled")
    if args.prepare_platform and not (platform_action or args.doctor or args.gateway_only or args.hermes_args):
        return 0
    if args.doctor:
        doctor(portable_env(), show_header=False)
        return 0
    if platform_action:
        return run_platform_action(*platform_action)
    gateway = None
    try:
        if args.gateway_only or (not args.no_gateway and not args.hermes_args):
            gateway = start_gateway(portable_env())
            if args.gateway_only:
                print("Gateway-only mode. Press Ctrl+C to stop.")
                while gateway.poll() is None:
                    time.sleep(1)
                return gateway.returncode or 0
        hermes_args = args.hermes_args or []
        if hermes_args and hermes_args[0].lower() == "hermes":
            hermes_args = hermes_args[1:]
        return subprocess.call(hermes_cmd(hermes_args, env=portable_env()), cwd=SRC, env=portable_env())
    finally:
        stop_process_tree(gateway)


def reset_runtime():
    print(f"Removing host-local runtime cache: {RUNTIME}")
    shutil.rmtree(RUNTIME, ignore_errors=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Hermes portable v2 launcher")
    parser.add_argument("--no-gateway", action="store_true", help="do not start gateway child")
    parser.add_argument("--gateway-only", action="store_true", help="run gateway in foreground-like supervised mode")
    parser.add_argument("--doctor", action="store_true", help="check portable paths/dependencies")
    parser.add_argument("--repair", action="store_true", help="rebuild the shared portable runtime and gateway-specific host caches")
    parser.add_argument("--repair-node", action="store_true", help="redownload host-local Node runtime")
    parser.add_argument("--reset-runtime", action="store_true", help="delete host-local runtime cache and exit")
    parser.add_argument("--setup-platform", choices=SETUP_PLATFORMS, help="show portable setup notes, then run Hermes gateway setup for a messenger platform")
    parser.add_argument("--prepare-platform", choices=SETUP_PLATFORMS, help="prepare the portable runtime for a messenger platform and exit unless another action is requested")
    parser.add_argument("--platform-action", nargs=2, metavar=("PLATFORM", "ACTION"), help="run a platform-specific portable action such as 'slack manifest' or 'whatsapp pair'")
    parser.add_argument("--pair-whatsapp", action="store_true", help="prepare runtime and run Hermes WhatsApp pairing")
    parser.add_argument("--skip-gateway-prepare", dest="skip_gateway_prepare", action="store_true", help="skip gateway-specific host-cache preparation such as the WhatsApp bridge")
    parser.add_argument("--skip-whatsapp-prepare", dest="skip_gateway_prepare", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("hermes_args", nargs=argparse.REMAINDER, help="arguments passed to hermes; prefix with -- before Hermes args if needed")
    args = parser.parse_args(argv)
    if args.hermes_args and args.hermes_args[0] == "--":
        args.hermes_args = args.hermes_args[1:]
    if args.reset_runtime:
        reset_runtime()
        return 0
    return command_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
