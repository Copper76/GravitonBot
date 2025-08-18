#!/bin/bash
set -euo pipefail

APP_DIR="/home/user/GravitonBot"
VENV_DIR="$APP_DIR/venv"
PY_MAIN="main.py"
BRANCH="master"
LOG_FILE="$APP_DIR/bot.log"

cd "$APP_DIR"

echo "[refresh] Fetching…"
git fetch --all

echo "[refresh] Checkout $BRANCH…"
git checkout "$BRANCH"

echo "[refresh] Reset hard to origin/$BRANCH…"
git reset --hard "origin/$BRANCH"

echo "[refresh] Activating venv…"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "[refresh] Installing deps…"
pip install --upgrade pip
pip install -r requirements.txt

echo "[refresh] Stopping existing bot…"
pids=$(pgrep -f "python3 .*${PY_MAIN}" || true)
[[ -n "${pids}" ]] && kill ${pids} || true

echo "[refresh] Starting bot…"
nohup python3 "$PY_MAIN" > "$LOG_FILE" 2>&1 &

echo "[refresh] Done (PID $!)"
EOF

chmod +x /home/user/GravitonBot/refresh.sh
echo "Bot started with PID $!"

ssh -i ./github_actions_ed25519 user@137.220.103.18 'echo ok && whoami && hostname'
