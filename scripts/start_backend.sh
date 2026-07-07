#!/bin/zsh
# start_backend.sh
#
# Checks if the backend FastAPI server is running on port 33000.
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
PORT=33000
PORT_FILE="$BACKEND_DIR/logs/.backend.port"

cd "$BACKEND_DIR"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
fi

current_port() {
  if [ -f "$PORT_FILE" ]; then
    cat "$PORT_FILE" 2>/dev/null
  else
    echo "$PORT"
  fi
}

is_running_on_port() {
  local port="$1"
  lsof -i :"$port" -P -n 2>/dev/null | grep -q LISTEN
}

wait_for_port_release() {
  local port="$1"
  local timeout_seconds="${2:-20}"
  local i
  for i in $(seq 1 "$timeout_seconds"); do
    if ! is_running_on_port "$port"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_pids_exit() {
  local pids="$1"
  local timeout_seconds="${2:-20}"
  local i pid alive
  for i in $(seq 1 "$timeout_seconds"); do
    alive=0
    for pid in $(echo "$pids"); do
      if kill -0 "$pid" 2>/dev/null; then
        alive=1
        break
      fi
    done
    if [ "$alive" -eq 0 ]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

backend_pids() {
  local pid root_pid candidate
  {
    for pid in $(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null); do
      root_pid=$(project_backend_root_pid "$pid")
      if [ -n "$root_pid" ]; then
        echo "$root_pid"
      fi
    done
    for candidate in $(pgrep -f "uvicorn app.main:app" 2>/dev/null); do
      if is_project_uvicorn "$candidate"; then
        echo "$candidate"
      fi
    done
    for candidate in $(ps -eo pid=,command= | awk '/--multiprocessing-fork/ {print $1}'); do
      if is_project_uvicorn_worker "$candidate"; then
        echo "$candidate"
      fi
    done
  } | sort -n | uniq
}

is_project_uvicorn() {
  local pid="$1" command cwd
  if [ -z "$pid" ]; then
    return 1
  fi
  command=$(ps -p "$pid" -o command= 2>/dev/null)
  cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
  [[ "$command" == *"uvicorn app.main:app"* && "$cwd" == "$BACKEND_DIR" ]]
}

is_project_uvicorn_worker() {
  local pid="$1" command cwd
  if [ -z "$pid" ]; then
    return 1
  fi
  command=$(ps -p "$pid" -o command= 2>/dev/null)
  cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
  [[ "$command" == *"--multiprocessing-fork"* && "$cwd" == "$BACKEND_DIR" ]]
}

is_project_task_worker() {
  local pid="$1" command cwd
  if [ -z "$pid" ]; then
    return 1
  fi
  command=$(ps -p "$pid" -o command= 2>/dev/null)
  cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
  [[ "$command" == *"app.task_worker_main"* && "$cwd" == "$BACKEND_DIR" ]]
}

task_worker_pids() {
  local candidate
  for candidate in $(pgrep -f "app.task_worker_main" 2>/dev/null); do
    if is_project_task_worker "$candidate"; then
      echo "$candidate"
    fi
  done | sort -n | uniq
}

project_backend_root_pid() {
  local pid="$1" current parent
  current="$pid"
  while [ -n "$current" ] && [ "$current" != "0" ] && [ "$current" != "1" ]; do
    if is_project_uvicorn "$current"; then
      echo "$current"
      return 0
    fi
    parent=$(ps -p "$current" -o ppid= 2>/dev/null | tr -d ' ')
    if [ -z "$parent" ] || [ "$parent" = "$current" ]; then
      break
    fi
    current="$parent"
  done
}

watchdog_pids() {
  ps -eo pid=,command= | awk -v script="$SCRIPT_DIR/backend_watchdog.sh" '
    index($0, "zsh " script) > 0 || index($0, "zsh " "\"" script "\"") > 0 { print $1 }
  '
}

start_watchdog() {
  mkdir -p "$BACKEND_DIR/logs"
  screen -dmS backend-watchdog zsh "$SCRIPT_DIR/backend_watchdog.sh" > "$BACKEND_DIR/logs/watchdog_screen.log" 2>&1
  echo "[start_backend] Watchdog started in screen session 'backend-watchdog' (auto-restarts backend if it dies)"
}

if [ "$1" = "--restart" ]; then
  echo "[start_backend] Forcing restart..."
  # 先杀守护进程，否则它会立刻把旧 uvicorn 拉起来
  WATCHDOG_PIDS=$(watchdog_pids)
  if [ -n "$WATCHDOG_PIDS" ]; then
    echo "$WATCHDOG_PIDS" | xargs kill 2>/dev/null && echo "[start_backend] Killed watchdog"
  fi
  sleep 1
  WATCHDOG_PIDS=$(watchdog_pids)
  if [ -n "$WATCHDOG_PIDS" ]; then
    echo "$WATCHDOG_PIDS" | xargs kill -9 2>/dev/null && echo "[start_backend] Force killed watchdog"
    sleep 1
  fi
  BACKEND_PIDS=$(backend_pids)
  if [ -n "$BACKEND_PIDS" ]; then
    echo "$BACKEND_PIDS" | xargs kill 2>/dev/null && echo "[start_backend] Killed old project uvicorn"
    if ! wait_for_pids_exit "$BACKEND_PIDS" 20 || ! wait_for_port_release "$PORT" 10; then
      echo "$BACKEND_PIDS" | xargs kill -9 2>/dev/null && echo "[start_backend] Force killed old project uvicorn"
      wait_for_pids_exit "$BACKEND_PIDS" 10 >/dev/null 2>&1 || true
      wait_for_port_release "$PORT" 10 >/dev/null 2>&1 || true
    fi
  fi
  TASK_WORKER_PIDS=$(task_worker_pids)
  if [ -n "$TASK_WORKER_PIDS" ]; then
    echo "$TASK_WORKER_PIDS" | xargs kill 2>/dev/null && echo "[start_backend] Killed old project task workers"
    if ! wait_for_pids_exit "$TASK_WORKER_PIDS" 20; then
      echo "$TASK_WORKER_PIDS" | xargs kill -9 2>/dev/null && echo "[start_backend] Force killed old project task workers"
      wait_for_pids_exit "$TASK_WORKER_PIDS" 10 >/dev/null 2>&1 || true
    fi
  fi
  rm -rf "$BACKEND_DIR/logs/.watchdog.lock" "$BACKEND_DIR/logs/.watchdog.pid" "$PORT_FILE" 2>/dev/null
fi

PORT=$(current_port)
if is_running_on_port "$PORT"; then
  PID=$(lsof -i :"$PORT" -P -n 2>/dev/null | awk '/LISTEN/{print $2}' | head -1)
  echo "[start_backend] Backend already running on $HOST:$PORT (PID $PID)"
  echo "[start_backend] Health check: http://$HOST:$PORT/api/health"
  if [ -z "$(watchdog_pids)" ]; then
    echo "[start_backend] Watchdog not running; starting watchdog to supervise existing backend"
    rm -rf "$BACKEND_DIR/logs/.watchdog.lock" "$BACKEND_DIR/logs/.watchdog.pid" 2>/dev/null
    start_watchdog
  fi
  exit 0
fi

echo "[start_backend] Starting FastAPI on $HOST:$PORT (with auto-restart watchdog) ..."
# 通过守护进程拉起：uvicorn 崩溃/退出会被自动重启，日志超限自动归档（防磁盘打满导致暴毙）
start_watchdog

# Wait for startup
echo "[start_backend] Waiting for backend to become healthy..."
for i in $(seq 1 30); do
  PORT=$(current_port)
  if curl -s "http://$HOST:$PORT/api/health" >/dev/null 2>&1; then
    echo "[start_backend] Backend is healthy after ${i}s on $HOST:$PORT"
    exit 0
  fi
  sleep 1
done

echo "[start_backend] ERROR: Backend did not start within 30s. Check logs:"
echo "  tail -50 $BACKEND_DIR/logs/backend.log"
exit 1
