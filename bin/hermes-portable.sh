#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "[ERROR] Python 3.11+ is required to start Hermes portable. Install Python, then rerun this launcher." >&2
    exit 1
  fi
fi
exec "$PYTHON_BIN" "$ROOT/bin/bootstrap_portable.py" "$@"
