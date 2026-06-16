#!/bin/bash
# 华世王镞 V2 - 每日自动备份（建议加入 crontab）
# crontab: 0 3 * * * /path/to/backend/scripts/maintenance/daily_backup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKUP_ROOT="$BACKEND_ROOT/backups/full"
RETENTION_DAYS=${RETENTION_DAYS:-30}
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_NAME="daily_${TIMESTAMP}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting daily backup: ${BACKUP_NAME}"

# Run backup
bash "$SCRIPT_DIR/backup_database.sh" "$BACKUP_NAME"

# Clean old backups (older than RETENTION_DAYS)
find "$BACKUP_ROOT" -maxdepth 1 -type d -name "daily_*" -ctime +${RETENTION_DAYS} -exec rm -rf {} \; 2>/dev/null
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Cleaned backups older than ${RETENTION_DAYS} days"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily backup completed"
