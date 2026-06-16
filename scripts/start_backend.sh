#!/bin/zsh
# start_backend.sh
#
# Checks if the backend FastAPI server is running on port 30004.
# If not, starts it automatically.
#
# Usage:
#   ./scripts/start_backend.sh                 # start or verify running
#   ./scripts/start_backend.sh --restart       # force restart

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
HOST="127.0.0.1"
PORT=30004

cd "$BACKEND_DIR"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
fi

is_running() {
  lsof -i :$PORT -P -n 2>/dev/null | grep -q LISTEN
}

if [ "$1" = "--restart" ]; then
  echo "[start_backend] Forcing restart..."
  PID=$(lsof -i :$PORT -P -n 2>/dev/null | awk '/LISTEN/{print $2}' | head -1)
  if [ -n "$PID" ]; then
    kill "$PID" 2>/dev/null && echo "[start_backend] Killed old process $PID"
    sleep 2
  fi
fi

if is_running; then
  PID=$(lsof -i :$PORT -P -n 2>/dev/null | awk '/LISTEN/{print $2}' | head -1)
  echo "[start_backend] Backend already running on $HOST:$PORT (PID $PID)"
  echo "[start_backend] Health check: http://$HOST:$PORT/api/health"
  exit 0
fi

echo "[start_backend] Starting FastAPI on $HOST:$PORT ..."
nohup python3 -m uvicorn app.main:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers 1 \
  --log-level info \
  > "$BACKEND_DIR/logs/backend.log" 2>&1 &

BACKEND_PID=$!
echo "[start_backend] Backend PID: $BACKEND_PID"

# Wait for startup
echo "[start_backend] Waiting for backend to become healthy..."
for i in $(seq 1 30); do
  if curl -s "http://$HOST:$PORT/api/health" >/dev/null 2>&1; then
    echo "[start_backend] Backend is healthy after ${i}s"
    exit 0
  fi
  sleep 1
done

echo "[start_backend] ERROR: Backend did not start within 30s. Check logs:"
echo "  tail -50 $BACKEND_DIR/logs/backend.log"
exit 1
