#!/bin/bash
set -euo pipefail

APP_DIR="$1"
PY_MAIN="main.py"

cd "$APP_DIR"

echo "[refresh] Stopping existing bot…"
pids=$(pgrep -f "python3 .*${PY_MAIN}" || true)
[[ -n "${pids}" ]] && kill ${pids} || true

echo "Killed Bot"
