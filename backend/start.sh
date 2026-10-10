#!/usr/bin/env bash
# ==============================================================================
# Bong Hneshel — Backend Startup Script (FastAPI)
# Run from backend directory or project root: ./start.sh
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

VENV_DIR="$DIR/.venv"
PID_FILE="$DIR/.backend.pid"
LOG_FILE="$DIR/backend.log"
PORT="${PORT:-8002}"

echo "=================================================="
echo "🍛 Bong Hneshel — Backend Startup (Port: $PORT)"
echo "=================================================="

# 1. Check if backend is already running
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if ps -p "$OLD_PID" > /dev/null 2>&1; then
    echo "⚠️  Backend is already running (PID: $OLD_PID) on port $PORT"
    echo "👉 To stop it, run: ./stop.sh"
    exit 0
  else
    rm -f "$PID_FILE"
  fi
fi

PORT_PID=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$PORT_PID" ]; then
  echo "⚠️  Port $PORT is already in use by PID: $PORT_PID"
  echo "👉 To stop it, run: ./stop.sh"
  exit 0
fi

# 3. Check Virtual Environment (Python 3.12 preferred)
if [ ! -d "$VENV_DIR" ]; then
  PYTHON_BIN="python3"
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  fi
  echo "📦 Creating virtual environment using $PYTHON_BIN..."
  $PYTHON_BIN -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip
  "$VENV_DIR/bin/pip" install -r "$DIR/requirements.txt"
fi

# 4. Detect Host Local IP
if command -v ipconfig >/dev/null 2>&1; then
  LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "localhost")
elif command -v hostname >/dev/null 2>&1; then
  LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
else
  LAN_IP="localhost"
fi

# 5. Start Uvicorn Server in Background
echo "🚀 Starting FastAPI on 0.0.0.0:$PORT..."
nohup "$VENV_DIR/bin/uvicorn" server:app --host 0.0.0.0 --port $PORT --reload > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

sleep 2
if ps -p "$SERVER_PID" > /dev/null 2>&1; then
  echo "✅ Backend is running! (PID: $SERVER_PID)"
  echo ""
  echo "--------------------------------------------------"
  echo "🌐 Local API:        http://localhost:$PORT"
  echo "📱 Mobile/LAN:       http://${LAN_IP}:$PORT"
  echo "📖 Interactive Docs: http://localhost:$PORT/docs"
  echo "📄 Log file:         $LOG_FILE"
  echo "--------------------------------------------------"
  echo "👉 Stop backend:     ./stop.sh"
  echo "👉 View live logs:   tail -f $LOG_FILE"
else
  echo "❌ Backend failed to start. Last log lines:"
  tail -n 20 "$LOG_FILE"
  rm -f "$PID_FILE"
  exit 1
fi

