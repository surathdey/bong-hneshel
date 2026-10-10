#!/usr/bin/env bash
# ==============================================================================
# Bong Hneshel — Backend Stop Script
# Run from backend directory or project root: ./stop.sh
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PID_FILE="$DIR/.backend.pid"
PORT="${PORT:-8002}"

echo "=================================================="
echo "🛑 Stopping Bong Hneshel Backend (Port: $PORT)"
echo "=================================================="

STOPPED=0

# 1. Stop systemd service if active
if command -v systemctl >/dev/null 2>&1 && sudo systemctl is-active --quiet bong-hneshel; then
  echo "🔄 Stopping via systemd service (bong-hneshel)..."
  sudo systemctl stop bong-hneshel
  STOPPED=1
fi

# 2. Stop by PID file (for manual / local nohup runs)
if [ -f "$PID_FILE" ]; then
  PID=$(cat "$PID_FILE")
  if ps -p "$PID" > /dev/null 2>&1; then
    echo "Stopping manual process (PID: $PID)..."
    kill -15 "$PID" 2>/dev/null || true
    sleep 1
    if ps -p "$PID" > /dev/null 2>&1; then
      kill -9 "$PID" 2>/dev/null || true
    fi
    STOPPED=1
  fi
  rm -f "$PID_FILE"
fi

# 3. Stop process listening on port
PORT_PID=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PORT_PID" ]; then
  echo "Stopping process listening on port $PORT (PID: $PORT_PID)..."
  kill -15 $PORT_PID 2>/dev/null || true
  sleep 1
  PORT_PID_RETRY=$(lsof -ti :$PORT 2>/dev/null || true)
  if [ -n "$PORT_PID_RETRY" ]; then
    kill -9 $PORT_PID_RETRY 2>/dev/null || true
  fi
  STOPPED=1
fi

if [ "$STOPPED" -eq 1 ]; then
  echo "✅ Backend successfully stopped."
else
  echo "ℹ️  Backend was not running."
fi
