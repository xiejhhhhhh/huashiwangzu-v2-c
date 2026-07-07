#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

DB_HOST="127.0.0.1"
DB_PORT="5432"
DB_USER="postgres"
DB_NAME="华世王镞_v2"
SKIP_FRONTEND_BUILD=0
SKIP_START=0
SKIP_SYSTEM_INSTALL=0
SKIP_SEED=0
SKIP_MODULES=0

usage() {
  cat <<'EOF'
Usage: bash scripts/deploy_mac.sh [options]

Options:
  --db-host HOST          PostgreSQL host (default: 127.0.0.1)
  --db-port PORT          PostgreSQL port (default: 5432)
  --db-user USER          PostgreSQL user (default: postgres)
  --db-name NAME          PostgreSQL database (default: 华世王镞_v2)
  --skip-frontend-build   Install frontend deps but skip npm build
  --skip-start            Do not start backend after deployment
  --skip-system-install   Detect system dependencies but do not install them
  --skip-seed             Skip default user/app/role seed data
  --skip-modules          Skip module database init hooks
  -h, --help              Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --db-host) DB_HOST="$2"; shift 2 ;;
    --db-port) DB_PORT="$2"; shift 2 ;;
    --db-user) DB_USER="$2"; shift 2 ;;
    --db-name) DB_NAME="$2"; shift 2 ;;
    --skip-frontend-build) SKIP_FRONTEND_BUILD=1; shift ;;
    --skip-start) SKIP_START=1; shift ;;
    --skip-system-install) SKIP_SYSTEM_INSTALL=1; shift ;;
    --skip-seed) SKIP_SEED=1; shift ;;
    --skip-modules) SKIP_MODULES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

log() { printf '[deploy:mac] %s\n' "$1"; }
fail() { printf '[deploy:mac] ERROR: %s\n' "$1" >&2; exit 1; }
command_exists() { command -v "$1" >/dev/null 2>&1; }

ask_yes_no() {
  local prompt="$1"
  local answer=""
  read -r -p "$prompt [y/N] " answer
  [[ "$answer" == "y" || "$answer" == "Y" ]]
}

prompt_proxy() {
  log "Network acceleration is recommended. Agent-assisted installs often need a proxy for git, pip, npm and Homebrew."
  log "Example: http://127.0.0.1:7890 or socks5://127.0.0.1:7890"
  local proxy=""
  read -r -p "Proxy URL for this deployment process (empty to skip): " proxy
  if [[ -n "$proxy" ]]; then
    export HTTP_PROXY="$proxy"
    export HTTPS_PROXY="$proxy"
    export ALL_PROXY="$proxy"
    export http_proxy="$proxy"
    export https_proxy="$proxy"
    export all_proxy="$proxy"
    export NO_PROXY="127.0.0.1,localhost"
    export no_proxy="$NO_PROXY"
    log "Proxy enabled for this process."
    if ask_yes_no "Also write proxy to global git and npm config"; then
      git config --global http.proxy "$proxy" || true
      git config --global https.proxy "$proxy" || true
      npm config set proxy "$proxy" || true
      npm config set https-proxy "$proxy" || true
      log "Global git/npm proxy updated."
    fi
  fi
}

require_brew() {
  if ! command_exists brew; then
    fail "Homebrew is required for automatic system dependency installation. Install it from https://brew.sh/ and rerun this script."
  fi
}

install_brew_package() {
  local package="$1"
  local binary="$2"
  if command_exists "$binary"; then
    return 0
  fi
  if [[ "$SKIP_SYSTEM_INSTALL" -eq 1 ]]; then
    fail "Missing dependency: $binary. Install package '$package' and rerun."
  fi
  require_brew
  log "Installing $package via Homebrew..."
  brew install "$package"
}

ensure_path_for_brew_packages() {
  if command_exists brew; then
    local brew_prefix
    brew_prefix="$(brew --prefix 2>/dev/null || true)"
    if [[ -n "$brew_prefix" ]]; then
      export PATH="$brew_prefix/bin:$brew_prefix/sbin:$PATH"
      if [[ -d "$brew_prefix/opt/postgresql@17/bin" ]]; then
        export PATH="$brew_prefix/opt/postgresql@17/bin:$PATH"
      fi
      if [[ -d "$brew_prefix/opt/python@3.14/bin" ]]; then
        export PATH="$brew_prefix/opt/python@3.14/bin:$PATH"
      fi
    fi
  fi
}

