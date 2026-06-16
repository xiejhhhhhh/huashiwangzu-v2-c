#!/bin/zsh
# 批量向量化 D4 - 给存量 chunks 补向量
# Usage: zsh scripts/maintenance/vectorize_existing_chunks.sh [catalog_id]

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SELF_DIR/../.." && pwd)"
VENV="$PROJECT_DIR/.venv/bin/activate"
CATALOG_ID="${1:-}"

if [ ! -f "$VENV" ]; then
    echo "[失败] 虚拟环境未找到: $VENV"
    exit 1
fi

source "$VENV"

echo "========================================"
echo " D4 批量向量化"
echo " 目录: $PROJECT_DIR"
echo " catalog_id: ${CATALOG_ID:-全部}"
echo "========================================"

cd "$PROJECT_DIR"

python3 -c "
import asyncio, sys
sys.path.insert(0, '.')
from app.database import AsyncSessionLocal
from app.services.knowledge.embedding_service import EmbeddingService

async def main():
    catalog_id = None if not '$CATALOG_ID' else int('$CATALOG_ID')
    async with AsyncSessionLocal() as db:
        count = await EmbeddingService.vectorize_chunks_batch(
            db, catalog_id=catalog_id,
        )
    print(f'[完成] 向量化 {count} 个 chunk')

asyncio.run(main())
"

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[成功] 向量化完成"
else
    echo "[失败] 脚本异常退出 (code=$EXIT_CODE)"
fi
exit $EXIT_CODE
