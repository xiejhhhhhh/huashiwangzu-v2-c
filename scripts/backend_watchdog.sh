#!/bin/zsh
# backend_watchdog.sh —— 后端守护进程
# 职责：常驻看护后端 uvicorn，崩溃/退出后自动重启；日志超限自动归档，防止磁盘被打满（曾是后端"暴毙"的主因之一）。
# 由 start_backend.sh 通过 nohup 后台拉起；不要直接前台跑。

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
HOST="127.0.0.1"
PORT=33000
LOG="$BACKEND_DIR/logs/backend.log"
PORT_FILE="$BACKEND_DIR/logs/.backend.port"
MAX_LOG_BYTES=52428800   # 50MB，超过就归档清空
TASK_WORKER_PROCESSES="${TASK_WORKER_PROCESSES:-}"
TASK_WORKER_MEMORY_LIMIT_MB="${TASK_WORKER_MEMORY_LIMIT_MB:-}"
TASK_WORKER_MEMORY_CHECK_SECONDS="${TASK_WORKER_MEMORY_CHECK_SECONDS:-}"

cd "$BACKEND_DIR"
if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
elif [ -f "venv/bin/activate" ]; then
  source venv/bin/activate
fi

mkdir -p "$BACKEND_DIR/logs"

# 单实例守卫：用原子目录锁防止多个 watchdog 同时跑、互相抢端口反复重启。
PIDFILE="$BACKEND_DIR/logs/.watchdog.pid"
LOCKDIR="$BACKEND_DIR/logs/.watchdog.lock"
EXISTING_BACKEND_PID=""
WEB_PID=""
WORKER_PIDS=""

acquire_lock() {
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ > "$PIDFILE"
    return 0
  fi

  OLD_WD=$(cat "$PIDFILE" 2>/dev/null)
  if [ -n "$OLD_WD" ] && [ "$OLD_WD" != "$$" ] && kill -0 "$OLD_WD" 2>/dev/null; then
    echo "[watchdog] $(date '+%F %T') another watchdog already running (PID $OLD_WD), exiting" >> "$LOG"
    exit 0
  fi

  echo "[watchdog] $(date '+%F %T') removing stale watchdog lock" >> "$LOG"
  rm -rf "$LOCKDIR" "$PIDFILE" 2>/dev/null
  if mkdir "$LOCKDIR" 2>/dev/null; then
    echo $$ > "$PIDFILE"
    return 0
  fi

  echo "[watchdog] $(date '+%F %T') failed to acquire watchdog lock, exiting" >> "$LOG"
  exit 1
}

acquire_lock
cleanup_and_exit() {
  stop_process_group "watchdog shutdown"
  rm -rf "$LOCKDIR" "$PIDFILE" 2>/dev/null
  exit 0
}
trap 'rm -rf "$LOCKDIR" "$PIDFILE" 2>/dev/null' EXIT
trap 'cleanup_and_exit' INT TERM

wait_for_port_release() {
  local port="$1"
  for _ in $(seq 1 30); do
    if ! lsof -ti tcp:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

log_listener() {
  local port="$1"
  local pid="$2"
  local command cwd
  command=$(ps -p "$pid" -o command= 2>/dev/null | sed 's/[[:space:]]\+/ /g')
  cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
  echo "[watchdog] $(date '+%F %T') port $port listener pid=$pid cwd=${cwd:-unknown} command=${command:-unknown}" >> "$LOG"
}

is_own_backend_pid() {
  local pid="$1"
  local command cwd
  command=$(ps -p "$pid" -o command= 2>/dev/null)
  cwd=$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
  [[ "$command" == *"uvicorn app.main:app"* && "$cwd" == "$BACKEND_DIR" ]]
}

port_listener_pid() {
  local port="$1"
  lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null | head -1
}

normalize_worker_process_count() {
  if [ -z "$TASK_WORKER_PROCESSES" ]; then
    TASK_WORKER_PROCESSES=$(python3 - <<'PY'
import json
from pathlib import Path
path = Path("data/config/task_worker.json")
try:
    data = json.loads(path.read_text(encoding="utf-8"))
    print(int(data.get("worker_process_slots") or 4))
except Exception:
    print(4)
PY
)
  fi
  case "$TASK_WORKER_PROCESSES" in
    ''|*[!0-9]*)
      TASK_WORKER_PROCESSES=4
      ;;
  esac
  if [ "$TASK_WORKER_PROCESSES" -lt 1 ]; then
    TASK_WORKER_PROCESSES=1
  fi
}