ensure_system_dependencies() {
  ensure_path_for_brew_packages
  install_brew_package git git
  install_brew_package node node

  if ! command_exists python3.14; then
    if [[ "$SKIP_SYSTEM_INSTALL" -eq 1 ]]; then
      fail "Missing dependency: python3.14"
    fi
    require_brew
    log "Installing python@3.14 via Homebrew..."
    brew install python@3.14
    ensure_path_for_brew_packages
  fi

  if ! command_exists psql; then
    if [[ "$SKIP_SYSTEM_INSTALL" -eq 1 ]]; then
      fail "Missing dependency: psql"
    fi
    require_brew
    log "Installing postgresql@17 via Homebrew..."
    brew install postgresql@17
    ensure_path_for_brew_packages
  fi
}

start_postgres() {
  if command_exists pg_isready && pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
    log "PostgreSQL is already accepting connections on $DB_HOST:$DB_PORT."
    return 0
  fi

  if command_exists brew; then
    log "Trying to start Homebrew postgresql@17..."
    brew services start postgresql@17 >/dev/null 2>&1 || true
    sleep 3
  fi

  if command_exists pg_isready && pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
    log "PostgreSQL is ready on $DB_HOST:$DB_PORT."
    return 0
  fi

  local flyenv_pg="$HOME/Library/FlyEnv/server/postgresql/postgresql17/bin/pg_ctl"
  local flyenv_data="$HOME/Library/FlyEnv/server/postgresql/postgresql17/data"
  if [[ -x "$flyenv_pg" && -d "$flyenv_data" ]]; then
    log "Trying to start FlyEnv PostgreSQL 17..."
    LC_ALL=zh_CN.UTF-8 "$flyenv_pg" -D "$flyenv_data" start >/dev/null 2>&1 || true
    sleep 3
  fi

  if command_exists pg_isready && pg_isready -h "$DB_HOST" -p "$DB_PORT" >/dev/null 2>&1; then
    log "PostgreSQL is ready on $DB_HOST:$DB_PORT."
    return 0
  fi

  fail "PostgreSQL is not reachable on $DB_HOST:$DB_PORT. Start PostgreSQL manually and rerun."
}

read_secret() {
  local prompt="$1"
  local value=""
  read -r -s -p "$prompt" value
  printf '\n' >&2
  printf '%s' "$value"
}

install_backend() {
  log "Preparing backend virtual environment..."
  cd "$BACKEND_DIR"
  python3.14 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
}

install_frontend() {
  log "Installing frontend dependencies..."
  cd "$FRONTEND_DIR"
  npm install
  npm run scan:modules
  if [[ "$SKIP_FRONTEND_BUILD" -eq 0 ]]; then
    npm run build
  else
    log "Frontend build skipped."
  fi
}

run_initializer() {
  cd "$PROJECT_ROOT"
  local db_password seed_password
  db_password="$(read_secret "PostgreSQL password for user '$DB_USER' (empty allowed): ")"
  seed_password=""
  if [[ "$SKIP_SEED" -eq 0 ]]; then
    seed_password="$(read_secret "Default password for admin/editor/viewer seed users: ")"
    if [[ -z "$seed_password" ]]; then
      fail "Seed password cannot be empty unless --skip-seed is used."
    fi
  fi

  # shellcheck disable=SC1091
  source "$BACKEND_DIR/.venv/bin/activate"
  export DB_HOST DB_PORT DB_USER DB_NAME
  export DB_PASSWORD="$db_password"
  export V2_SEED_DEFAULT_PASSWORD="$seed_password"

  local args=(
    --db-host "$DB_HOST"
    --db-port "$DB_PORT"
    --db-user "$DB_USER"
    --db-name "$DB_NAME"
  )
  if [[ "$SKIP_SEED" -eq 1 ]]; then
    args+=(--skip-seed)
  fi
  if [[ "$SKIP_MODULES" -eq 1 ]]; then
    args+=(--skip-modules)
  fi

  python "$SCRIPT_DIR/deploy_common.py" "${args[@]}"
}

start_backend() {
  if [[ "$SKIP_START" -eq 1 ]]; then
    log "Backend startup skipped."
    return 0
  fi
  log "Starting backend watchdog..."
  zsh "$SCRIPT_DIR/start_backend.sh"
}

main() {
  log "Project root: $PROJECT_ROOT"
  prompt_proxy
  ensure_system_dependencies
  start_postgres
  install_backend
  run_initializer
  install_frontend
  start_backend
  log "Deployment completed."
  log "Backend health: http://127.0.0.1:33000/api/health"
  log "Frontend dev server: cd frontend && npm run dev, then open http://127.0.0.1:5173"
}

main
