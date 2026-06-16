#!/bin/zsh
# 启动 opencode-go 云端模型代理（端口 30006）
# 提供 OpenAI 兼容 API，请求转发到 opencode.ai 云端

cd "$(dirname "$0")/../.." || exit 1
source .venv/bin/activate 2>/dev/null

PORT=${1:-30006}
exec python3 -m app.services.proxies.opencode_proxy --port "$PORT"
