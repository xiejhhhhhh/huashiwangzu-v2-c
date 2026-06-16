#!/bin/zsh
# 启动知识库 Worker（用 screen 跑后台）
# Usage: zsh scripts/worker/start_worker.sh [--interval 15] [--lease-minutes 30]

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SELF_DIR/../.." && pwd)"
VENV="$PROJECT_DIR/.venv/bin/activate"
WORKER_SCRIPT="$SELF_DIR/knowledge_worker.py"
SCREEN_SESSION="知识库worker"

# 检查是否已在运行
screen -list 2>/dev/null | grep -q "$SCREEN_SESSION"
if [ $? -eq 0 ]; then
    echo "[错误] Worker 已在运行 (screen session: $SCREEN_SESSION)"
    echo "如需重启，先运行: zsh scripts/worker/stop_worker.sh"
    exit 1
fi

if [ ! -f "$VENV" ]; then
    echo "[失败] 虚拟环境未找到: $VENV"
    exit 1
fi

if [ ! -f "$WORKER_SCRIPT" ]; then
    echo "[失败] Worker 脚本未找到: $WORKER_SCRIPT"
    exit 1
fi

source "$VENV"

EXTRA_ARGS="${@:---interval 15}"

screen -dmS "$SCREEN_SESSION" zsh -c "
    source $VENV
    cd $PROJECT_DIR
    exec python3 $WORKER_SCRIPT $EXTRA_ARGS
"

sleep 1
screen -list 2>/dev/null | grep -q "$SCREEN_SESSION"
if [ $? -eq 0 ]; then
    echo "[成功] Worker 已启动 (screen session: $SCREEN_SESSION)"
    echo "查看日志: screen -r $SCREEN_SESSION"
    echo "分离: Ctrl+A, D"
else
    echo "[失败] Worker 启动失败"
    exit 1
fi
