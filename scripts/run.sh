#!/usr/bin/env bash
# JPNH launcher: starts the FastAPI backend and the Electron desktop app.
set -euo pipefail

cd "$(dirname "$0")/.."

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "[JPNH] Creating virtual environment…"
  python3 -m venv .venv
  "$PY" -m pip install -q --upgrade pip
  "$PY" -m pip install -q -r requirements.txt
fi

if [ ! -d desktop/node_modules ]; then
  echo "[JPNH] Installing desktop dependencies (Electron)…"
  (cd desktop && npm install)
fi

# Electron on Linux needs a root-owned SUID chrome-sandbox. When that is not
# available (e.g. non-root install), fall back to --no-sandbox.
SANDBOX_ARGS=""
SB=desktop/node_modules/electron/dist/chrome-sandbox
if [ -f "$SB" ]; then
  OWNER=$(stat -c "%U" "$SB" 2>/dev/null || echo root)
  if [ "$OWNER" != "root" ]; then
    echo "[JPNH] chrome-sandbox not root-owned; using --no-sandbox."
    SANDBOX_ARGS="--no-sandbox"
  fi
fi

echo "[JPNH] Launching Johnny Personal Network Hub…"
exec desktop/node_modules/.bin/electron desktop $SANDBOX_ARGS "$@"