normalize_worker_memory_limits() {
  if [ -z "$TASK_WORKER_MEMORY_LIMIT_MB" ]; then
    TASK_WORKER_MEMORY_LIMIT_MB=$(python3 - <<'PY'
import json
from pathlib import Path
path = Path("data/config/task_worker.json")
try:
    data = json.loads(path.read_text(encoding="utf-8"))
    print(int(data.get("worker_total_memory_limit_mb") or 0))
except Exception:
    print(0)
PY
)
  fi
  if [ -z "$TASK_WORKER_MEMORY_CHECK_SECONDS" ]; then
    TASK_WORKER_MEMORY_CHECK_SECONDS=$(python3 - <<'PY'
import json
from pathlib import Path
path = Path("data/config/task_worker.json")
try:
    data = json.loads(path.read_text(encoding="utf-8"))
    print(int(data.get("worker_memory_check_seconds") or 5))
except Exception:
    print(5)
PY
)
  fi
  case "$TASK_WORKER_MEMORY_LIMIT_MB" in
    ''|*[!0-9]*)
      TASK_WORKER_MEMORY_LIMIT_MB=0
      ;;
  esac
  case "$TASK_WORKER_MEMORY_CHECK_SECONDS" in
    ''|*[!0-9]*)
      TASK_WORKER_MEMORY_CHECK_SECONDS=5
      ;;
  esac
  if [ "$TASK_WORKER_MEMORY_CHECK_SECONDS" -lt 1 ]; then
    TASK_WORKER_MEMORY_CHECK_SECONDS=1
  fi
}

worker_group_rss_kb() {
  local pid total rss
  total=0
  for pid in $(echo "$WORKER_PIDS"); do
    if kill -0 "$pid" 2>/dev/null; then
      rss=$(ps -p "$pid" -o rss= 2>/dev/null | tr -d ' ')
      case "$rss" in
        ''|*[!0-9]*)
          rss=0
          ;;
      esac
      total=$((total + rss))
    fi
  done
  echo "$total"
}

start_worker_group() {
  local idx
  normalize_worker_process_count
  WORKER_PIDS=""
  for idx in $(seq 1 "$TASK_WORKER_PROCESSES"); do
    echo "[watchdog] $(date '+%F %T') starting task worker idx=$idx/$TASK_WORKER_PROCESSES cwd=$BACKEND_DIR" >> "$LOG"
    python3 -m app.task_worker_main >> "$LOG" 2>&1 &
    WORKER_PIDS="$WORKER_PIDS $!"
  done
  echo "[watchdog] $(date '+%F %T') task worker pids=$WORKER_PIDS" >> "$LOG"
}

stop_process_group() {
  local reason="$1"
  local pid
  if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
    echo "[watchdog] $(date '+%F %T') stopping uvicorn pid=$WEB_PID reason=$reason" >> "$LOG"
    kill "$WEB_PID" 2>/dev/null
  fi
  for pid in $(echo "$WORKER_PIDS"); do
    if kill -0 "$pid" 2>/dev/null; then
      echo "[watchdog] $(date '+%F %T') stopping task worker pid=$pid reason=$reason" >> "$LOG"
      kill "$pid" 2>/dev/null
    fi
  done
}

force_stop_process_group() {
  local pid
  if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill -9 "$WEB_PID" 2>/dev/null
  fi
  for pid in $(echo "$WORKER_PIDS"); do
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null
    fi
  done
}

