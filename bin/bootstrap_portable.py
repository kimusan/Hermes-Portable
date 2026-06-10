#!/usr/bin/env python3
"""Hermes USB portable launcher/bootstrapper.

Design goals:
- keep durable Hermes state on the USB drive (data/)
- keep rebuildable runtimes on the host cache (venv, node, node_modules, npm cache)
- optionally run the gateway only as a child of the portable launcher
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
import tomllib
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
MAX_PYTHON = (3, 14)
RELEASE_VERSION = "0.2.0"
HERMES_UPSTREAM_REPO = "NousResearch/hermes-agent"
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
                changed = False
                if data.get("release_version") != RELEASE_VERSION:
                    data["release_version"] = RELEASE_VERSION
                    changed = True
                if changed:
                    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
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
VENV_PYTHON_META = RUNTIME / "venv-python.json"
DASHBOARD_SOURCE_ROOT = RUNTIME / "dashboard-source"
DASHBOARD_BUILD_MARKER = RUNTIME / "dashboard-build.marker"
DASHBOARD_WEB_DIST = DASHBOARD_SOURCE_ROOT / "hermes_cli" / "web_dist"
DASHBOARD_TUI_DIR = DASHBOARD_SOURCE_ROOT / "ui-tui"
DASHBOARD_TUI_ENTRY = DASHBOARD_TUI_DIR / "dist" / "entry.js"


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def exe(name: str) -> str:
    return name + (".exe" if is_windows() else "")


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if is_windows() else "bin/python")


def venv_bin(name: str) -> Path:
    return VENV / (f"Scripts/{name}.exe" if is_windows() else f"bin/{name}")


def _format_python_version(version: tuple[int, int, int] | tuple[int, int]) -> str:
    return ".".join(str(part) for part in version)


def _read_hermes_python_requirement() -> str:
    pyproject = SRC / "pyproject.toml"
    if not pyproject.exists():
        return f">={_format_python_version(MIN_PYTHON)},<{_format_python_version(MAX_PYTHON)}"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        value = data.get("project", {}).get("requires-python")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception:
        pass
    return f">={_format_python_version(MIN_PYTHON)},<{_format_python_version(MAX_PYTHON)}"


def _parse_version_spec(spec: str) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    minimum = None
    maximum = None
    for part in spec.split(","):
        item = part.strip()
        if item.startswith(">="):
            minimum = tuple(int(piece) for piece in item[2:].split(".")[:2])
        elif item.startswith("<"):
            maximum = tuple(int(piece) for piece in item[1:].split(".")[:2])
    return minimum, maximum


def _python_version_info(python: str | Path) -> tuple[int, int, int] | None:
    cp = capture(
        [
            str(python),
            "-c",
            "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')",
        ]
    )
    if cp.returncode != 0:
        return None
    raw = cp.stdout.strip()
    try:
        major, minor, patch = (int(piece) for piece in raw.split(".")[:3])
        return major, minor, patch
    except Exception:
        return None


def _python_satisfies(version: tuple[int, int, int], spec: str) -> bool:
    minimum, maximum = _parse_version_spec(spec)
    short = version[:2]
    if minimum and short < minimum:
        return False
    if maximum and short >= maximum:
        return False
    return True


def _discover_host_python(spec: str) -> tuple[str, tuple[int, int, int]]:
    candidates: list[str] = []
    for name in ("python3.13", "python3.12", "python3.11", "python3", "python"):
        path = shutil.which(name)
        if path and path not in candidates:
            candidates.append(path)
    current = str(Path(sys.executable).resolve())
    if current not in candidates:
        candidates.append(current)

    checked: list[str] = []
    for candidate in candidates:
        version = _python_version_info(candidate)
        if not version:
            continue
        checked.append(f"{candidate} ({_format_python_version(version)})")
        if _python_satisfies(version, spec):
            return candidate, version

    detail = ", ".join(checked) if checked else "none found"
    raise SystemExit(
        "No compatible host Python interpreter was found for Hermes. "
        f"Hermes requires {spec}; checked: {detail}. "
        "Install Python 3.11, 3.12, or 3.13 and rerun."
    )


def _selected_venv_python(spec: str) -> tuple[str, tuple[int, int, int]]:
    if VENV_PYTHON_META.exists():
        try:
            data = json.loads(VENV_PYTHON_META.read_text(encoding="utf-8"))
            executable = str(data.get("executable", "")).strip()
            version = _python_version_info(executable) if executable else None
            if executable and version and _python_satisfies(version, spec):
                return executable, version
        except Exception:
            pass
    return _discover_host_python(spec)


def run(cmd, *, cwd=None, env=None, check=True, quiet=False, timeout=None):
    if not quiet:
        info(" ".join(map(str, cmd)))
    kwargs = {}
    if quiet:
        kwargs.update({"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL})
    return subprocess.run(cmd, cwd=cwd, env=env, check=check, text=True, timeout=timeout, **kwargs)


def capture(cmd, *, env=None, cwd=None):
    return subprocess.run(cmd, env=env, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _git_output(args: list[str], *, cwd: Path = ROOT) -> str:
    cp = capture(["git", *args], cwd=cwd)
    if cp.returncode != 0:
        detail = cp.stderr.strip() or cp.stdout.strip() or "git command failed"
        raise SystemExit(detail)
    return cp.stdout.strip()


def _git_output_optional(args: list[str], *, cwd: Path = ROOT) -> str:
    cp = capture(["git", *args], cwd=cwd)
    if cp.returncode != 0:
        return ""
    return cp.stdout.strip()


def _require_clean_worktree(repo: Path = ROOT):
    status = _git_output(["status", "--short"], cwd=repo)
    if status:
        raise SystemExit("Refusing to update with local changes present. Commit, stash, or clean the worktree first.")


def _github_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Hermes-Portable-Updater"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _download_file(url: str, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Portable-Updater"})
    with urllib.request.urlopen(req, timeout=60) as response, open(target, "wb") as handle:
        shutil.copyfileobj(response, handle)


def _extract_single_top_level_dir(archive: Path, destination: Path) -> Path:
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(destination)
    children = [p for p in destination.iterdir() if p.is_dir()]
    if len(children) != 1:
        raise SystemExit(f"Expected one extracted directory in {destination}, found {len(children)}")
    return children[0]


def _reset_runtime_after_update(reason: str):
    reset_runtime(reason=reason)
    warn("Runtime cache removed. The next launch will rebuild Hermes against the updated source.")


def _interactive_child_env(env: dict[str, str]) -> dict[str, str]:
    child_env = env.copy()
    # Hermes treats SSH-like PTY environments as "preserve Ctrl+Enter/newline"
    # terminals, leaving c-j free for newline insertion instead of submit.
    # The wrapper's PTY bridge is a nested thin PTY with the same practical
    # newline ambiguity, so advertise an SSH_TTY marker when one is not
    # already present. This keeps the wrapped interactive CLI aligned with
    # direct Hermes behavior for Ctrl+Enter/Ctrl-J newline shortcuts.
    if not any(child_env.get(name) for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "WT_SESSION")):
        try:
            child_env["SSH_TTY"] = os.ttyname(sys.stdin.fileno())
        except Exception:
            child_env["SSH_TTY"] = "pty-wrapper"
    return child_env


def run_interactive_command(cmd: list[str], *, env: dict[str, str], cwd: Path) -> int:
    if is_windows() or not sys.stdin.isatty() or not sys.stdout.isatty():
        return subprocess.call(cmd, cwd=cwd, env=env)

    import pty

    previous_cwd = Path.cwd()
    previous_winch = signal.getsignal(signal.SIGWINCH)
    previous_env = os.environ.copy()

    def _on_winch(_signum, _frame):
        return None

    try:
        os.chdir(cwd)
        os.environ.clear()
        os.environ.update(env)
        signal.signal(signal.SIGWINCH, _on_winch)
        status = pty.spawn(cmd)
    finally:
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_env)
        signal.signal(signal.SIGWINCH, previous_winch)

    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 1


def run_hermes_command(args: list[str], *, env: dict[str, str], interactive: bool = False) -> int:
    cmd = hermes_cmd(args, env=env)
    try:
        if interactive:
            return run_interactive_command(cmd, env=_interactive_child_env(env), cwd=SRC)
        return subprocess.call(cmd, cwd=SRC, env=env)
    except KeyboardInterrupt:
        return 130


def should_use_interactive_pty(hermes_args: list[str]) -> bool:
    if is_windows() or not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    if not hermes_args:
        return True
    first = hermes_args[0].lower()
    if first.startswith('-'):
        return True
    if first in {"chat"}:
        return True
    return False


def update_wrapper() -> int:
    _require_clean_worktree(ROOT)
    branch = _git_output(["rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT)
    upstream = _git_output_optional(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=ROOT)
    if upstream:
        remote, _, ref = upstream.partition("/")
    else:
        remote, ref = "origin", branch
    info(f"Updating portable wrapper from {remote}/{ref}")
    run(["git", "pull", "--ff-only", remote, ref], cwd=ROOT)
    success("Portable wrapper update completed")
    _reset_runtime_after_update("Resetting host-local runtime cache after wrapper update")
    return 0


def resolve_hermes_update_ref(requested_ref: str | None = None) -> str:
    if requested_ref:
        return requested_ref
    try:
        data = _github_json(f"https://api.github.com/repos/{HERMES_UPSTREAM_REPO}/releases/latest")
        tag = str(data.get("tag_name", "")).strip()
        if tag:
            return tag
    except Exception as exc:
        warn(f"Could not query latest Hermes release ({exc}); falling back to upstream main")
    return "main"


def update_hermes(ref: str | None = None) -> int:
    _require_clean_worktree(ROOT)
    resolved_ref = resolve_hermes_update_ref(ref)
    info(f"Updating vendored Hermes source to {resolved_ref}")
    update_root = PORTABLE / "update-cache"
    archive = update_root / "hermes-agent.tar.gz"
    extract_root = update_root / "extract"
    src_parent = SRC.parent
    tag_url = f"https://codeload.github.com/{HERMES_UPSTREAM_REPO}/tar.gz/refs/tags/{resolved_ref}"
    head_url = f"https://codeload.github.com/{HERMES_UPSTREAM_REPO}/tar.gz/refs/heads/{resolved_ref}"
    try:
        _download_file(tag_url, archive)
    except Exception:
        _download_file(head_url, archive)
    extracted_dir = _extract_single_top_level_dir(archive, extract_root)
    src_parent.mkdir(parents=True, exist_ok=True)
    previous_src = src_parent / "hermes-agent.previous"
    shutil.rmtree(previous_src, ignore_errors=True)
    if SRC.exists():
        SRC.rename(previous_src)
    try:
        shutil.move(str(extracted_dir), str(SRC))
    except Exception:
        if previous_src.exists() and not SRC.exists():
            previous_src.rename(SRC)
        raise
    shutil.rmtree(previous_src, ignore_errors=True)
    shutil.rmtree(update_root, ignore_errors=True)
    success(f"Vendored Hermes source updated to {resolved_ref}")
    _reset_runtime_after_update("Resetting host-local runtime cache after Hermes source update")
    return 0


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


DEPRECATED_ENV_KEYS = {
    "TERMINAL_CWD": "Move this to config.yaml under terminal.cwd if you still need a non-default working directory."
}


def cleanup_deprecated_env_keys() -> list[str]:
    env_path = DATA / ".env"
    if not env_path.exists():
        return []
    lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
    kept: list[str] = []
    removed: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            kept.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in DEPRECATED_ENV_KEYS:
            removed.append(key)
            continue
        kept.append(line)
    if removed:
        payload = "\n".join(kept).rstrip()
        if payload:
            payload += "\n"
        env_path.write_text(payload, encoding="utf-8")
    return removed


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


def print_banner():
    if os.environ.get("HERMES_PORTABLE_NO_LOGO"):
        print(style(f"Hermes Portable v{RELEASE_VERSION}", GOLD, bold=True))
        return
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


def print_header(*, show_paths: bool = True):
    print_banner()
    if not show_paths:
        return
    key_value("root", ROOT)
    key_value("HERMES_HOME", DATA)
    key_value("env file", DATA / '.env')
    key_value("runtime cache", RUNTIME)
    key_value("usb id", style(USB_ID, MUTED))


def ensure_dirs():
    for p in [DATA, PORTABLE, RUNTIME, TMP, RUNTIME / "home", RUNTIME / "pip-cache", RUNTIME / "npm-cache", DATA / "logs", DATA / "platforms" / "whatsapp" / "session"]:
        p.mkdir(parents=True, exist_ok=True)


def ensure_python_compatible():
    bootstrap = sys.version_info[:3]
    if bootstrap < MIN_PYTHON:
        raise SystemExit(
            f"Python {_format_python_version(MIN_PYTHON)}+ is required to bootstrap Hermes; "
            f"current is {platform.python_version()}."
        )


def _hermes_install_extras(*, include_dashboard: bool = False) -> tuple[str, ...]:
    extras = ["messaging"]
    if include_dashboard:
        extras.extend(["web", "pty"])
    return tuple(extras)


def _hermes_dashboard_packages(*, include_dashboard: bool = False) -> tuple[str, ...]:
    if not include_dashboard:
        return ()
    return ("python-multipart",)


def ensure_venv(force=False, *, include_dashboard: bool = False):
    ensure_python_compatible()
    requires_python = _read_hermes_python_requirement()
    builder_python, builder_version = _selected_venv_python(requires_python)
    py = venv_python()
    install_extras = _hermes_install_extras(include_dashboard=include_dashboard)
    install_spec = ",".join(install_extras)
    dashboard_packages = _hermes_dashboard_packages(include_dashboard=include_dashboard)
    package_marker = ",".join(dashboard_packages)
    if force and VENV.exists():
        shutil.rmtree(VENV, ignore_errors=True)
    elif py.exists():
        existing_version = _python_version_info(py)
        if not existing_version or not _python_satisfies(existing_version, requires_python):
            warn(
                "Cached portable venv uses an incompatible Python "
                f"({_format_python_version(existing_version) if existing_version else 'unknown'}); rebuilding"
            )
            shutil.rmtree(VENV, ignore_errors=True)
    if not py.exists():
        info(
            "Creating host-local Python venv with "
            f"{builder_python} ({_format_python_version(builder_version)})"
        )
        run([builder_python, "-m", "venv", str(VENV)])
        VENV_PYTHON_META.write_text(
            json.dumps(
                {
                    "executable": builder_python,
                    "version": _format_python_version(builder_version),
                    "requires_python": requires_python,
                },
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
    # Make sure pip exists. Do not run ensurepip on every launch; some
    # Python builds are noisy even when everything is already present.
    pip_check = capture([str(py), "-m", "pip", "--version"])
    if pip_check.returncode != 0:
        run([str(py), "-m", "ensurepip", "--upgrade"], check=False, quiet=True)
    marker = RUNTIME / "hermes-install.marker"
    source_marker = hashlib.sha256(str(SRC.resolve()).encode()).hexdigest()[:16]
    desired_marker = f"{source_marker}|extras={install_spec}|packages={package_marker}|python={requires_python}"
    installed_marker = marker.read_text(encoding="utf-8") if marker.exists() else ""
    if force or not venv_bin("hermes").exists() or installed_marker != desired_marker:
        info("Installing Hermes into host-local venv from USB source")
        run([str(py), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"], env=portable_env())
        run([str(py), "-m", "pip", "install", "-e", f"{SRC}[{install_spec}]"], env=portable_env())
        if dashboard_packages:
            run([str(py), "-m", "pip", "install", *dashboard_packages], env=portable_env())
        marker.write_text(desired_marker, encoding="utf-8")


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


def _effective_node_binary(env: dict[str, str] | None = None) -> str:
    if node_bin().exists() and (node_major(node_bin()) or 0) >= MIN_NODE_MAJOR:
        return str(node_bin())
    path = (env or portable_env()).get("PATH", "")
    return shutil.which("node", path=path) or "node"


def _effective_npm_binary(env: dict[str, str] | None = None) -> str:
    if npm_bin().exists():
        return str(npm_bin())
    path = (env or portable_env()).get("PATH", "")
    return shutil.which("npm", path=path) or "npm"


def _dashboard_build_env() -> dict[str, str]:
    env = portable_env()
    env["HERMES_NODE"] = _effective_node_binary(env)
    return env


def dashboard_env() -> dict[str, str]:
    env = _dashboard_build_env()
    env["HERMES_WEB_DIST"] = str(DASHBOARD_WEB_DIST)
    env["HERMES_TUI_DIR"] = str(DASHBOARD_TUI_DIR)
    return env


def _dashboard_source_hash() -> str:
    excluded = {".git", "node_modules", "__pycache__", "web_dist", "tui_dist", "dist", "release", ".pytest_cache", ".ruff_cache"}
    h = hashlib.sha256()
    for file_path in sorted(SRC.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(SRC)
        if any(part in excluded for part in rel.parts):
            continue
        if file_path.suffix in {".pyc", ".pyo"}:
            continue
        h.update(rel.as_posix().encode("utf-8", "ignore"))
        h.update(file_path.read_bytes())
    node_version = capture([_effective_node_binary(_dashboard_build_env()), "--version"], env=_dashboard_build_env())
    h.update(node_version.stdout.encode("utf-8", "ignore"))
    return h.hexdigest()


def ensure_dashboard_assets(*, force: bool = False):
    desired = _dashboard_source_hash()
    current = DASHBOARD_BUILD_MARKER.read_text(encoding="utf-8") if DASHBOARD_BUILD_MARKER.exists() else ""
    if force:
        shutil.rmtree(DASHBOARD_SOURCE_ROOT, ignore_errors=True)
    if (
        not force
        and current == desired
        and (DASHBOARD_WEB_DIST / "index.html").exists()
        and DASHBOARD_TUI_ENTRY.exists()
    ):
        success("Portable dashboard assets are current")
        return

    info("Preparing dashboard source/build cache in host-local runtime")
    shutil.rmtree(DASHBOARD_SOURCE_ROOT, ignore_errors=True)
    shutil.copytree(
        SRC,
        DASHBOARD_SOURCE_ROOT,
        ignore=shutil.ignore_patterns(
            ".git", "node_modules", "__pycache__", "*.pyc", "*.pyo",
            "web_dist", "tui_dist", ".pytest_cache", ".ruff_cache",
            "release"
        ),
    )
    env = _dashboard_build_env()
    npm = _effective_npm_binary(env)
    run(
        [
            npm,
            "install",
            "--no-fund",
            "--no-audit",
            "--progress=false",
            "--workspace",
            "web",
            "--workspace",
            "ui-tui",
            "--workspace",
            "ui-tui/packages/hermes-ink",
            "--include-workspace-root=false",
        ],
        cwd=DASHBOARD_SOURCE_ROOT,
        env=env,
        timeout=1800,
    )
    run([npm, "run", "build", "--workspace", "ui-tui"], cwd=DASHBOARD_SOURCE_ROOT, env=env, timeout=1800)
    run([npm, "run", "build", "--workspace", "web"], cwd=DASHBOARD_SOURCE_ROOT, env=env, timeout=1800)
    if not (DASHBOARD_WEB_DIST / "index.html").exists():
        raise SystemExit(f"Dashboard web build did not produce {DASHBOARD_WEB_DIST / 'index.html'}")
    if not DASHBOARD_TUI_ENTRY.exists():
        raise SystemExit(f"Dashboard TUI build did not produce {DASHBOARD_TUI_ENTRY}")
    DASHBOARD_BUILD_MARKER.write_text(desired, encoding="utf-8")
    success("Portable dashboard assets are current")


def _dashboard_server_mode(hermes_args: list[str]) -> str | None:
    if not hermes_args or hermes_args[0].lower() != "dashboard":
        return None
    if len(hermes_args) > 1 and not hermes_args[1].startswith("-"):
        return None
    if "--status" in hermes_args:
        return "status"
    if "--stop" in hermes_args:
        return "stop"
    return "start"


def _wrapper_dashboard_requested(args) -> bool:
    return bool(getattr(args, "dashboard", False) or getattr(args, "dashboard_stop", False) or getattr(args, "dashboard_status", False))


def _wrapper_dashboard_args(args) -> list[str]:
    cmd = ["dashboard"]
    if args.dashboard_status:
        cmd.append("--status")
        return cmd
    if args.dashboard_stop:
        cmd.append("--stop")
        return cmd
    cmd.extend(["--host", args.dashboard_host, "--port", str(args.dashboard_port)])
    if args.dashboard_no_open:
        cmd.append("--no-open")
    if args.dashboard_insecure:
        cmd.append("--insecure")
    return cmd


def _dashboard_launch_options(hermes_args: list[str]) -> tuple[str, int, bool]:
    host = "127.0.0.1"
    port = 9119
    no_open = False
    for index, arg in enumerate(hermes_args):
        if arg == "--host" and index + 1 < len(hermes_args):
            host = hermes_args[index + 1]
        elif arg.startswith("--host="):
            host = arg.split("=", 1)[1]
        elif arg == "--port" and index + 1 < len(hermes_args):
            try:
                port = int(hermes_args[index + 1])
            except ValueError:
                pass
        elif arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg == "--no-open":
            no_open = True
    return host, port, no_open


def _system_open_command(url: str) -> list[str] | None:
    system = platform.system().lower()
    if system == "linux":
        opener = shutil.which("xdg-open")
        return [opener, url] if opener else None
    if system == "darwin":
        opener = shutil.which("open")
        return [opener, url] if opener else None
    if system == "windows":
        comspec = os.environ.get("COMSPEC") or shutil.which("cmd.exe")
        return [comspec, "/c", "start", "", url] if comspec else None
    return None


def _schedule_system_browser_open(url: str, *, delay_seconds: float = 1.0):
    cmd = _system_open_command(url)
    if not cmd:
        warn(f"No system URL opener found; open {url} manually")
        return

    def _open_later():
        time.sleep(delay_seconds)
        try:
            kwargs = {}
            if is_windows():
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
        except Exception as exc:
            warn(f"Could not open dashboard URL automatically ({exc}); open {url} manually")

    threading.Thread(target=_open_later, daemon=True).start()


def _should_start_dashboard_gateway(args, dashboard_mode: str | None) -> bool:
    return bool(dashboard_mode == "start" and not args.no_gateway and not getattr(args, "dashboard_no_gateway", False))


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
            run_hermes_command(["slack", "manifest", "--write"], env=env)
        info("Starting upstream Hermes gateway setup wizard")
        print("  Select the platform(s) you want to configure, then restart the portable gateway.")
        return run_hermes_command(["gateway", "setup"], env=env, interactive=True)
    if action == "manifest":
        info("Writing Slack app manifest in the portable Hermes home")
        return run_hermes_command(["slack", "manifest", "--write"], env=env)
    if action == "pair":
        prepare_gateway_runtime(platform_name, force=False)
        return run_hermes_command(["whatsapp"], env=env, interactive=True)
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
    requires_python = _read_hermes_python_requirement()
    check_value("source exists", SRC.exists(), SRC)
    check_value("data exists", DATA.exists(), DATA)
    check_value(".env exists", (DATA / '.env').exists(), DATA / '.env')
    key_value("bootstrap python", f"{sys.executable} ({platform.python_version()})")
    key_value("hermes python", requires_python)
    check_value("venv python", venv_python().exists(), venv_python())
    if venv_python().exists():
        version = _python_version_info(venv_python())
        check_value(
            "venv python compatible",
            bool(version and _python_satisfies(version, requires_python)),
            _format_python_version(version) if version else "unknown",
        )
    check_value("dashboard web dist", (DASHBOARD_WEB_DIST / 'index.html').exists(), DASHBOARD_WEB_DIST / 'index.html')
    check_value("dashboard tui dist", DASHBOARD_TUI_ENTRY.exists(), DASHBOARD_TUI_ENTRY)
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
    removed_env_keys = cleanup_deprecated_env_keys()
    env = portable_env()
    platform_action = _normalize_platform_action(args)
    cleanup_runtime = should_cleanup_runtime_on_exit(args)
    hermes_args = args.hermes_args or []
    if hermes_args and hermes_args[0].lower() == "hermes":
        hermes_args = hermes_args[1:]
    if _wrapper_dashboard_requested(args):
        hermes_args = _wrapper_dashboard_args(args)
    if args.resume_session_id:
        hermes_args = ["--resume", args.resume_session_id, *hermes_args]
    dashboard_mode = _dashboard_server_mode(hermes_args)
    print_header()
    for key in removed_env_keys:
        warn(f"Removed deprecated {key} entry from {DATA / '.env'}")
        print(f"  {DEPRECATED_ENV_KEYS.get(key, '')}")
    if cleanup_runtime:
        info("Temporary-machine mode enabled; host-local runtime cache will be removed on exit")
    gateway = None
    try:
        ensure_venv(force=args.repair, include_dashboard=(dashboard_mode == "start"))
        if dashboard_mode == "start" or not dashboard_mode:
            ensure_node(force=args.repair_node)
        dashboard_starts_gateway = _should_start_dashboard_gateway(args, dashboard_mode)
        if dashboard_mode:
            if dashboard_starts_gateway and not args.skip_gateway_prepare:
                prepare_target = args.prepare_platform or (platform_action[0] if platform_action else "all")
                prepare_gateway_runtime(prepare_target, force=args.repair)
            elif dashboard_starts_gateway and (args.prepare_platform or (platform_action and platform_action[1] == "pair")):
                warn("Skipping requested platform preparation because gateway preparation is disabled")
            elif args.prepare_platform or (platform_action and platform_action[1] == "pair"):
                warn("Skipping requested platform preparation because dashboard mode does not use gateway runtime preparation")
        elif not args.skip_gateway_prepare:
            prepare_target = args.prepare_platform or (platform_action[0] if platform_action else "all")
            prepare_gateway_runtime(prepare_target, force=args.repair)
        elif args.prepare_platform or (platform_action and platform_action[1] == "pair"):
            warn("Skipping requested platform preparation because gateway preparation is disabled")
        if args.prepare_platform and not (platform_action or args.doctor or args.gateway_only or hermes_args):
            return 0
        if args.doctor:
            doctor(portable_env(), show_header=False)
            return 0
        if platform_action:
            return run_platform_action(*platform_action)
        if dashboard_mode:
            hermes_env = portable_env()
            if dashboard_mode == "start":
                ensure_dashboard_assets(force=args.repair or args.repair_node)
                hermes_env = dashboard_env()
                if _should_start_dashboard_gateway(args, dashboard_mode):
                    gateway = start_gateway(portable_env())
                host, port, no_open = _dashboard_launch_options(hermes_args)
                if "--skip-build" not in hermes_args:
                    hermes_args = [*hermes_args, "--skip-build"]
                if "--no-open" not in hermes_args:
                    hermes_args = [*hermes_args, "--no-open"]
                if not no_open:
                    _schedule_system_browser_open(f"http://{host}:{port}")
            return run_hermes_command(hermes_args, env=hermes_env, interactive=False)
        if args.gateway_only or (not args.no_gateway and not hermes_args):
            gateway = start_gateway(portable_env())
            if args.gateway_only:
                print("Gateway-only mode. Press Ctrl+C to stop.")
                while gateway.poll() is None:
                    time.sleep(1)
                return gateway.returncode or 0
        return run_hermes_command(hermes_args, env=portable_env(), interactive=should_use_interactive_pty(hermes_args))
    finally:
        stop_process_tree(gateway)
        if cleanup_runtime:
            reset_runtime(reason="Cleaning up temporary-machine host-local runtime cache")


def reset_runtime(*, reason: str | None = None):
    if reason:
        info(reason)
    print(f"Removing host-local runtime cache: {RUNTIME}")
    shutil.rmtree(RUNTIME, ignore_errors=True)


def should_cleanup_runtime_on_exit(args) -> bool:
    return bool(getattr(args, "temporary", False) or getattr(args, "cleanup_runtime_on_exit", False))


class PortableArgumentParser(argparse.ArgumentParser):
    def _print_banner_once(self, file=None):
        if getattr(self, "_portable_banner_printed", False):
            return
        self._portable_banner_printed = True
        stream = file or sys.stdout
        with contextlib.redirect_stdout(stream):
            print_header(show_paths=False)
            print()

    def print_help(self, file=None):
        self._print_banner_once(file=file)
        super().print_help(file=file)

    def error(self, message):
        self._print_banner_once(file=sys.stderr)
        super().error(message)


def main(argv=None):
    parser = PortableArgumentParser(description="Hermes portable v2 launcher")
    parser.add_argument("--no-gateway", action="store_true", help="do not start gateway child")
    parser.add_argument("--gateway-only", action="store_true", help="run gateway in foreground-like supervised mode")
    parser.add_argument("--doctor", action="store_true", help="check portable paths/dependencies")
    parser.add_argument("--repair", action="store_true", help="rebuild the shared portable runtime and gateway-specific host caches")
    parser.add_argument("--repair-node", action="store_true", help="redownload host-local Node runtime")
    parser.add_argument("--reset-runtime", action="store_true", help="delete host-local runtime cache and exit")
    parser.add_argument("--update-wrapper", action="store_true", help="fast-forward this portable wrapper repo from its git upstream and reset local runtime cache")
    parser.add_argument("--update-hermes", action="store_true", help="replace src/hermes-agent with the latest upstream Hermes release and reset local runtime cache")
    parser.add_argument("--update-hermes-ref", help="update src/hermes-agent to a specific upstream Hermes tag or branch")
    parser.add_argument("--temporary", action="store_true", help="use temporary-machine mode and remove the host-local runtime cache on exit")
    parser.add_argument("--cleanup-runtime-on-exit", action="store_true", help="remove the host-local runtime cache on exit")
    parser.add_argument("--dashboard", action="store_true", help="start Hermes dashboard with host-cached portable web/TUI assets")
    parser.add_argument("--dashboard-stop", action="store_true", help="stop running Hermes dashboard processes")
    parser.add_argument("--dashboard-status", action="store_true", help="list running Hermes dashboard processes")
    parser.add_argument("--dashboard-host", default="127.0.0.1", help="dashboard host to bind when using --dashboard (default 127.0.0.1)")
    parser.add_argument("--dashboard-port", type=int, default=9119, help="dashboard port to bind when using --dashboard (default 9119)")
    parser.add_argument("--dashboard-no-open", action="store_true", help="do not auto-open a browser when using --dashboard")
    parser.add_argument("--dashboard-no-gateway", action="store_true", help="start the dashboard without the portable gateway child")
    parser.add_argument("--dashboard-insecure", action="store_true", help="allow non-localhost dashboard binds without auth hardening when using --dashboard")
    parser.add_argument("--setup-platform", choices=SETUP_PLATFORMS, help="show portable setup notes, then run Hermes gateway setup for a messenger platform")
    parser.add_argument("--prepare-platform", choices=SETUP_PLATFORMS, help="prepare the portable runtime for a messenger platform and exit unless another action is requested")
    parser.add_argument("--platform-action", nargs=2, metavar=("PLATFORM", "ACTION"), help="run a platform-specific portable action such as 'slack manifest' or 'whatsapp pair'")
    parser.add_argument("--resume", dest="resume_session_id", help="resume a Hermes session by ID, like 'hermes --resume <session-id>'")
    parser.add_argument("--pair-whatsapp", action="store_true", help="prepare runtime and run Hermes WhatsApp pairing")
    parser.add_argument("--skip-gateway-prepare", dest="skip_gateway_prepare", action="store_true", help="skip gateway-specific host-cache preparation such as the WhatsApp bridge")
    parser.add_argument("--skip-whatsapp-prepare", dest="skip_gateway_prepare", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("hermes_args", nargs=argparse.REMAINDER, help="arguments passed to hermes; prefix with -- before Hermes args if needed")
    args = parser.parse_args(argv)
    if args.hermes_args and args.hermes_args[0] == "--":
        args.hermes_args = args.hermes_args[1:]
    if args.update_wrapper and (args.update_hermes or args.update_hermes_ref):
        raise SystemExit("Run --update-wrapper and --update-hermes separately so each update can complete cleanly.")
    dashboard_ops = sum(bool(value) for value in (args.dashboard, args.dashboard_stop, args.dashboard_status))
    if dashboard_ops > 1:
        raise SystemExit("Choose only one of --dashboard, --dashboard-stop, or --dashboard-status.")
    if args.reset_runtime:
        print_header(show_paths=False)
        reset_runtime()
        return 0
    if args.update_wrapper:
        print_header(show_paths=False)
        return update_wrapper()
    if args.update_hermes or args.update_hermes_ref:
        print_header(show_paths=False)
        return update_hermes(args.update_hermes_ref)
    return command_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
