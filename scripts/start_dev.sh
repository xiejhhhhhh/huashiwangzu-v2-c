#!/bin/zsh
# start_dev.sh
#
# One-command startup for the V2 development environment.
# Starts the backend server and prints instructions for the frontend.
#
# Usage:
#   ./scripts/start_dev.sh
#   ./scripts/start_dev.sh --with-models   # also start local model services

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Huashi Wangzu V2 Development Environment ==="
echo ""

# ── 1. Backend ──
echo "[1/3] Backend server (FastAPI port 30004)..."
"$SCRIPT_DIR/start_backend.sh" || echo "[1/3] Backend start failed, continuing..."
echo ""

# ── 2. Model services (optional) ──
if [ "$1" = "--with-models" ]; then
  echo "[2/3] Model services..."
  # opencode-go proxy (cloud model gateway)
  if [ -f "$PROJECT_ROOT/backend/scripts/models/start_opencode_go_proxy.sh" ]; then
    echo "  Starting opencode-go proxy (port 30006)..."
    zsh "$PROJECT_ROOT/backend/scripts/models/start_opencode_go_proxy.sh" &
    sleep 2
  fi
  echo ""
else
  echo "[2/3] Model services: skipped (use --with-models to start local models)"
  echo ""
fi

# ── 3. Frontend (instruction) ──
echo "[3/3] Frontend dev server..."
echo ""
echo "  To start the frontend, run in another terminal:"
echo "    cd frontend && npm run dev"
echo ""
echo "  Then open: http://localhost:5173"
echo ""
echo "=== All done ==="
echo "Health check: http://127.0.0.1:30004/api/health"
