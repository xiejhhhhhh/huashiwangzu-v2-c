#!/bin/bash
# 华世王镞 V2 - 测试环境数据库备份脚本
# 用法: bash backend/scripts/maintenance/backup_test.sh
# 密码从环境变量 PGPASSWORD 或 backend/.env 获取

set -e

BACKEND_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKUP_ROOT="$BACKEND_ROOT/backups"
ENV_FILE="$BACKEND_ROOT/.env"
DB_NAME="华世王镞_v2"
DB_USER="postgres"
DB_HOST="127.0.0.1"
DB_PORT=5432
PG_DUMP="/Library/PostgreSQL/17/bin/pg_dump"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILE="${BACKUP_ROOT}/${DB_NAME}_${TIMESTAMP}.dump"
RETENTION_DAYS=14

# 优先用环境变量，否则从 .env 读取
if [ -z "$PGPASSWORD" ] && [ -f "$ENV_FILE" ]; then
    export PGPASSWORD=$(grep "^DB_PASSWORD=" "$ENV_FILE" | head -1 | cut -d= -f2)
fi

if [ -z "$PGPASSWORD" ]; then
    echo "ERROR: PGPASSWORD 未设置，请 export PGPASSWORD=xxx 或配置 backend/.env"
    exit 1
fi

mkdir -p "$BACKUP_ROOT"

if [ ! -f "$PG_DUMP" ]; then
    echo "ERROR: pg_dump not found at $PG_DUMP"
    echo "请确认 PostgreSQL 17 已安装"
    exit 1
fi

echo "===== 备份开始: $(date) ====="
echo "数据库: $DB_NAME"
echo "输出: $BACKUP_FILE"
echo ""

"$PG_DUMP" \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
    --no-owner --no-acl --format=custom \
    -f "$BACKUP_FILE" "$DB_NAME"

if [ $? -eq 0 ]; then
    FILE_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "[OK] 备份成功: $BACKUP_FILE ($FILE_SIZE)"
else
    echo "[FAIL] pg_dump 失败"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# 清理旧备份（保留最近 14 天）
echo ""
echo "清理 ${RETENTION_DAYS} 天前的备份..."
find "$BACKUP_ROOT" -name "${DB_NAME}_*.dump" -type f -mtime +${RETENTION_DAYS} -delete
find "$BACKUP_ROOT" -name "${DB_NAME}_*.dump" -type f | sort

echo ""
echo "===== 备份完成 ====="
echo "已保留以下备份文件:"
ls -lh "$BACKUP_ROOT"/*.dump 2>/dev/null || echo "  (无)"
