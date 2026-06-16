#!/bin/zsh
# 停止知识库 Worker
# Usage: zsh scripts/worker/stop_worker.sh

SCREEN_SESSION="知识库worker"

screen -list 2>/dev/null | grep -q "$SCREEN_SESSION"
if [ $? -eq 0 ]; then
    screen -S "$SCREEN_SESSION" -X quit
    sleep 1
    screen -list 2>/dev/null | grep -q "$SCREEN_SESSION"
    if [ $? -eq 0 ]; then
        echo "[失败] Worker 停止失败，请手动检查: screen -list"
        exit 1
    else
        echo "[成功] Worker 已停止"
    fi
else
    echo "[信息] Worker 未在运行"
fi
