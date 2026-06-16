#!/bin/bash
# 华世王镞 V2 - 数据库备份脚本
# 用法: bash backend/scripts/maintenance/backup_database.sh [备份名称]

set -e

BACKEND_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKUP_ROOT="$BACKEND_ROOT/backups/full"
ENV_FILE="$BACKEND_ROOT/.env"
DB_NAME="华世王镞_v2"
DB_USER="postgres"
DB_HOST="127.0.0.1"
DB_PORT=5432
PG_DUMP=$(which pg_dump 2>/dev/null || echo "pg_dump")
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_NAME="${1:-auto_backup_${TIMESTAMP}}"
BACKUP_DIR="${BACKUP_ROOT}/${BACKUP_NAME}"

if [ -z "$PGPASSWORD" ] && [ -f "$ENV_FILE" ]; then
    export PGPASSWORD=$(grep "^DB_PASSWORD=" "$ENV_FILE" | head -1 | cut -d= -f2)
fi

if [ -z "$PGPASSWORD" ]; then
    echo "ERROR: PGPASSWORD is not set. Export it or configure backend/.env."
    exit 1
fi

if [ ! -f "$PG_DUMP" ]; then
    echo "ERROR: pg_dump not found. Please install PostgreSQL client tools."
    exit 1
fi

mkdir -p "$BACKUP_DIR"
echo "Creating backup: ${BACKUP_NAME}"

# Dump database
DB_FILE="${BACKUP_DIR}/database.sql"
"$PG_DUMP" \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" \
    --no-owner --no-acl --format=custom \
    -f "$DB_FILE" "$DB_NAME" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "  [OK] Database dump: ${DB_FILE}"
else
    echo "  [WARN] Database dump failed (DB may not be running)"
    touch "${BACKUP_DIR}/database_empty"
fi

# Write manifest
MANIFEST="${BACKUP_DIR}/manifest.json"
cat > "$MANIFEST" << JSONEOF
{
    "backup_name": "${BACKUP_NAME}",
    "backup_time": "$(date '+%Y-%m-%d %H:%M:%S')",
    "database_name": "${DB_NAME}",
    "file_list": [{"path": "database.sql", "description": "PostgreSQL custom format dump"}]
}
JSONEOF
echo "  [OK] Manifest written"

echo "Backup completed: ${BACKUP_DIR}"