monitor_process_group() {
  local pid rss_kb limit_kb
  normalize_worker_memory_limits
  limit_kb=$((TASK_WORKER_MEMORY_LIMIT_MB * 1024))
  while true; do
    if [ -z "$WEB_PID" ] || ! kill -0 "$WEB_PID" 2>/dev/null; then
      echo "[watchdog] $(date '+%F %T') uvicorn pid=${WEB_PID:-unknown} exited; restarting process group" >> "$LOG"
      return 1
    fi
    for pid in $(echo "$WORKER_PIDS"); do
      if ! kill -0 "$pid" 2>/dev/null; then
        echo "[watchdog] $(date '+%F %T') task worker pid=$pid exited; restarting process group" >> "$LOG"
        return 1
      fi
    done
    if [ "$TASK_WORKER_MEMORY_LIMIT_MB" -gt 0 ]; then
      rss_kb=$(worker_group_rss_kb)
      if [ "$rss_kb" -gt "$limit_kb" ]; then
        echo "[watchdog] $(date '+%F %T') task worker RSS ${rss_kb}KB exceeded limit ${limit_kb}KB (${TASK_WORKER_MEMORY_LIMIT_MB}MB); restarting process group to release memory" >> "$LOG"
        return 1
      fi
    fi
    sleep "$TASK_WORKER_MEMORY_CHECK_SECONDS"
  done
}

check_port() {
  local pid
  EXISTING_BACKEND_PID=""
  pid=$(port_listener_pid "$PORT")
  if [ -z "$pid" ]; then
    return 0
  fi

  log_listener "$PORT" "$pid"
  if is_own_backend_pid "$pid"; then
    echo "[watchdog] $(date '+%F %T') port $PORT is already held by this backend; supervising existing process" >> "$LOG"
    echo "$PORT" > "$PORT_FILE"
    EXISTING_BACKEND_PID="$pid"
    return 1
  fi

  echo "[watchdog] $(date '+%F %T') port $PORT is occupied by external process; backend not started" >> "$LOG"
  return 2
}

while true; do
  # 日志超限归档，防止无限增长打满磁盘
  if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null)" -gt "$MAX_LOG_BYTES" ]; then
    mv "$LOG" "$LOG.old"
  fi

  check_port
  PORT_STATUS=$?
  if [ "$PORT_STATUS" -eq 1 ]; then
    while [ -n "$EXISTING_BACKEND_PID" ] && kill -0 "$EXISTING_BACKEND_PID" 2>/dev/null; do
      sleep 3
    done
    echo "[watchdog] $(date '+%F %T') observed backend pid=${EXISTING_BACKEND_PID:-unknown} exit; restarting" >> "$LOG"
    continue
  elif [ "$PORT_STATUS" -ne 0 ]; then
    sleep 5
    continue
  fi

  echo "$PORT" > "$PORT_FILE"
  echo "[watchdog] $(date '+%F %T') starting uvicorn host=$HOST port=$PORT cwd=$BACKEND_DIR watchdog_pid=$$ task_worker_autostart=0" >> "$LOG"
  TASK_WORKER_AUTOSTART=0 python3 -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers 3 \
    --log-level info >> "$LOG" 2>&1 &
  WEB_PID=$!
  echo "[watchdog] $(date '+%F %T') uvicorn child pid=$WEB_PID port=$PORT" >> "$LOG"
  start_worker_group
  monitor_process_group
  stop_process_group "process group restart"
  sleep 5
  force_stop_process_group
  wait "$WEB_PID" 2>/dev/null
  for pid in $(echo "$WORKER_PIDS"); do
    wait "$pid" 2>/dev/null
  done
  WEB_PID=""
  WORKER_PIDS=""
  echo "[watchdog] $(date '+%F %T') backend process group exited port=$PORT, restarting in 2s" >> "$LOG"
  wait_for_port_release "$PORT" || echo "[watchdog] $(date '+%F %T') port $PORT still busy before restart" >> "$LOG"
  sleep 2
done
